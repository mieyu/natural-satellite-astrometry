# **********************************CCD 图像预处理（Super Background 模式）*************************************
# program name: 01pre.py
#
# function:
#   1）从 fitspath.in 中读取每天观测数据的 FITS 目录，生成 fits.lst 文件列表（供后续 02match/03match 使用）。
#   2）预处理模式：仅实现“超级背景修正”（对应 Fortran 版 01pre.f90 中 super_flat=1 的分支）：
#       - 对原始科学图像执行一维/二维中值滤波生成超级背景（Super Background）；
#       - 根据 bkgdmode 选择除法或减法方式扣除背景，并恢复全场平均背景水平；
#       - 可选地使用 3×3 均值滤波进行轻微图像增强（降噪和平滑）。
#   3）输出经超级背景修正后的图像 *_n.fit，保留原始头信息。
#
# input:
#   0）主路径配置文件 fitspath.in：
#       每一行给出一个观测日期对应的科学图像目录绝对路径（例如：F:\000obs\SHAO\200609\20060918\fits）。
#   1）预处理配置文件 adias.cfg（本脚本仅使用与超级背景相关的参数）：
#       1.1）1biasflag      % 是否使用 bias 修正（目前解析但未在本脚本中实际使用）
#       1.2）1darkflag      % 是否使用 dark 修正（目前解析但未在本脚本中实际使用）
#       1.3）1flatflag      % 是否使用 flat 修正（目前解析但未在本脚本中实际使用）
#       1.4）1superflag     % 是否启用超级背景修正（1=启用，0=跳过，仅生成列表）
#       1.5）1med_length    % 中值滤波窗口长度（列方向）
#       1.6）1med_width     % 中值滤波窗口宽度（行方向）
#       1.7）1bkgdmode      % 超级背景扣除模式（1=除法归一化；2=减法扣除）
#       1.8）1enhance_flag  % 是否启用 3×3 均值滤波增强（1=启用，0=关闭）
#
# output:
#   1）每个观测目录下的 fits.lst 文件：按行列出所有待处理的科学 .fit 图像路径。
#   2）经超级背景预处理后的图像文件：对每个原始 a.fit 生成 a_n.fit，保存在原目录中。
#
# 主要函数/子程序：
#   1）parse_config(config_path)
#           解析 adias.cfg，提取 bias/dark/flat/super 以及中值滤波、背景模式等参数，并提供默认值保护。
#   2）cal_b(data, sigma_factor, max_iter, convergence)
#           采用迭代 sigma-clipping 计算图像背景均值和 sigma，剔除恒星、宇宙线等高亮像素的影响。
#   3）fits_superbkgd_pro(fitsfile, med_length, med_width, bkgdmode, enhance_flag, nfitsfile)
#           对单幅 FITS 图像执行一维/二维中值滤波生成超级背景，按 bkgdmode 扣除背景并可选做 3×3 均值增强，最终写出 *_n.fit。
#   4）main()
#           读取 fitspath.in 中的观测路径，生成各日的 fits.lst 文件，并在 superflag=1 时批量调用 fits_superbkgd_pro 完成预处理。
#
# 版本信息：
#   V1.0 by zhy 2020.12.10
#   V2.0 by zhy 2024.9.30  程序中间输出中文化
#   V3.0 by lhy 2025.12.05 程序改写成python
# ************************************************************************************************

import glob
import os
import time

# 引入警告模块，忽略非标准的FITS头文件警告，防止控制台输出过多干扰信息
import warnings

import numpy as np
from astropy.io import fits
from astropy.utils.exceptions import AstropyWarning
from scipy.ndimage import median_filter, uniform_filter

warnings.filterwarnings("ignore", category=AstropyWarning)


def parse_config(config_path="adias.cfg"):
    """
    解析配置文件 adias.cfg。
    该函数会跳过注释行，解析形如 '1med_width = 25' 的参数，
    并将其映射为程序内部使用的变量名（如 'med_width'）。
    """
    # 默认参数字典，防止配置文件缺失时程序崩溃
    params = {
        "biasflag": 0,
        "darkflag": 0,
        "flatflag": 0,
        "superflag": 0,
        "med_length": 1,
        "med_width": 25,
        "bkgdmode": 2,
        "enhance_flag": 1,
    }

    if not os.path.exists(config_path):
        print(f"警告：配置文件 '{config_path}' 未找到，将使用默认参数。")
        return params

    # 使用 utf-8-sig 编码读取，防止Windows记事本BOM头导致的解析错误
    with open(config_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和以 !, ;, #, [ 开头的注释行
            if not line or line.startswith(("!", ";", "#", "[")):
                continue
            if "=" in line:
                key_part, value_part = line.split("=", 1)
                key = key_part.strip()
                # 去除值后面的注释（即 % 之后的内容）
                value = value_part.split("%")[0].strip()

                # 定义配置文件中的键名到程序变量名的映射表
                key_map = {
                    "1biasflag": "biasflag",
                    "1darkflag": "darkflag",
                    "1flatflag": "flatflag",
                    "1superflag": "superflag",
                    "1med_length": "med_length",
                    "1med_width": "med_width",
                    "1bkgdmode": "bkgdmode",
                    "1enhance_flag": "enhance_flag",
                }

                if key in key_map and value:
                    try:
                        params[key_map[key]] = int(value)
                    except ValueError:
                        print(f"警告: 无法解析配置项 {key}={value}")
    return params


def cal_b(data, sigma_factor=2.6, max_iter=10, convergence=0.01):
    """
    计算图像背景均值(avervalue)和标准差(sigma)。
    【算法说明】采用迭代 Sigma-Clipping 算法：
    1. 初步计算均值和sigma。
    2. 剔除偏离均值超过 2.6倍 sigma 的像素点（剔除亮星或宇宙线）。
    3. 重新计算剩余像素的均值和sigma。
    4. 重复直到sigma收敛或达到最大迭代次数。
    此逻辑严格对齐 Fortran 原版 cal_b 子程序。
    """
    flat_data = data.flatten().astype(np.float64)
    npx = len(flat_data)
    if npx < 2:
        return np.mean(flat_data) if npx > 0 else 0, 0

    avervalue = np.mean(flat_data)
    # 使用手动计算标准差公式 (sum((x-mean)^2) / (N-1)) 以匹配 Fortran 精度
    sumvalue2 = np.sum((flat_data - avervalue) ** 2)
    sigma = np.sqrt(sumvalue2 / (npx - 1))

    for _ in range(max_iter):
        old_sigma = sigma
        # 创建掩膜，保留正常范围内的像素
        mask = np.abs(flat_data - avervalue) <= sigma_factor * sigma
        clipped_data = flat_data[mask]
        k = len(clipped_data)
        if k < 2:
            break

        avervalue2 = np.mean(clipped_data)
        sumvalue2_new = np.sum((clipped_data - avervalue2) ** 2)
        sigma2 = np.sqrt(sumvalue2_new / (k - 1))

        # 判断收敛条件：sigma几乎不变或变化率小于1%
        if sigma2 <= 1e-6 or np.abs(sigma2 - old_sigma) < convergence * old_sigma:
            avervalue = avervalue2
            sigma = sigma2
            break
        avervalue = avervalue2
        sigma = sigma2
    return avervalue, sigma


def fits_superbkgd_pro(
    fitsfile, med_length, med_width, bkgdmode, enhance_flag, nfitsfile
):
    """
    核心处理函数：执行超级背景(Super Background)扣除。
    【逻辑说明】
    如果 med_length 或 med_width 为1，则执行特殊的“串联滤波”：
    先在一个方向做中值滤波并扣除，再在另一个方向做中值滤波并扣除。
    这通常用于去除 CCD 图像中的扫描线或条纹噪声。
    """
    print(f"--- 开始处理文件: {os.path.basename(fitsfile)} ---")
    with fits.open(fitsfile, ignore_missing_end=True) as hdul:
        original_data = hdul[0].data.astype(np.float64)
        header = hdul[0].header

    # 计算原始图像的背景统计量
    bkgd0, sigma0 = cal_b(original_data)
    print(f"预处理前图像背景及sigma: {bkgd0:.3f}, {sigma0:.3f}")

    processed_data = original_data.copy()

    # --- 特殊逻辑：单向/串联中值滤波 (对应 Fortran 中的核心去背景算法) ---
    if med_length == 1 or med_width == 1:
        # 步骤 1: 第一次滤波 (通常是宽方向)
        print(f"第一次~中值滤波窗口(length,width): {med_length}, {med_width}")
        # 构造滤波核：例如 (25, 1) 表示一行一行地滤波
        kernel1 = (med_width, 1) if med_width > 1 else (1, med_length)
        background1 = median_filter(original_data, size=kernel1)

        # 模式1: 除法归一化; 模式2: 减法扣除 (通常用模式2)
        if bkgdmode == 1:
            processed_data = original_data / background1 * bkgd0
        else:  # bkgdmode == 2
            processed_data = original_data - background1 + bkgd0

        # 中间检查
        bkgd, sigma = cal_b(processed_data)
        print(f"第一次滤波后的图像背景及sigma: {bkgd:.3f}, {sigma:.3f}")

        # 步骤 2: 第二次滤波 (交换长宽，处理另一个方向)
        med_length0, med_width0 = med_width, med_length  # 交换窗口参数
        print(f"第二次~中值滤波窗口(length,width): {med_length0}, {med_width0}")
        kernel2 = (med_width0, 1) if med_width0 > 1 else (1, med_length0)

        # 注意：是在第一次处理后的数据 processed_data 上继续操作
        background2 = median_filter(processed_data, size=kernel2)

        if bkgdmode == 1:
            processed_data = processed_data / background2 * bkgd0
        else:  # bkgdmode == 2
            processed_data = processed_data - background2 + bkgd0

        bkgd, sigma = cal_b(processed_data)
        print(f"第二次滤波后的图像背景及sigma: {bkgd:.3f}, {sigma:.3f}")

    else:
        # --- 常规逻辑：矩形块状中值滤波 ---
        print(f"中值滤波窗口(length, width): {med_length}, {med_width}")
        background_data = median_filter(original_data, size=(med_width, med_length))
        if bkgdmode == 1:
            processed_data = original_data / background_data * bkgd0
        else:
            processed_data = original_data - background_data + bkgd0
        bkgd, sigma = cal_b(processed_data)
        print(f"滤波后(bkgd, sigma): {bkgd:.3f}, {sigma:.3f}")

    # 可选：平滑增强 (3x3 均值滤波，用于轻微模糊噪声)
    if enhance_flag == 1:
        processed_data = uniform_filter(processed_data, size=3)
        bkgd, sigma = cal_b(processed_data)
        print(f"3*3均值滤波后图像背景及sigma: {bkgd:.3f}, {sigma:.3f}")

    # 保存结果，数据类型转回 float32 节省空间
    fits.writeto(nfitsfile, processed_data.astype(np.float32), header, overwrite=True)
    print(f"处理完成，结果已保存到: {nfitsfile}")


def main():
    """主程序入口"""
    t0 = time.time()
    fitspath_file = "fitspath.in"
    if not os.path.exists(fitspath_file):
        print(
            f"错误: 主路径文件 '{fitspath_file}' 未找到。请确保该文件存在，其中包含待处理数据的目录路径。"
        )
        return

    # 读取所有待处理的日期文件夹路径
    with open(fitspath_file, "r") as f:
        all_paths = [line.strip() for line in f if line.strip()]

    # 遍历每一个目录进行处理
    for day_index, fitspath in enumerate(all_paths, 1):
        print(f"\n{'=' * 20} [ {day_index}/{len(all_paths)} ] {'=' * 20}")
        print(f"正在处理路径: {fitspath}")

        # 每次循环都重新解析配置，允许不同运行间微调（虽然通常是一样的）
        config = parse_config("adias.cfg")
        print("当前配置参数:", config)

        # --- 清理旧文件 ---
        # 删除旧的 *_n.fit 结果文件和 *.lst 列表文件，确保本次运行干净
        for f in glob.glob(os.path.join(fitspath, "*_n.fit*")) + glob.glob(
            os.path.join(fitspath, "*.lst")
        ):
            os.remove(f)

        # 获取当前目录下的所有原始 .fit 文件
        science_files_to_process = sorted(glob.glob(os.path.join(fitspath, "*.fit")))
        if not science_files_to_process:
            print(f"在 '{fitspath}' 中未找到FITS文件，跳过当天。")
            continue

        # 生成 fits.lst 文件列表（供后续程序如 02match 等使用）
        with open(os.path.join(fitspath, "fits.lst"), "w") as f_lst:
            for ff in science_files_to_process:
                f_lst.write(f"{ff}\n")
        print(f"已生成fit文件序列--> {os.path.join(fitspath, 'fits.lst')}")

        # 检查是否开启 Super Background 处理模式
        if config["superflag"] == 1:
            print("\n--- 进入super模式 ---")
            for science_file in science_files_to_process:
                base, ext = os.path.splitext(science_file)
                # 输出文件名加 '_n' 后缀
                output_file = f"{base}_n{ext}"
                fits_superbkgd_pro(
                    science_file,
                    config["med_length"],
                    config["med_width"],
                    config["bkgdmode"],
                    config["enhance_flag"],
                    output_file,
                )
        else:
            print("根据配置文件，未启用super模式，跳过处理。")

    print(f"\n{'=' * 50}\n所有 {len(all_paths)} 天的数据处理完毕。\n{'=' * 50}")
    print(f"代码总耗时: {time.time() - t0:.2f} s")


if __name__ == "__main__":
    main()
