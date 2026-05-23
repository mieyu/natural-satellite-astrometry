"""01pre：超级背景预处理。

对每个观测目录扫描原始 .fit，按 superflag 选择算法（中值滤波 / 同态滤波 /
Retinex），结果落到同日 fits_n/ 子目录。
"""

import cv2
import numpy as np

from adias.application.log import get_logger
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


def _process_one(fitsfile, med_length, med_width, bkgdmode, enhance_flag, out_file):
    """单幅 FITS 的超级背景扣除。

    med_length 或 med_width 为 1 时走串联单向中值（先行后列），可去扫描线条纹。
    否则做普通二维矩形中值。bkgdmode=1 除法归一化、2 减法扣除（保持均值水平）。
    enhance_flag=1 时再叠一次 3×3 均值滤波轻微降噪。
    """
    _log.info(f"  处理: {fitsfile.name}")
    data, header = read_fits(str(fitsfile))

    bkgd0, sigma0 = calculate_background(data)
    _log.info(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    if med_length == 1 or med_width == 1:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = calculate_background(processed)
        _log.info(f"    第一次滤波后背景/sigma: {b:.3f} / {s:.3f}")

        processed = apply_superbkgd(processed, bkgd0, med_width, med_length, bkgdmode)
        b, s = calculate_background(processed)
        _log.info(f"    第二次滤波后背景/sigma: {b:.3f} / {s:.3f}")
    else:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = calculate_background(processed)
        _log.info(f"    滤波后背景/sigma: {b:.3f} / {s:.3f}")

    if enhance_flag == 1:
        processed = apply_smooth(processed)
        b, s = calculate_background(processed)
        _log.info(f"    3×3 均值滤波后背景/sigma: {b:.3f} / {s:.3f}")

    write_fits(str(out_file), processed, header)
    _log.info(f"    已写出 --> {out_file.name}")


def _process_homomorphic(fitsfile, out_file, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5):
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


def run_pre(config, fitspath_list):
    """对每个观测目录执行超级背景预处理；产物落到同日 fits_n/。

    superflag: 0=跳过，1=中值滤波，2=同态滤波，3=Retinex
    """
    pre = config.pre
    result = StepResult("pre")
    n = len(fitspath_list)
    for idx, fitspath in enumerate(fitspath_list, 1):
        from pathlib import Path
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

        for fitsfile in science_files:
            out_file = pre_path(fitspath, fitsfile.name)

            if pre.superflag == 1:
                _process_one(
                    fitsfile,
                    pre.med_length,
                    pre.med_width,
                    pre.bkgdmode,
                    pre.enhance_flag,
                    out_file,
                )
            elif pre.superflag == 2:
                _process_homomorphic(fitsfile, out_file)
            elif pre.superflag == 3:
                _process_retinex(fitsfile, out_file)

        result.output_files.extend(str(p) for p in sorted(pre_dir.glob("*_n.fit")))

    _log.info(f"\n{'=' * 50}")
    _log.info(f"01pre 完成，共处理 {n} 个观测目录。")
    return result
