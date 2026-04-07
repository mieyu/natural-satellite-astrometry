# 功能：图像统计与滤波工具函数（背景估计、中值滤波、均值滤波）。
# 使用：from adias.utils.image_utils import calculate_background, apply_superbkgd

import numpy as np
from scipy.ndimage import median_filter, uniform_filter, label as ndimage_label


def calculate_background(data, sigma_factor=2.6, max_iter=10, convergence=0.01):
    """
    使用迭代 Sigma-Clipping（Sigma 剔除）算法计算图像或数组的背景均值和标准差。

    该算法通过多次迭代，不断剔除掉偏离均值超过 `sigma_factor` 倍标准差的异常值，
    从而获得更准确、不受极端值（如亮星、坏像素）影响的背景统计信息。
    Parameters
    ----------
    data          : np.ndarray，输入图像（任意形状）
    sigma_factor  : float，剔除阈值倍数，默认 2.6
    max_iter      : int，最大迭代次数，默认 10
    convergence   : float，sigma 变化率收敛阈值，默认 0.01

    Returns
    -------
    avervalue : float，背景均值
    sigma     : float，背景标准差
    """
    flat = np.asarray(data, dtype=np.float64).ravel()
    n = len(flat)
    if n < 2:
        return (float(flat[0]) if n == 1 else 0.0), 0.0

    avervalue = np.mean(flat)
    sigma = np.std(flat, ddof=1)

    for _ in range(max_iter):
        old_sigma = sigma

        threshold = sigma_factor * sigma
        clipped = flat[np.abs(flat - avervalue) <= threshold]

        if len(clipped) < 2:
            break

        avervalue = np.mean(clipped)
        sigma2 = np.std(clipped, ddof=1)

        if sigma2 <= 1e-6 or abs(sigma2 - old_sigma) < convergence * old_sigma:
            sigma = sigma2
            break

        sigma = sigma2

    return avervalue, sigma


def apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode):
    """
    对图像执行一次中值滤波并按 bkgdmode 扣除背景。

    Parameters
    ----------
    data      : np.ndarray，输入图像
    bkgd0     : float，全场背景均值（用于恢复平均亮度）
    med_length: int，滤波窗口列方向尺寸
    med_width : int，滤波窗口行方向尺寸
    bkgdmode  : int，1=除法归一化，2=减法扣除

    Returns
    -------
    np.ndarray，扣除背景后的图像
    """
    # 判断：给定的 med_width 是否大于 1？
    if med_width > 1:
        # 如果大于 1，就生成一个“竖长条”形状的窗口
        kernel = (med_width, 1)  
    else:
        # 如果不大于 1，就忽略 med_width，用 med_length 生成一个“横长条”形状的窗口
        kernel = (1, med_length)
        
    bg = median_filter(data, size=kernel)

    if bkgdmode == 1:
        return data / bg * bkgd0
    else:
        return data - bg + bkgd0


def apply_smooth(data):
    """
    3×3 均值滤波轻微降噪（对应 enhance_flag=1）。

    Parameters
    ----------
    data : np.ndarray

    Returns
    -------
    np.ndarray
    """
    return uniform_filter(data, size=3)


def detect_stars_by_moments(data, bkgd_threshold, pos_method):
    """
    连通域星象检测 + 修正矩定中心（子像素精度）。

    Parameters
    ----------
    data            : np.ndarray，float64 图像数据
    bkgd_threshold  : float，背景起伏阈值系数
    pos_method      : int，修正矩阶数（1/2/3）

    Returns
    -------
    detected_stars : list[dict]，按亮度降序排列的星表
        每个 dict 包含：starx, stary, sumi, snr, star_id, star_pix, overflag
    bkgd           : float，背景均值
    bkgdsigma      : float，背景 sigma
    """
    naxis2, naxis1 = data.shape
    maxflux = 65535.0
    minpix  = 3
    maxpix  = int(np.pi * 40 ** 2)

    bkgd, bkgdsigma = calculate_background(data)

    # 阈值分割并清除边缘
    data_thresh = data - (bkgd + bkgd_threshold * bkgdsigma)
    data_thresh[data_thresh < 0] = 0
    data_thresh[0, :]  = 0
    data_thresh[-1, :] = 0
    data_thresh[:, 0]  = 0
    data_thresh[:, -1] = 0

    structure = np.ones((3, 3), dtype=int)
    labels, num_features = ndimage_label(data_thresh > 0, structure=structure)

    if num_features == 0:
        return [], bkgd, bkgdsigma

    detected_stars = []
    for i in range(1, num_features + 1):
        coords  = np.where(labels == i)
        num_pix = len(coords[0])
        if not (minpix <= num_pix <= maxpix):
            continue

        pixel_values_orig   = data[coords]
        if np.any(pixel_values_orig >= maxflux):   # 过曝跳过
            continue

        pixel_values_thresh = data_thresh[coords]
        weights     = pixel_values_thresh ** pos_method
        sum_weights = np.sum(weights)
        if sum_weights < 1e-9:
            continue

        stary_0 = np.sum(coords[0] * weights) / sum_weights
        starx_0 = np.sum(coords[1] * weights) / sum_weights
        if not (10 <= starx_0 < naxis1 - 10 and 10 <= stary_0 < naxis2 - 10):
            continue

        sumi_real     = np.sum(pixel_values_thresh)
        snr_denom     = np.sqrt(sumi_real + num_pix * bkgdsigma ** 2)
        snr           = sumi_real / snr_denom if snr_denom > 0 else 0

        detected_stars.append({
            'starx':    starx_0 + 1,
            'stary':    stary_0 + 1,
            'sumi':     sumi_real,
            'snr':      snr,
            'star_id':  i,
            'star_pix': num_pix,
            'overflag': 0,
        })

    detected_stars.sort(key=lambda s: s['sumi'], reverse=True)
    return detected_stars, bkgd, bkgdsigma