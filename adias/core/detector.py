"""02detect：连通域 + 修正矩星象检测。

原始 .fit 来自 fits/，预处理图来自 fits_n/，检测产物 *.fit.reg 落到同日
fits_reg/ 子目录。
"""

from pathlib import Path

from adias.application.log import get_logger
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


def run_detect(config, fitspath_list):
    """对每个观测目录的所有原始 .fit 执行星象检测。

    superflag != 0 时读 fits_n/ 下的预处理图；否则读原始 .fit。
    输出 DS9 region 写到 fits_reg/。
    """
    pre = config.pre
    detect = config.detect
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

        n_processed = 0
        for fitsfile_path in fits_files:
            n_processed += 1
            _log.info(f"\n  {n_processed:04d}-{fitsfile_path.name}")

            # 按 superflag 选择输入：预处理图来自 fits_n/，否则用原始 .fit
            if pre.superflag != 0:
                input_name = f"{fitsfile_path.stem}_n{fitsfile_path.suffix}"
                input_path = pre_input_dir / input_name
                _log.info(f"    使用预处理图像: {input_name}")
            else:
                input_path = fitsfile_path
                _log.info("    使用原始图像。")

            if not input_path.exists():
                _log.info(f"    错误：文件不存在 -> {input_path}")
                result.warnings.append(f"detect: 输入缺失 {input_path}")
                result.failed_items.append(str(input_path))
                continue

            # 读取 BITPIX 用于动态计算饱和阈值 maxflux=2**bitpix-1
            data, header = read_fits(str(input_path))
            bitpix = int(header.get("BITPIX", 16))
            raw_stars, bkgd, bkgdsigma = detect_stars_by_moments(
                data,
                detect.bkgd_threshold,
                detect.pos_method,
                bitpix,
                connectivity=detect.connectivity,
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
                detect.snr_threshold,
            )

            _log.info(f"    图像背景/sigma: {bkgd:10.3f} / {bkgdsigma:10.3f}")
            _log.info(f"    满足条件的星数: {n_out:4d}")

        _log.info(f"\n    共检测图像：{n_processed} 幅，reg 写入 {reg_out_dir}")
        result.output_files.extend(str(p) for p in sorted(reg_out_dir.glob("*.fit.reg")))

    _log.info(f"\n{'=' * 50}")
    _log.info("02detect 完成。")
    return result
