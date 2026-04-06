# **********************************CCD Image preprocessing - 02detect (Star Detection)**********************************
# program name: 02detect.py
#
# function:
#   1）逐幅读取待处理的科学图像（*.fit 或 *_n.fit），对每一幅图像进行连通域星象检测。
#   2）基于迭代 sigma-clipping 估计全场背景与 sigma，并按照背景起伏阈值和 SNR 阈值筛选星象。
#   3）采用“修正矩”方法（pos_method=1/2/3，对应不同阶数）计算星象中心位置（子像素精度）。
#   4）为每幅图像生成对应的 DS9 区域文件 *.reg，输出星象位置、亮度信息以及 SNR、像素数等参数。
#
# input:
#   0）主路径配置文件 fitspath.in：
#        - 每一行给出一个观测日期对应的 FITS 目录路径；
#        - 本脚本会逐日读取目录中的 fits.lst（由 01pre/pre_superbkgd 程序生成）。
#   1）配置文件 adias.cfg：
#        1.1）2bkgd_threshold   背景起伏阈值系数（决定 data - (bkgd + k * sigma) 的截断水平）；
#        1.2）2snr_threshold    信噪比阈值（仅输出 SNR 大于该阈值的星象）；
#        1.3）2pos_method       星象中心定位方法（1-修正矩；2-二阶修正矩；3-三阶修正矩）；
#        1.4）1superflag        是否使用 *_n.fit 作为输入（1=使用预处理后的超级背景图像；0=使用原始图像）。
#
# output:
#   1）检测星象文件：*.reg
#        - DS9 region 格式，记录每一颗星象的椭圆区域、总亮度、SNR、像素数、是否过曝、背景及背景 sigma 等信息；
#        - 文件位于每个观测目录下，与原始 .fit 文件同目录，文件名形如：original_name.fit.reg。
#
# 主要函数/子程序对应关系：
#   1）read_config(config_path)
#           读取 adias.cfg，并提取与星象检测相关的参数（bkgd_threshold、snr_threshold、pos_method、superflag）。
#   2）cal_b(data, sigma_factor, max_iter, convergence)
#           计算图像背景值及其 sigma（通过迭代 sigma-clipping 剔除恒星等高亮像素），复现 Fortran cal_b 子程序逻辑。
#   3）detect_stars_xzj(fits_file_path, bkgd_threshold, pos_method)
#           连通域检测星象 + 修正矩定星象中心：
#               - 阈值分割图像，去除边缘；
#               - 连通组件分析筛选像素数合适的候选星象；
#               - 利用修正矩/高阶矩计算中心位置、总亮度与 SNR；
#               - 返回按总亮度从大到小排序的星表。
#   4）main()
#           逐日读取 fitspath.in 中的观测路径：
#               - 读取每日 fits.lst；
#               - 按 superflag 选择使用 *.fit 或 *_n.fit 作为检测输入；
#               - 调用 detect_stars_xzj 完成星象检测；
#               - 将结果写出到 *.reg 文件（DS9 可直接加载显示）。
#
# 注意：
#   1）若在前一个预处理程序（01pre / 01pre_superbkgd）中使用了“超级背景图像”方法做预处理（superflag=1），
#      则本程序得到的结果仅适用于星象位置测量与匹配，不建议直接作为精确测光数据使用。
#   2）SNR 公式已按 Fortran 版本修改为：信号 = 所有像素减去背景，总噪声包含信号和背景起伏项。
#
# 历史版本说明（对应 Fortran）：
#  by zhy 2019.09.02
#  V2.2 add the enhance function by zhy 2019.09.24
#  V3.0  Chinese comment by zhy 2020.01.29
# 20200212修改信噪比公式，使得信噪比=所有像素-背景值/起伏度
# 20200216修改detect_xzj子程序，将亮度输出为原始图像亮度，没有减过背景的数据，方便在match部分计算夜天光
# 20200216亮度输出为原始图像-背景（含了bias）数值
# 20241001 修改过程输出为中文
#  V4.0 by lhy 2025.12.05 程序改写成python
# ***************************************************************************************************************

import os
import numpy as np
from astropy.io import fits
from scipy.ndimage import label
import time

def read_config(config_path='adias.cfg'):
    """读取 adias.cfg 配置文件"""
    config = {'bkgd_threshold': 5.0, 'snr_threshold': 5.0, 'pos_method': 2, 'superflag': 0}
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(('!', ';', '#', '[')): continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key, value = key.strip(), value.strip().split('#')[0].strip()
                    try:
                        if key == '1superflag':
                            config['superflag'] = int(value)
                        elif key == '2bkgd_threshold':
                            config['bkgd_threshold'] = float(value)
                        elif key == '2snr_threshold':
                            config['snr_threshold'] = float(value)
                        elif key == '2pos_method':
                            config['pos_method'] = int(value)
                    except (IndexError, ValueError):
                        pass
    except FileNotFoundError:
        print(f"错误：配置文件 '{config_path}' 未找到。将使用默认值。")
    return config

def cal_b(data, sigma_factor=2.6, max_iter=10, convergence=0.01):
    """计算图像背景和sigma，精确匹配Fortran cal_b子程序逻辑"""
    flat_data = data.flatten().astype(np.float64)
    npx = len(flat_data)
    if npx < 2: return np.mean(flat_data) if npx > 0 else 0, 0

    avervalue = np.mean(flat_data)
    sumvalue2 = np.sum((flat_data - avervalue) ** 2)
    sigma = np.sqrt(sumvalue2 / (npx - 1))

    for _ in range(max_iter):
        old_sigma = sigma
        mask = np.abs(flat_data - avervalue) <= sigma_factor * sigma
        clipped_data = flat_data[mask]
        k = len(clipped_data)
        if k < 2: break

        avervalue2 = np.mean(clipped_data)
        sumvalue2_new = np.sum((clipped_data - avervalue2) ** 2)
        sigma2 = np.sqrt(sumvalue2_new / (k - 1))

        if sigma2 <= 1e-6 or np.abs(sigma2 - old_sigma) < convergence * old_sigma:
            avervalue = avervalue2
            sigma = sigma2
            break
        avervalue = avervalue2
        sigma = sigma2
    return avervalue, sigma


def detect_stars_xzj(fits_file_path, bkgd_threshold, pos_method):
    """核心函数：连通域检测星象 + 修正矩定中心"""
    try:
        with fits.open(fits_file_path, ignore_missing_end=True) as hdul:
            header = hdul[0].header
            data = hdul[0].data.astype(np.float64)
    except Exception as e:
        print(f"    错误：无法读取FITS文件 '{os.path.basename(fits_file_path)}': {e}")
        return [], 0, 0

    naxis2, naxis1 = data.shape
    
    maxflux = 65535.0

    minpix = 3
    maxpix = int(np.pi * 40 ** 2)

    bkgd, bkgdsigma = cal_b(data)

    data_thresh = data - (bkgd + bkgd_threshold * bkgdsigma)
    data_thresh[data_thresh < 0] = 0

    data_thresh[0, :] = data_thresh[-1, :] = data_thresh[:, 0] = data_thresh[:, -1] = 0

    structure = np.ones((3, 3), dtype=int)
    labels, num_features = label(data_thresh > 0, structure=structure)

    if num_features == 0:
        return [], bkgd, bkgdsigma

    detected_stars = []
    for i in range(1, num_features + 1):
        coords = np.where(labels == i)
        num_pix = len(coords[0])

        if not (minpix <= num_pix <= maxpix): continue

        pixel_values_orig = data[coords]
        overflag = 1 if np.any(pixel_values_orig >= maxflux) else 0

        if overflag == 1: continue

        pixel_values_thresh = data_thresh[coords]
        weights = pixel_values_thresh ** pos_method
        sum_weights = np.sum(weights)

        if sum_weights < 1e-9: continue

        stary_0based = np.sum(coords[0] * weights) / sum_weights
        starx_0based = np.sum(coords[1] * weights) / sum_weights

        if not (10 <= starx_0based < naxis1 - 10 and 10 <= stary_0based < naxis2 - 10): continue

        sumi_real = np.sum(pixel_values_thresh)
        snr_denominator = np.sqrt(sumi_real + num_pix * bkgdsigma ** 2)
        snr = sumi_real / snr_denominator if snr_denominator > 0 else 0

        detected_stars.append({
            'starx': starx_0based + 1, 'stary': stary_0based + 1, 'sumi': sumi_real,
            'snr': snr, 'star_id': i, 'star_pix': num_pix, 'overflag': overflag
        })

    detected_stars.sort(key=lambda s: s['sumi'], reverse=True)
    return detected_stars, bkgd, bkgdsigma

def main():
    """主程序"""
    t0 = time.time()
    if not os.path.exists('fitspath.in'):
        print("错误：输入文件 'fitspath.in' 未找到！")
        return

    with open('fitspath.in', 'r') as f:
        fits_paths = [line.strip() for line in f if line.strip()]

    n_day_total = 0
    for fitspath in fits_paths:
        n_day_total += 1
        print(f"第 {n_day_total:03d} 天- 本日fits所在文件夹：{fitspath}")
        print("    检测出的星象的信息已写入reg文件，可供后续程序调用及DS9显示！")
        print("    ====================本日fits图像处理情况===================")
        print()

        config = read_config('adias.cfg')

        fits_list_path = os.path.join(fitspath, 'fits.lst')
        if not os.path.exists(fits_list_path):
            print(f"警告：在 '{fitspath}' 中未找到 'fits.lst' 文件，跳过此日期。")
            continue

        with open(fits_list_path, 'r') as f:
            fits_files = [os.path.basename(line.strip()) for line in f if line.strip()]

        n_fits_processed = 0
        for fitsfile0 in fits_files:
            n_fits_processed += 1
            print(f"  {n_fits_processed:04d}-{fitsfile0}")

            # superflag=1时，强制使用_n.fit
            if config['superflag'] > 0.5:
                base, ext = os.path.splitext(fitsfile0)
                fits_to_process_name = base + '_n' + ext
                print(f"    使用预处理图像进行检测: {fits_to_process_name}")
            else:
                fits_to_process_name = fitsfile0
                print("    使用原始图像进行图像检测！")

            full_fits_path = os.path.join(fitspath, fits_to_process_name)
            if not os.path.exists(full_fits_path):
                print(f"    错误：文件不存在: {full_fits_path}")
                continue

            stars, bkgd, bkgdsigma = detect_stars_xzj(
                full_fits_path, config['bkgd_threshold'], config['pos_method']
            )

            xyfile_path = os.path.join(fitspath, fitsfile0 + '.reg')
            n_outstar = 0
            with open(xyfile_path, 'w') as reg_file:
                reg_file.write(
                    'global color=green font="helvetica 10 normal" select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n')
                reg_file.write('physical\n')

                for star in stars:
                    if star['snr'] > config['snr_threshold'] and star['star_pix'] > 5:
                        line = f"ellipse {star['starx']:11.3f}{star['stary']:11.3f}{10.0:6.1f}{10.0:6.1f}   #  {star['sumi']:21.4f}{star['snr']:10.2f}{star['star_id']:5d}{star['star_pix']:5d}{star['overflag']:5d}{bkgd:15.3f}{bkgdsigma:15.3f}\n"
                        reg_file.write(line)
                        n_outstar += 1

            print(f"                    图像的背景及sigma: {bkgd:10.3f}{bkgdsigma:10.3f}")
            print(f"    满足SNR和最少像素数条件的检测星数: {n_outstar:4d}")
            print()

        print('================02Detect-Program execution summary==================')
        print(f'    完成星象检测(*.reg)，共检测图像：{n_fits_processed}')
        print('    检测出的星象信息已写入.reg文件（存储于图像文件夹，可供DS9加载使用）')
        print('====================================================================\n')

    print(f'星象检测程序结束，共检测图像天数：{n_day_total}')
    print('=================================================================')
    print(f"代码总耗时: {time.time() - t0:.2f} s")

if __name__ == '__main__':
    main()