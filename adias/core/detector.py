"""02detect：连通域 + 修正矩星象检测。

原始 .fit 来自 fits/，预处理图来自 fits_n/，检测产物 *.fit.reg 落到同日
fits_reg/ 子目录。

并发模型与 01pre 一致：ProcessPoolExecutor 文件级并发，子进程内
redirect_stdout 捕获日志，主进程按提交顺序回放。
"""

import io
import os
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path

from adias.application.log import get_logger, setup_logging
from adias.application.pipeline import StepResult
from adias.domain.models import DetectedStar
from adias.io.fits_io import read_fits
from adias.io.text_io import write_reg_file
from adias.paths import (
    DETECT_DIR,
    PRE_DIR,
    ensure_dir,
    list_fits,
    reg_path,
    stage_dirs,
)
from adias.utils.image_utils import detect_stars_by_moments

_log = get_logger("detect")


def _stars_to_reg_dicts(stars):
    """DetectedStar 列表 → write_reg_file 期望的 dict 列表。"""
    return [
        {
            "starx": s.x,
            "stary": s.y,
            "sumi": s.flux,
            "snr": s.snr,
            "star_id": s.star_id,
            "star_pix": s.pixel_count,
            "overflag": 1 if s.saturated else 0,
        }
        for s in stars
    ]


def _detect_one(fitsfile_str, pre_input_dir_str, fitspath_str,
                pre_superflag, detect_cfg, n_idx):
    """单帧检测：返回 (log_text, info_dict)。

    info_dict 键：reg_path、warning、failed_item、err。
    主进程根据这些字段累加 StepResult。
    """
    buf = io.StringIO()
    info = {"reg_path": None, "warning": None, "failed_item": None, "err": None}
    fitsfile_path = Path(fitsfile_str)
    pre_input_dir = Path(pre_input_dir_str)
    fitspath = Path(fitspath_str)
    try:
        with redirect_stdout(buf):
            setup_logging(log_file=None)
            _log.info(f"\n  {n_idx:04d}-{fitsfile_path.name}")

            if pre_superflag != 0:
                input_name = f"{fitsfile_path.stem}_n{fitsfile_path.suffix}"
                input_path = pre_input_dir / input_name
                _log.info(f"    使用预处理图像: {input_name}")
            else:
                input_path = fitsfile_path
                _log.info("    使用原始图像。")

            if not input_path.exists():
                _log.info(f"    错误：文件不存在 -> {input_path}")
                info["warning"] = f"detect: 输入缺失 {input_path}"
                info["failed_item"] = str(input_path)
                return buf.getvalue(), info

            data, header = read_fits(str(input_path))
            bitpix = int(header.get("BITPIX", 16))
            raw_stars, bkgd, bkgdsigma = detect_stars_by_moments(
                data,
                detect_cfg["bkgd_threshold"],
                detect_cfg["pos_method"],
                bitpix,
                connectivity=detect_cfg["connectivity"],
            )

            stars = [
                DetectedStar(
                    x=s["starx"],
                    y=s["stary"],
                    flux=s["sumi"],
                    snr=s["snr"],
                    star_id=s["star_id"],
                    pixel_count=s["star_pix"],
                    saturated=s["overflag"] >= 1,
                )
                for s in raw_stars
            ]

            out_reg = reg_path(fitspath, fitsfile_path.name)
            n_out = write_reg_file(
                str(out_reg),
                _stars_to_reg_dicts(stars),
                bkgd,
                bkgdsigma,
                detect_cfg["snr_threshold"],
            )
            info["reg_path"] = str(out_reg)
            _log.info(f"    图像背景/sigma: {bkgd:10.3f} / {bkgdsigma:10.3f}")
            _log.info(f"    满足条件的星数: {n_out:4d}")
    except Exception as exc:
        info["err"] = exc
        buf.write(f"  错误：{fitsfile_path.name}: {exc!r}\n")
    return buf.getvalue(), info


def _emit(log_text):
    """worker 捕获的多行文本逐行交回主进程 logger。"""
    for line in log_text.splitlines():
        _log.info(line)


def run_detect(config, fitspath_list):
    """对每个观测目录的所有原始 .fit 执行星象检测。

    superflag != 0 时读 fits_n/ 下的预处理图；否则读原始 .fit。
    输出 DS9 region 写到 fits_reg/。
    """
    pre = config.pre
    detect = config.detect
    detect_cfg = {
        "bkgd_threshold": detect.bkgd_threshold,
        "snr_threshold": detect.snr_threshold,
        "pos_method": detect.pos_method,
        "connectivity": detect.connectivity,
    }
    result = StepResult("detect")
    for idx, fitspath in enumerate(fitspath_list, 1):
        fitspath = Path(fitspath)
        _log.info(f"\n第 {idx:03d} 天 - fits 文件夹：{fitspath}")
        _log.info("    ====================本日fits图像处理情况===================")

        fits_files = list_fits(fitspath)
        if not fits_files:
            _log.info("    警告：未发现原始 .fit，跳过。")
            result.warnings.append(f"detect: 未发现 .fit {fitspath}")
            continue

        stages = stage_dirs(fitspath)
        reg_out_dir = ensure_dir(stages[DETECT_DIR])
        pre_input_dir = stages[PRE_DIR]

        cpu = os.cpu_count() or 1
        n_workers = max(1, min(len(fits_files), cpu))
        _log.info(f"--- 并行：n_workers={n_workers} ---")

        tasks = [
            (str(fp), str(pre_input_dir), str(fitspath), pre.superflag, detect_cfg, n + 1)
            for n, fp in enumerate(fits_files)
        ]

        # 单文件或 n_workers<=1 直接串行，免去进程启动开销
        if n_workers <= 1 or len(tasks) <= 1:
            for t in tasks:
                log_text, info = _detect_one(*t)
                _emit(log_text)
                if info["err"] is not None:
                    raise info["err"]
                if info["warning"]:
                    result.warnings.append(info["warning"])
                if info["failed_item"]:
                    result.failed_items.append(info["failed_item"])
        else:
            with ProcessPoolExecutor(max_workers=n_workers) as ex:
                futures = [ex.submit(_detect_one, *t) for t in tasks]
                for fut in futures:
                    log_text, info = fut.result()
                    _emit(log_text)
                    if info["err"] is not None:
                        raise info["err"]
                    if info["warning"]:
                        result.warnings.append(info["warning"])
                    if info["failed_item"]:
                        result.failed_items.append(info["failed_item"])

        _log.info(f"\n    共检测图像：{len(fits_files)} 幅，reg 写入 {reg_out_dir}")
        result.output_files.extend(str(p) for p in sorted(reg_out_dir.glob("*.fit.reg")))

    _log.info(f"\n{'=' * 50}")
    _log.info("02detect 完成。")
    return result
