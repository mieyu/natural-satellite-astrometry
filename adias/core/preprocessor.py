# 01pre：超级背景预处理。逐幅 .fit 扣除背景后落到同日 fits_n/ 子目录。

import glob
import os

import cv2
import numpy as np

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


def _process_one(fitsfile, med_length, med_width, bkgdmode, enhance_flag, out_file):
    """单幅 FITS 的超级背景扣除。

    med_length 或 med_width 为 1 时走串联单向中值（先行后列），可去扫描线条纹。
    否则做普通二维矩形中值。bkgdmode=1 除法归一化、2 减法扣除（保持均值水平）。
    enhance_flag=1 时再叠一次 3×3 均值滤波轻微降噪。
    """
    print(f"  处理: {os.path.basename(fitsfile)}")
    data, header = read_fits(fitsfile)

    bkgd0, sigma0 = calculate_background(data)
    print(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    if med_length == 1 or med_width == 1:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = calculate_background(processed)
        print(f"    第一次滤波后背景/sigma: {b:.3f} / {s:.3f}")

        processed = apply_superbkgd(processed, bkgd0, med_width, med_length, bkgdmode)
        b, s = calculate_background(processed)
        print(f"    第二次滤波后背景/sigma: {b:.3f} / {s:.3f}")
    else:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = calculate_background(processed)
        print(f"    滤波后背景/sigma: {b:.3f} / {s:.3f}")

    if enhance_flag == 1:
        processed = apply_smooth(processed)
        b, s = calculate_background(processed)
        print(f"    3×3 均值滤波后背景/sigma: {b:.3f} / {s:.3f}")

    write_fits(out_file, processed, header)
    print(f"    已写出 --> {os.path.basename(out_file)}")


def _process_homomorphic(
    fitsfile, out_file, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5
):
    print(f"  处理（同态滤波）: {os.path.basename(fitsfile)}")
    data, header = read_fits(fitsfile)
    bkgd0, sigma0 = calculate_background(data)
    print(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    filtered = homomorphic_filter(data, gamma_low, gamma_high, cutoff, c)

    bkgd, sigma = calculate_background(filtered)
    print(f"    同态滤波后背景/sigma: {bkgd:.3f} / {sigma:.3f}")

    write_fits(out_file, filtered, header)
    print(f"    已写出 --> {os.path.basename(out_file)}")


def _process_retinex(fitsfile, out_file, d=15):
    print(f"  处理（Retinex）: {os.path.basename(fitsfile)}")
    data, header = read_fits(fitsfile)
    bkgd0, sigma0 = calculate_background(data)
    print(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    reflectance, _illum = bilateral_retinex(data, d)
    final = cv2.GaussianBlur(reflectance.astype(np.float32), (9, 9), 0).astype(np.float64)

    bkgd, sigma = calculate_background(final)
    print(f"    Retinex 后背景/sigma: {bkgd:.3f} / {sigma:.3f}")

    write_fits(out_file, final, header)
    print(f"    已写出 --> {os.path.basename(out_file)}")


def run_pre(config, fitspath_list):
    """对每个观测目录执行超级背景预处理；产物落到同日 fits_n/。

    superflag: 0=跳过，1=中值滤波，2=同态滤波，3=Retinex
    """
    result = StepResult("pre")
    n = len(fitspath_list)
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n{'=' * 20} [ {idx}/{n} ] {'=' * 20}")
        print(f"路径: {fitspath}")

        if not os.path.isdir(fitspath):
            print("警告：目录不存在，跳过。")
            result.warnings.append(f"pre: 目录不存在 {fitspath}")
            result.failed_items.append(fitspath)
            continue

        science_files = list_fits(fitspath)
        if not science_files:
            print("未找到 .fit 文件，跳过。")
            result.warnings.append(f"pre: 未发现 .fit {fitspath}")
            continue
        print(f"扫描到原始 .fit 共 {len(science_files)} 个。")

        if config["superflag"] == 0:
            print("superflag=0，跳过图像处理。")
            result.warnings.append(f"pre: superflag=0 跳过 {fitspath}")
            continue

        pre_dir = ensure_dir(stage_dirs(fitspath)[PRE_DIR])
        clean_pre_dir(fitspath)

        mode_name = {1: "中值滤波", 2: "同态滤波", 3: "Retinex"}.get(
            config["superflag"], "未知"
        )
        print(f"--- 进入 super 模式（{mode_name}）→ {pre_dir} ---")

        for fitsfile in science_files:
            out_file = pre_path(fitspath, os.path.basename(fitsfile))

            if config["superflag"] == 1:
                _process_one(
                    fitsfile,
                    config["med_length"],
                    config["med_width"],
                    config["bkgdmode"],
                    config["enhance_flag"],
                    out_file,
                )
            elif config["superflag"] == 2:
                _process_homomorphic(fitsfile, out_file)
            elif config["superflag"] == 3:
                _process_retinex(fitsfile, out_file)

        result.output_files.extend(sorted(glob.glob(os.path.join(pre_dir, "*_n.fit"))))

    print(f"\n{'=' * 50}")
    print(f"01pre 完成，共处理 {n} 个观测目录。")
    return result
