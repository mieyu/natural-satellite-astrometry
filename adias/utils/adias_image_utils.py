# 功能：图像统计与滤波工具函数（背景估计、中值滤波、均值滤波）。
# 使用：from adias.utils.image_utils import calculate_background, apply_superbkgd

import cv2
import numpy as np
from scipy.ndimage import label as ndimage_label
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


def detect_stars_by_moments(data, bkgd_threshold, pos_method, bitpix=16):
    """
    连通域星象检测 + 修正矩定中心（子像素精度）。

    Parameters
    ----------
    data            : np.ndarray，float64 图像数据
    bkgd_threshold  : float，背景起伏阈值系数
    pos_method      : int，修正矩阶数（1/2/3）
    bitpix          : int，FITS 头 BITPIX 值，用于动态计算饱和阈值，默认 16
                      对应 Fortran：maxflux = 2**bitpix - 1

    Returns
    -------
    detected_stars : list[dict]，按亮度降序排列的星表
        每个 dict 包含：starx, stary, sumi, snr, star_id, star_pix, overflag
    bkgd           : float，背景均值
    bkgdsigma      : float，背景 sigma
    """
    naxis2, naxis1 = data.shape  # naxis2=行数(Y/height), naxis1=列数(X/width)

    # [差异4] maxflux 由 bitpix 动态计算，与 Fortran 的 maxflux=2**bitpix-1 一致
    # 原 Python 硬编码 65535.0，对非 16-bit 图像会误判饱和
    maxflux = float(2**bitpix - 1)

    minpix = 3
    maxpix = int(np.pi * 40**2)

    bkgd, bkgdsigma = calculate_background(data)

    # 阈值分割
    data_thresh = data - (bkgd + bkgd_threshold * bkgdsigma)
    data_thresh[data_thresh < 0] = 0

    # 边缘清零——四条边各清一像素，与 Fortran 边缘清零等价。
    # 注意 Fortran 内部约定与 Python(FITS) 相反：
    #   Fortran naxis1=行数、naxis2=列数；Python naxis2=行数、naxis1=列数
    # 对应关系：
    #   abox(1,j)=0      →  data_thresh[0, :]          上边缘
    #   abox(naxis1,j)=0 →  data_thresh[naxis2-1, :]   下边缘（Fortran naxis1=行数）
    #   abox(i,1)=0      →  data_thresh[:, 0]           左边缘
    #   abox(i,naxis2)=0 →  data_thresh[:, naxis1-1]   右边缘（Fortran naxis2=列数）
    data_thresh[0, :] = 0
    data_thresh[naxis2 - 1, :] = 0
    data_thresh[:, 0] = 0
    data_thresh[:, naxis1 - 1] = 0

    structure = np.ones((3, 3), dtype=int)
    labels, num_features = ndimage_label(data_thresh > 0, structure=structure)

    if num_features == 0:
        return [], bkgd, bkgdsigma

    detected_stars = []
    for i in range(1, num_features + 1):
        coords = np.where(labels == i)
        rows, cols = coords

        # [差异3] 质心累加与所有统计量仅限 10 像素内边距区域内的像素
        # 对应 Fortran 质心累加循环：do i=10,naxis2-10; do j=10,naxis1-10
        # 原 Python 是先用全部像素算质心再做坐标过滤，与 Fortran 在边缘星象时行为不同：
        # Fortran 只累加内部像素（边缘像素不贡献），Python 原版用全部像素算质心后丢弃。
        interior = (
            (rows >= 10) & (rows < naxis2 - 10) & (cols >= 10) & (cols < naxis1 - 10)
        )
        if not np.any(interior):
            continue

        int_rows = rows[interior]
        int_cols = cols[interior]
        int_thresh = data_thresh[int_rows, int_cols]  # abox(i,j) in Fortran
        int_orig = data[int_rows, int_cols]  # abox0(i,j) in Fortran

        # numpix / minpix / maxpix 均基于内边距内像素数（与 Fortran 一致）
        num_pix = len(int_rows)
        if not (minpix <= num_pix <= maxpix):
            continue

        # [差异4] 用动态 maxflux 检测过曝（Fortran: if(abox0(i,j).ge.maxflux) overflag=1）
        if np.any(int_orig >= maxflux):
            continue

        weights = int_thresh**pos_method
        sum_weights = np.sum(weights)
        if sum_weights < 1e-9:
            continue

        # 质心仅由内边距内像素贡献（Fortran: starx=sumx/sumi, stary=sumy/sumi）
        stary_0 = np.sum(int_rows * weights) / sum_weights
        starx_0 = np.sum(int_cols * weights) / sum_weights

        # sumi_real / snr 均基于内边距内像素（与 Fortran numpix/sumi_real 一致）
        sumi_real = np.sum(int_thresh)
        snr_denom = np.sqrt(sumi_real + num_pix * bkgdsigma**2)
        snr = sumi_real / snr_denom if snr_denom > 0 else 0

        detected_stars.append(
            {
                "starx": starx_0 + 1,
                "stary": stary_0 + 1,
                "sumi": sumi_real,
                "snr": snr,
                "star_id": i,
                "star_pix": num_pix,
                "overflag": 0,
            }
        )

    detected_stars.sort(key=lambda s: s["sumi"], reverse=True)
    return detected_stars, bkgd, bkgdsigma


def homomorphic_filter(data, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5):
    """
    同态滤波（Homomorphic Filter）。
    通过对数域高斯高通滤波压制低频光照变化，增强高频细节。

    Parameters
    ----------
    data       : np.ndarray，float64 图像数据
    gamma_low  : float，低频增益（< 1 压制背景）
    gamma_high : float，高频增益（> 1 增强细节）
    cutoff     : float，截止频率（像素单位）
    c          : float，滤波器过渡陡度

    Returns
    -------
    np.ndarray，float64，滤波后图像（灰度值域与输入一致）
    """
    image = data.astype(np.float64)
    orig_min, orig_max = image.min(), image.max()

    log_image = np.log(image + 1e-6)

    fft_shift = np.fft.fftshift(np.fft.fft2(log_image))

    rows, cols = image.shape
    x = np.linspace(-cols / 2, cols / 2, cols)
    y = np.linspace(-rows / 2, rows / 2, rows)
    xx, yy = np.meshgrid(x, y)
    H = (gamma_high - gamma_low) * (
        1 - np.exp(-c * (xx**2 + yy**2) / cutoff**2)
    ) + gamma_low

    img_back = np.abs(np.fft.ifft2(np.fft.ifftshift(fft_shift * H)))
    filtered = np.exp(img_back) - 1e-6

    # 恢复到原始灰度值域
    bg_mask = image < np.percentile(image, 50)
    scale = np.std(image[bg_mask]) / (np.std(filtered[bg_mask]) + 1e-9)
    offset = np.mean(image[bg_mask]) - np.mean(filtered[bg_mask]) * scale
    restored = np.clip(filtered * scale + offset, orig_min, orig_max)

    return restored


def bilateral_retinex(data, d=15):
    """
    双边 Retinex（BFR，Bilateral Filter Retinex）。
    在对数域用双边滤波分离光照与反射，输出反射分量（去除背景光照后的细节图）。

    Parameters
    ----------
    data : np.ndarray，float64 图像数据（原始 ADU 值）
    d    : int，双边滤波邻域直径

    Returns
    -------
    reflectance  : np.ndarray，float64，反射分量（细节）
    illumination : np.ndarray，float64，光照分量（背景）
    """
    max_val = data.max()
    if max_val <= 0:
        return data.copy(), data.copy()

    img_norm = (data / max_val).astype(np.float32)
    log_img = np.log1p(img_norm)

    bilateral = cv2.bilateralFilter(log_img, d, 120, 120)
    detail = log_img - bilateral

    reflectance = np.expm1(detail).astype(np.float64)
    illumination = np.expm1(bilateral).astype(np.float64)

    # 归一化回原始值域
    def _norm_to_range(arr, target_max):
        a_min, a_max = arr.min(), arr.max()
        if a_max - a_min < 1e-9:
            return arr
        return (arr - a_min) / (a_max - a_min) * target_max

    reflectance = _norm_to_range(reflectance, max_val)
    illumination = _norm_to_range(illumination, max_val)

    return reflectance, illumination
