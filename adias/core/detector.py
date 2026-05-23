"""02detect：连通域 + 修正矩星象检测。原始 .fit 来自 fits/，预处理图来自 fits_n/，
检测产物 *.fit.reg 落到同日 fits_reg/ 子目录。
"""

import glob
import os

from adias.adapters.region_adapter import write_detected_region
from adias.application.pipeline import StepResult
from adias.domain.models import DetectedStar
from adias.io.fits_io import read_fits
from adias.paths import (
    DETECT_DIR,
    PRE_DIR,
    ensure_dir,
    list_fits,
    reg_path,
    stage_dirs,
)
from adias.utils.image_utils import detect_stars_by_moments


def run_detect(config, fitspath_list):
    """对每个观测目录的所有原始 .fit 执行星象检测。

    superflag != 0 时读 fits_n/ 下的预处理图；否则读原始 .fit。
    输出 DS9 region 写到 fits_reg/。
    """
    result = StepResult("detect")
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n第 {idx:03d} 天 - fits 文件夹：{fitspath}")
        print("    ====================本日fits图像处理情况===================")

        fits_files = list_fits(fitspath)
        if not fits_files:
            print("    警告：未发现原始 .fit，跳过。")
            result.warnings.append(f"detect: 未发现 .fit {fitspath}")
            continue

        stages = stage_dirs(fitspath)
        reg_out_dir = ensure_dir(stages[DETECT_DIR])
        pre_input_dir = stages[PRE_DIR]

        n_processed = 0
        for fitsfile_path in fits_files:
            fitsfile0 = os.path.basename(fitsfile_path)
            n_processed += 1
            print(f"\n  {n_processed:04d}-{fitsfile0}")

            # 按 superflag 选择输入：预处理图来自 fits_n/，否则用原始 .fit
            if config["superflag"] != 0:
                base, ext = os.path.splitext(fitsfile0)
                input_name = f"{base}_n{ext}"
                input_path = os.path.join(pre_input_dir, input_name)
                print(f"    使用预处理图像: {input_name}")
            else:
                input_path = fitsfile_path
                print("    使用原始图像。")

            if not os.path.exists(input_path):
                print(f"    错误：文件不存在 -> {input_path}")
                result.warnings.append(f"detect: 输入缺失 {input_path}")
                result.failed_items.append(input_path)
                continue

            # 读取 BITPIX 用于动态计算饱和阈值 maxflux=2**bitpix-1
            data, header = read_fits(input_path)
            bitpix = int(header.get("BITPIX", 16))
            # 连通域算法可选：
            #   "fortran" 完全按 Fortran 三段式（含 nr=250 子区域合并）
            #   "scipy"   Python 标准 8 连通（更稳健，但与 Fortran 不完全等价）
            connectivity = config.get("connectivity", "fortran")
            raw_stars, bkgd, bkgdsigma = detect_stars_by_moments(
                data,
                config["bkgd_threshold"],
                config["pos_method"],
                bitpix,
                connectivity=connectivity,
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

            out_reg = reg_path(fitspath, fitsfile0)
            n_out = write_detected_region(
                out_reg, stars, bkgd, bkgdsigma, config["snr_threshold"]
            )

            print(f"    图像背景/sigma: {bkgd:10.3f} / {bkgdsigma:10.3f}")
            print(f"    满足条件的星数: {n_out:4d}")

        print(f"\n    共检测图像：{n_processed} 幅，reg 写入 {reg_out_dir}")
        result.output_files.extend(
            sorted(glob.glob(os.path.join(reg_out_dir, "*.fit.reg")))
        )

    print(f"\n{'=' * 50}")
    print("02detect 完成。")
    return result
