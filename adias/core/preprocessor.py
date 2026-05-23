"""01pre：超级背景预处理。

对每个观测目录扫描原始 .fit，按 superflag 选择算法（中值滤波 / 同态滤波 /
Retinex），结果落到同日 fits_n/ 子目录。

并发模型
--------
  - 文件级：ProcessPoolExecutor，n_workers = min(文件数, CPU 核数)
  - 滤波内：median_impl="scipy_threaded" 时沿正交轴切块多线程
  - 子进程内 redirect_stdout 捕获日志，主进程按提交顺序回放，
    保证文件处理顺序与日志可读性
"""

import io
import os
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path

import cv2
import numpy as np

from adias.application.log import get_logger, setup_logging
from adias.application.pipeline import StepResult
from adias.io.fits_io import read_fits, write_fits
from adias.paths import (
    PRE_DIR,
    clean_pre_dir,
    ensure_dir,
    list_fits,
    pre_path,
    stage_dirs,
)
from adias.utils.image_utils import (
    apply_smooth,
    apply_superbkgd,
    bilateral_retinex,
    calculate_background,
    homomorphic_filter,
)

_log = get_logger("pre")


def _process_one(fitsfile, med_length, med_width, bkgdmode, enhance_flag, out_file,
                 median_impl="scipy", n_threads=1):
    """单幅 FITS 的超级背景扣除。

    med_length 或 med_width 为 1 时走串联单向中值（先行后列），可去扫描线条纹。
    否则做普通二维矩形中值。bkgdmode=1 除法归一化、2 减法扣除（保持均值水平）。
    enhance_flag=1 时再叠一次 3×3 均值滤波轻微降噪。
    median_impl/n_threads 透传给 apply_superbkgd，不影响数值结果。
    """
    fitsfile = Path(fitsfile)
    out_file = Path(out_file)
    _log.info(f"  处理: {fitsfile.name}")
    data, header = read_fits(str(fitsfile))

    bkgd0, sigma0 = calculate_background(data)
    _log.info(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    if med_length == 1 or med_width == 1:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode,
                                    median_impl=median_impl, n_threads=n_threads)
        b, s = calculate_background(processed)
        _log.info(f"    第一次滤波后背景/sigma: {b:.3f} / {s:.3f}")

        processed = apply_superbkgd(processed, bkgd0, med_width, med_length, bkgdmode,
                                    median_impl=median_impl, n_threads=n_threads)
        b, s = calculate_background(processed)
        _log.info(f"    第二次滤波后背景/sigma: {b:.3f} / {s:.3f}")
    else:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode,
                                    median_impl=median_impl, n_threads=n_threads)
        b, s = calculate_background(processed)
        _log.info(f"    滤波后背景/sigma: {b:.3f} / {s:.3f}")

    if enhance_flag == 1:
        processed = apply_smooth(processed)
        b, s = calculate_background(processed)
        _log.info(f"    3×3 均值滤波后背景/sigma: {b:.3f} / {s:.3f}")

    write_fits(str(out_file), processed, header)
    _log.info(f"    已写出 --> {out_file.name}")


def _process_homomorphic(fitsfile, out_file, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5):
    fitsfile = Path(fitsfile)
    out_file = Path(out_file)
    _log.info(f"  处理（同态滤波）: {fitsfile.name}")
    data, header = read_fits(str(fitsfile))
    bkgd0, sigma0 = calculate_background(data)
    _log.info(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    filtered = homomorphic_filter(data, gamma_low, gamma_high, cutoff, c)

    bkgd, sigma = calculate_background(filtered)
    _log.info(f"    同态滤波后背景/sigma: {bkgd:.3f} / {sigma:.3f}")

    write_fits(str(out_file), filtered, header)
    _log.info(f"    已写出 --> {out_file.name}")


def _process_retinex(fitsfile, out_file, d=15):
    fitsfile = Path(fitsfile)
    out_file = Path(out_file)
    _log.info(f"  处理（Retinex）: {fitsfile.name}")
    data, header = read_fits(str(fitsfile))
    bkgd0, sigma0 = calculate_background(data)
    _log.info(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    reflectance, _illum = bilateral_retinex(data, d)
    final = cv2.GaussianBlur(reflectance.astype(np.float32), (9, 9), 0).astype(np.float64)

    bkgd, sigma = calculate_background(final)
    _log.info(f"    Retinex 后背景/sigma: {bkgd:.3f} / {sigma:.3f}")

    write_fits(str(out_file), final, header)
    _log.info(f"    已写出 --> {out_file.name}")


def _worker(mode, fitsfile, kwargs):
    """子进程入口：捕获子进程内的日志输出，由主进程统一回放。

    在 redirect_stdout 作用域内先重建 stdout-only logger（StreamHandler 会绑定
    当前 sys.stdout，也就是 buf），从而把子进程的 _log.info(...) 写入 buf。
    """
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            setup_logging(log_file=None)
            if mode == 1:
                _process_one(fitsfile, **kwargs)
            elif mode == 2:
                _process_homomorphic(fitsfile, **kwargs)
            elif mode == 3:
                _process_retinex(fitsfile, **kwargs)
    except Exception as exc:
        buf.write(f"  错误：{os.path.basename(str(fitsfile))}: {exc!r}\n")
        return buf.getvalue(), exc
    return buf.getvalue(), None


def _resolve_parallel(median_impl_cfg, n_files):
    """根据文件数与 CPU 核数自动选并发参数。

    返回 (n_workers, resolved_impl, n_threads)：
      - n_workers = min(文件数, CPU)
      - median_impl="auto" 解析为 "scipy_threaded"
      - 仅当 impl="scipy_threaded" 时 n_threads = max(1, CPU // n_workers)
    """
    cpu = os.cpu_count() or 1
    n_workers = max(1, min(n_files, cpu))
    resolved = "scipy_threaded" if median_impl_cfg == "auto" else median_impl_cfg
    if resolved == "scipy_threaded":
        n_threads = max(1, cpu // n_workers)
    else:
        n_threads = 1
    return n_workers, resolved, n_threads


def _emit(log_text):
    """把 worker 捕获的多行文本逐行交回主进程 logger，去掉末尾换行。"""
    for line in log_text.splitlines():
        _log.info(line)


def run_pre(config, fitspath_list):
    """对每个观测目录执行超级背景预处理；产物落到同日 fits_n/。

    superflag: 0=跳过，1=中值滤波，2=同态滤波，3=Retinex
    """
    pre = config.pre
    result = StepResult("pre")
    n = len(fitspath_list)
    for idx, fitspath in enumerate(fitspath_list, 1):
        fitspath = Path(fitspath)

        _log.info(f"\n{'=' * 20} [ {idx}/{n} ] {'=' * 20}")
        _log.info(f"路径: {fitspath}")

        if not fitspath.is_dir():
            _log.info("警告：目录不存在，跳过。")
            result.warnings.append(f"pre: 目录不存在 {fitspath}")
            result.failed_items.append(str(fitspath))
            continue

        science_files = list_fits(fitspath)
        if not science_files:
            _log.info("未找到 .fit 文件，跳过。")
            result.warnings.append(f"pre: 未发现 .fit {fitspath}")
            continue
        _log.info(f"扫描到原始 .fit 共 {len(science_files)} 个。")

        if pre.superflag == 0:
            _log.info("superflag=0，跳过图像处理。")
            result.warnings.append(f"pre: superflag=0 跳过 {fitspath}")
            continue

        pre_dir = ensure_dir(stage_dirs(fitspath)[PRE_DIR])
        clean_pre_dir(fitspath)

        mode_name = {1: "中值滤波", 2: "同态滤波", 3: "Retinex"}.get(pre.superflag, "未知")
        _log.info(f"--- 进入 super 模式（{mode_name}）→ {pre_dir} ---")

        n_workers, resolved_impl, n_threads = _resolve_parallel(
            pre.median_impl, len(science_files)
        )
        if pre.superflag == 1:
            _log.info(
                f"--- 并行：n_workers={n_workers}, median_impl={resolved_impl}, "
                f"threads_per_worker={n_threads} ---"
            )
        else:
            _log.info(f"--- 并行：n_workers={n_workers} ---")

        tasks = []
        for fitsfile in science_files:
            out_file = pre_path(fitspath, fitsfile.name)
            if pre.superflag == 1:
                kwargs = dict(
                    med_length=pre.med_length,
                    med_width=pre.med_width,
                    bkgdmode=pre.bkgdmode,
                    enhance_flag=pre.enhance_flag,
                    out_file=str(out_file),
                    median_impl=resolved_impl,
                    n_threads=n_threads,
                )
                tasks.append((1, str(fitsfile), kwargs))
            elif pre.superflag == 2:
                tasks.append((2, str(fitsfile), dict(out_file=str(out_file))))
            elif pre.superflag == 3:
                tasks.append((3, str(fitsfile), dict(out_file=str(out_file))))

        # 单文件或 n_workers<=1 直接串行，免去进程启动开销
        if n_workers <= 1 or len(tasks) <= 1:
            for mode, fitsfile, kwargs in tasks:
                log_text, err = _worker(mode, fitsfile, kwargs)
                _emit(log_text)
                if err is not None:
                    raise err
        else:
            with ProcessPoolExecutor(max_workers=n_workers) as ex:
                futures = [ex.submit(_worker, *t) for t in tasks]
                # 按提交顺序回放，保证文件处理顺序与日志可读
                for fut in futures:
                    log_text, err = fut.result()
                    _emit(log_text)
                    if err is not None:
                        raise err

        result.output_files.extend(str(p) for p in sorted(pre_dir.glob("*_n.fit")))

    _log.info(f"\n{'=' * 50}")
    _log.info(f"01pre 完成，共处理 {n} 个观测目录。")
    return result
