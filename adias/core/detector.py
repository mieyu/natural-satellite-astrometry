"""02detect：连通域 + 修正矩星象检测。

原始 .fit 来自 fits/，预处理图来自 fits_n/，检测产物 *.fit.reg 落到同日
fits_reg/ 子目录。

检测整体放进**一个全新 spawn 子进程**里串行执行：连通域标号依赖 numba
njit，而本环境（numba 0.65.0 + macOS）下，numba 一旦与 01pre 跑在同一个
长期存活的进程里，其 JIT 编译/执行会间歇段错误（即便主线程串行）；而单独
的全新进程跑检测则始终稳定。子进程内逐帧日志先写入 buffer，结束后整段交回
主进程经 _log 回放，保证控制台输出与日志文件与历史一致。
"""

import io
import multiprocessing as mp
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


def _detect_one(
    fitsfile_str, pre_input_dir_str, fitspath_str, pre_superflag, detect_cfg, n_idx
):
    """单帧检测：返回 info_dict，并直接经 _log 输出日志。

    info_dict 键：reg_path、warning、failed_item、err。
    调用方根据这些字段累加 StepResult。
    """
    info = {"reg_path": None, "warning": None, "failed_item": None, "err": None}
    fitsfile_path = Path(fitsfile_str)
    pre_input_dir = Path(pre_input_dir_str)
    fitspath = Path(fitspath_str)
    try:
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
            return info

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
        _log.info(f"  错误：{fitsfile_path.name}: {exc!r}")
    return info


def _run_detect_serial(config, fitspath_list):
    """实际串行检测循环：逐日逐帧调用 _detect_one，汇总 StepResult。

    在隔离子进程内执行（见模块 docstring）；日志直接经 _log 输出。
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

        _log.info("--- 串行检测 ---")
        for n, fp in enumerate(fits_files):
            info = _detect_one(
                str(fp),
                str(pre_input_dir),
                str(fitspath),
                pre.superflag,
                detect_cfg,
                n + 1,
            )
            if info["err"] is not None:
                raise info["err"]
            if info["warning"]:
                result.warnings.append(info["warning"])
            if info["failed_item"]:
                result.failed_items.append(info["failed_item"])

        _log.info(f"\n    共检测图像：{len(fits_files)} 幅，reg 写入 {reg_out_dir}")
        result.output_files.extend(
            str(p)
            for p in sorted(
                list(reg_out_dir.glob("*.fit.reg"))
                + list(reg_out_dir.glob("*.fits.reg"))
            )
        )

    _log.info(f"\n{'=' * 50}")
    _log.info("02detect 完成。")
    return result


def _detect_subprocess_entry(config, fitspath_list):
    """子进程入口：捕获本进程日志到 buffer，返回 (log_text, StepResult)。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        setup_logging(log_file=None)
        result = _run_detect_serial(config, fitspath_list)
    return buf.getvalue(), result


def run_detect(config, fitspath_list):
    """对每个观测目录的所有原始 .fit 执行星象检测。

    superflag != 0 时读 fits_n/ 下的预处理图；否则读原始 .fit。
    输出 DS9 region 写到 fits_reg/。

    检测在一个全新 spawn 子进程内完成，以隔离 numba（见模块 docstring）；
    子进程捕获的日志整段交回，由主进程 _log 回放到控制台与日志文件。
    """
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=1) as pool:
        log_text, result = pool.apply(
            _detect_subprocess_entry, (config, fitspath_list)
        )
    for line in log_text.splitlines():
        _log.info(line)
    return result
