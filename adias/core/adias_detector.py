# 功能：02detect 星象检测批处理逻辑。
# 使用：from adias.core.adias_detector import run_detect

import os

from adias.io.adias_fits_io import read_fits
from adias.io.adias_text_io import read_fits_list, write_reg_file
from adias.utils.adias_image_utils import detect_stars_by_moments


def run_detect(config, fitspath_list):
    """
    对 fitspath_list 中每个观测目录执行星象检测，输出 .reg 文件。

    流程
    ----
    1. 读取 fits.lst 获取文件列表
    2. 按 superflag 决定使用原始图像还是 *_n.fit
    3. 逐幅调用 detect_stars_by_moments 检测星象
    4. 调用 write_reg_file 写出 DS9 region 文件

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    fitspath_list : list[str]，观测目录路径列表
    """
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n第 {idx:03d} 天 - fits 文件夹：{fitspath}")
        print("    ====================本日fits图像处理情况===================")

        fits_files = read_fits_list(fitspath)
        if not fits_files:
            print(f"    警告：未找到 fits.lst，跳过。")
            continue

        n_processed = 0
        for fitsfile_path in fits_files:
            fitsfile0 = os.path.basename(fitsfile_path)
            n_processed += 1
            print(f"\n  {n_processed:04d}-{fitsfile0}")

            # 按 superflag 选择输入文件
            if config["superflag"] != 0:
                base, ext = os.path.splitext(fitsfile0)
                input_name = base + "_n" + ext
                print(f"    使用预处理图像: {input_name}")
            else:
                input_name = fitsfile0
                print("    使用原始图像。")

            input_path = os.path.join(fitspath, input_name)
            if not os.path.exists(input_path):
                print(f"    错误：文件不存在 -> {input_path}")
                continue

            # 读取图像并检测
            # [差异4] 保留 header 以读取 BITPIX，用于动态计算饱和阈值 maxflux=2**bitpix-1
            data, header = read_fits(input_path)
            bitpix = int(header.get("BITPIX", 16))
            stars, bkgd, bkgdsigma = detect_stars_by_moments(
                data,
                config["bkgd_threshold"],
                config["pos_method"],
                bitpix,
            )

            # 写出 reg 文件（以原始文件名为基础命名）
            reg_path = os.path.join(fitspath, fitsfile0 + ".reg")
            n_out = write_reg_file(
                reg_path, stars, bkgd, bkgdsigma, config["snr_threshold"]
            )

            print(f"    图像背景/sigma: {bkgd:10.3f} / {bkgdsigma:10.3f}")
            print(f"    满足条件的星数: {n_out:4d}")

        print(f"\n    共检测图像：{n_processed} 幅，reg 文件已写出。")

    print(f"\n{'=' * 50}")
    print("02detect 完成。")
