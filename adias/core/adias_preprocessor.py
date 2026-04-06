# 功能：01pre 超级背景预处理逻辑。
# 使用：from adias.core.preprocessor import run_pre

import os

from adias.io.adias_fits_io  import read_fits, write_fits
from adias.io.adias_text_io  import read_fits_list, write_fits_list, clean_old_files
from adias.utils.adias_image_utils import cal_b, apply_superbkgd, apply_smooth


def _process_one(fitsfile, med_length, med_width, bkgdmode, enhance_flag, out_file):
    """
    对单幅 FITS 图像执行超级背景扣除。

    逻辑说明
    --------
    - med_length==1 或 med_width==1：串联单向中值滤波，
      先行方向再列方向，用于去除扫描线/条纹噪声。
    - 否则：普通二维矩形中值滤波。
    - bkgdmode=1 除法归一化；bkgdmode=2 减法扣除（保持均值水平）。
    - enhance_flag=1：额外做一次 3×3 均值滤波轻微降噪。
    """
    print(f"  处理: {os.path.basename(fitsfile)}")
    data, header = read_fits(fitsfile)

    bkgd0, sigma0 = cal_b(data)
    print(f"    预处理前背景/sigma: {bkgd0:.3f} / {sigma0:.3f}")

    if med_length == 1 or med_width == 1:
        # 第一次滤波（原始参数方向）
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = cal_b(processed)
        print(f"    第一次滤波后背景/sigma: {b:.3f} / {s:.3f}")

        # 第二次滤波（交换 length/width，处理另一方向）
        processed = apply_superbkgd(processed, bkgd0, med_width, med_length, bkgdmode)
        b, s = cal_b(processed)
        print(f"    第二次滤波后背景/sigma: {b:.3f} / {s:.3f}")
    else:
        processed = apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode)
        b, s = cal_b(processed)
        print(f"    滤波后背景/sigma: {b:.3f} / {s:.3f}")

    if enhance_flag == 1:
        processed = apply_smooth(processed)
        b, s = cal_b(processed)
        print(f"    3×3 均值滤波后背景/sigma: {b:.3f} / {s:.3f}")

    write_fits(out_file, processed, header)
    print(f"    已写出 --> {os.path.basename(out_file)}")


def run_pre(config, fitspath_list):
    """
    对 fitspath_list 中每个观测目录执行超级背景预处理。

    流程
    ----
    1. 清理旧的 *_n.fit 和 *.lst
    2. 扫描原始 .fit 并生成 fits.lst
    3. 若 superflag==1，逐幅调用 _process_one

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    fitspath_list : list[str]，观测目录路径列表
    """
    n = len(fitspath_list)
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n{'=' * 20} [ {idx}/{n} ] {'=' * 20}")
        print(f"路径: {fitspath}")

        if not os.path.isdir(fitspath):
            print(f"警告：目录不存在，跳过。")
            continue

        clean_old_files(fitspath)
        science_files = write_fits_list(fitspath)

        if not science_files:
            print("未找到 .fit 文件，跳过。")
            continue

        if config['superflag'] != 1:
            print("superflag=0，仅生成文件列表，跳过图像处理。")
            continue

        print("--- 进入 super 模式 ---")
        for fitsfile in science_files:
            base, ext = os.path.splitext(fitsfile)
            _process_one(
                fitsfile,
                config['med_length'],
                config['med_width'],
                config['bkgdmode'],
                config['enhance_flag'],
                f"{base}_n{ext}",
            )

    print(f"\n{'=' * 50}")
    print(f"01pre 完成，共处理 {n} 个观测目录。")