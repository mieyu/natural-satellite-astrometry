# 功能：图像统计与滤波工具函数（背景估计、中值滤波、均值滤波）。
# 使用：from adias.utils.image_utils import cal_b, apply_superbkgd

import numpy as np
from scipy.ndimage import median_filter, uniform_filter


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
    kernel = (med_width, 1) if med_width > 1 else (1, med_length)
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