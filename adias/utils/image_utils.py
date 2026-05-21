# 功能：图像统计与滤波工具函数（背景估计、中值滤波、均值滤波）。
# 使用：from adias.utils.image_utils import calculate_background, apply_superbkgd

import cv2
import numpy as np
from scipy.ndimage import generate_binary_structure, median_filter, uniform_filter
from scipy.ndimage import label as ndimage_label


def calculate_background(data, sigma_factor=2.6, convergence=0.01, max_iter=100):
    """迭代 Sigma-Clipping 计算背景均值与 sigma。

    关键约定：
      - 每轮用 OLD mean/sigma 做剔除，剔除后再算 NEW mean2/sigma2
      - 收敛判据：|sigma2 - sigma| < convergence * sigma2（分母是 NEW sigma2）
      - 收敛或 sigma2 ≤ 1e-6 时输出 OLD mean/sigma（用作剔除基准的那对），不是 NEW

    max_iter 仅为安全保护，正常 5 次内收敛。
    """
    flat = np.asarray(data, dtype=np.float64).ravel()
    n = len(flat)
    if n < 2:
        return (float(flat[0]) if n == 1 else 0.0), 0.0

    avervalue = np.sum(flat) / n
    sigma = np.sqrt(np.sum((flat - avervalue) ** 2) / (n - 1))

    for _ in range(max_iter):
        mask = np.abs(flat - avervalue) <= sigma_factor * sigma
        clipped = flat[mask]
        k = len(clipped)
        if k < 2:
            break

        avervalue2 = np.sum(clipped) / k
        sigma2 = np.sqrt(np.sum((clipped - avervalue2) ** 2) / (k - 1))

        # 退化：图像极平坦，直接输出 OLD
        if sigma2 <= 1e-6:
            break
        # 收敛：差异 < convergence * NEW sigma2，输出 OLD
        if abs(sigma2 - sigma) < convergence * sigma2:
            break

        avervalue = avervalue2
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


def label_connectivity_fortran(abox, naxis2, naxis1, EPS=1e-9):
    """三段式连通域标号（Fortran 算法移植，保留方图同算行为）。

      Pass A: 首遍 4 邻居优先级标号（右上 > 正上 > 左上 > 左），
              用 elseif 链继承第一个非零邻居 label
      Pass B: 在 ±250 像素方框内就地合并水平相邻的不同 label
      Pass C: 8 邻接等价表 → 去重 → 简化合并 → 再去重 → 替换

    与 scipy 标准 8 连通的差异：Pass B 的 nr=250 局部合并是 Fortran 特有，
    在 Fortran 简化合并失败的极少数复杂形状下，scipy 结果反而更稳健。

    注：Pass A 的循环上界用了 naxis1/naxis2 反置（Fortran 自身 bug），
    对方图 naxis1==naxis2 无影响，这里完整保留以匹配原行为。
    """
    abox_l = abox.tolist()

    # ── Pass A：4 邻居优先级标号 ─────────────────────────────────────
    idbox = [[0] * naxis1 for _ in range(naxis2)]
    numobj = 0
    for i in range(1, naxis1 - 1):  # Fortran i=2..naxis1-1
        row_im1 = abox_l[i - 1]
        row_i = abox_l[i]
        idbox_im1 = idbox[i - 1]
        idbox_i = idbox[i]
        for j in range(1, naxis2 - 1):  # Fortran j=2..naxis2-1
            v = row_i[j]
            if v > EPS:
                lty1 = row_im1[j + 1]  # 右上
                lty2 = row_im1[j]  # 正上
                lty3 = row_im1[j - 1]  # 左上
                lty4 = row_i[j - 1]  # 左
                # 4 邻全 0 → 新建目标
                if lty1 + lty2 + lty3 + lty4 <= EPS:
                    numobj += 1
                    idbox_i[j] = numobj
                # elseif 链：取第一个非零邻居的 label
                elif lty1 > EPS:
                    idbox_i[j] = idbox_im1[j + 1]
                elif lty2 > EPS:
                    idbox_i[j] = idbox_im1[j]
                elif lty3 > EPS:
                    idbox_i[j] = idbox_im1[j - 1]
                elif lty4 > EPS:
                    idbox_i[j] = idbox_i[j - 1]

    # 转 numpy 用于 Pass B/C 的向量化子区域操作
    idbox2 = np.array(idbox, dtype=np.int32)

    # ── Pass B：±250 像素方框内合并水平相邻的不同 label ─────────────
    nr = 250
    for i in range(1, naxis2 - 1):
        row_abox_i = abox_l[i]
        for j in range(naxis1 - 2, 0, -1):  # 从右向左
            if row_abox_i[j] > EPS and row_abox_i[j - 1] > EPS:
                lab_left = int(idbox2[i, j - 1])
                lab_cur = int(idbox2[i, j])
                if lab_cur != lab_left:
                    ni1 = max(i - nr, 0)
                    ni2 = min(i + nr, naxis2 - 1)
                    nj1 = max(j - nr, 0)
                    nj2 = min(j + nr, naxis1 - 1)
                    sub = idbox2[ni1 : ni2 + 1, nj1 : nj2 + 1]
                    nrows = ni2 - ni1 + 1
                    ncols = nj2 - nj1 + 1
                    # 排除整行 i 与整列 j-1（Fortran 条件 i1≠i AND j1≠j-1）
                    row_mask = np.ones(nrows, dtype=bool)
                    if 0 <= i - ni1 < nrows:
                        row_mask[i - ni1] = False
                    col_mask = np.ones(ncols, dtype=bool)
                    if 0 <= (j - 1) - nj1 < ncols:
                        col_mask[(j - 1) - nj1] = False
                    keep = row_mask[:, None] & col_mask[None, :]
                    sub_mask = (sub == lab_left) & keep
                    sub[sub_mask] = lab_cur
                    # 被排除的 (i, j-1) 单点需手动更新
                    idbox2[i, j - 1] = lab_cur

    # ── Pass C：8 邻接等价表合并 ─────────────────────────────────────
    # 步骤 1：扫每个 >0 像素，记录与 8 邻居中不同 label 的等价对 (min, max)
    # 邻居顺序与 Fortran 一致：左、右、左上、上、右上、左下、下、右下
    pairs1 = []
    for i in range(1, naxis2 - 1):
        row_abox_i = abox_l[i]
        idbox2_im1 = idbox2[i - 1].tolist()
        idbox2_i = idbox2[i].tolist()
        idbox2_ip1 = idbox2[i + 1].tolist()
        for j in range(1, naxis1 - 1):
            if row_abox_i[j] > EPS:
                cur = idbox2_i[j]
                for nb in (
                    idbox2_i[j - 1], idbox2_i[j + 1],
                    idbox2_im1[j - 1], idbox2_im1[j], idbox2_im1[j + 1],
                    idbox2_ip1[j - 1], idbox2_ip1[j], idbox2_ip1[j + 1],
                ):
                    if cur != nb and nb > 0:
                        pairs1.append((cur, nb) if cur < nb else (nb, cur))

    # 步骤 2：去重，保首次出现顺序
    seen = set()
    pairs2 = []
    for p in pairs1:
        if p not in seen:
            seen.add(p)
            pairs2.append(p)

    # 步骤 3：简化合并（单遍扫描，不是完整 Union-Find；在罕见复杂形状下会
    # 合并不完整——但行为与 Fortran 一致，scipy 路径可绕开此限制）
    # 对每对 (t1, t2)，若 t1==eid2[j] 取 t1=eid1[j]；否则若 t2==eid2[j]
    # 则 t2=t1, t1=eid1[j]。无论是否匹配都加入缓冲。
    pairs3 = []
    eid1_buf = []
    eid2_buf = []
    for idx, (t1, t2) in enumerate(pairs2):
        if idx > 0:
            for jj in range(len(eid2_buf)):
                if t1 == eid2_buf[jj]:
                    t1 = eid1_buf[jj]
                    break
                elif t2 == eid2_buf[jj]:
                    t2 = t1
                    t1 = eid1_buf[jj]
                    break
        eid1_buf.append(t1)
        eid2_buf.append(t2)
        pairs3.append((t1, t2))

    # 步骤 4：再次去重
    seen = set()
    pairs4 = []
    for p in pairs3:
        if p not in seen:
            seen.add(p)
            pairs4.append(p)

    # 步骤 5：按等价对顺序逐对把 idbox2 中的 e2 替换为 e1
    if pairs4:
        mask_pos = abox > EPS
        for e1, e2 in pairs4:
            replace_mask = (idbox2 == e2) & mask_pos
            if replace_mask.any():
                idbox2[replace_mask] = e1

    return idbox2


def label_connectivity_scipy(abox, naxis2, naxis1, EPS=1e-9):
    """
    【B 函数】基于 scipy.ndimage_label 的标准 8 连通标号
    （不含 Fortran 的 nr=250 子区域合并）。

    Pass A 的 4 邻居优先级标号 + Pass C 的等价表传递闭包合并，
    在算法上等价于标准 8 连通；scipy 实现使用严格 Union-Find，
    比 Fortran 的简化单遍合并更稳健（在 Fortran 简化合并算法
    可能出现合并不完整的极少数复杂形状下，scipy 给出正确结果）。

    Parameters
    ----------
    abox    : np.ndarray，阈值分割后的 float 图像（已边缘清零）
    naxis2  : int，行数
    naxis1  : int，列数（仅用于签名一致，scipy 内部不需要）
    EPS     : float，零值判定阈值（默认 1e-9）

    Returns
    -------
    idbox2 : np.ndarray (int32, shape=(naxis2, naxis1))，连通域标号
    """
    structure = generate_binary_structure(2, 2)
    labels, _ = ndimage_label(abox > EPS, structure=structure)
    return labels.astype(np.int32)


def detect_stars_by_moments(
    data, bkgd_threshold, pos_method, bitpix=16, connectivity="fortran"
):
    """
    连通域星象检测 + 修正矩定中心（子像素精度）。

    Parameters
    ----------
    data            : np.ndarray，float64 图像数据
    bkgd_threshold  : float，背景起伏阈值系数
    pos_method      : int，修正矩阶数（1/2/3）
    bitpix          : int，FITS 头 BITPIX 值，用于动态计算饱和阈值，默认 16
                      对应 Fortran：maxflux = 2**bitpix - 1（仅对整型 FITS 有效）
    connectivity    : str，连通域算法选择
                      - "fortran"（默认）：A 函数 label_connectivity_fortran，
                        完全按 Fortran 三段式实现（首遍标号 + nr=250 合并 + 等价表）
                      - "scipy"：B 函数 label_connectivity_scipy，
                        Python 标准 8 连通，不含 nr=250 子区域合并

    Returns
    -------
    detected_stars : list[dict]，按亮度（sumi_real）降序排列的星表
        每个 dict 包含：starx, stary, sumi, snr, star_id, star_pix, overflag
    bkgd           : float，背景均值
    bkgdsigma      : float，背景 sigma
    """
    naxis2, naxis1 = data.shape  # FITS 标准：data.shape[0]=NAXIS2(行), [1]=NAXIS1(列)

    # maxflux：Fortran 公式 2**bitpix-1 仅对整型 FITS（BITPIX>0）有意义；
    # 对浮点 FITS（BITPIX=-32/-64）会算出 ≈ -1，导致所有像素被误判过曝。
    # 浮点 FITS 没有整型饱和概念，用 +inf 禁用过曝判断。
    if bitpix > 0:
        maxflux = float(2**bitpix - 1)
    else:
        maxflux = float("inf")

    minpix = 10
    maxpix = int(np.pi * 40**2)
    EPS = 1e-9

    bkgd, bkgdsigma = calculate_background(data)

    # 阈值分割：低于 bkgd + threshold*sigma 的像素归 0
    abox = data - (bkgd + bkgd_threshold * bkgdsigma)
    abox[abox < 0] = 0
    abox0 = data  # 原始数据（保留过曝判断）

    # 边缘清零（最外一圈不参与连通域）
    abox[0, :] = 0
    abox[naxis2 - 1, :] = 0
    abox[:, 0] = 0
    abox[:, naxis1 - 1] = 0

    abox_l = abox.tolist()

    # 连通域标号
    if connectivity == "fortran":
        idbox2 = label_connectivity_fortran(abox, naxis2, naxis1, EPS)
    elif connectivity == "scipy":
        idbox2 = label_connectivity_scipy(abox, naxis2, naxis1, EPS)
    else:
        raise ValueError(
            f"connectivity 必须为 'fortran' 或 'scipy'，收到：{connectivity!r}"
        )

    # 形心累加：仅扫内边距区域 [10, naxis-10)，numpix 因此是内边距像素数
    # （不是 Pass A 标号阶段的整连通域像素数）。坐标用 1-based 行/列号。
    sumx = {}
    sumy = {}
    sumi_d = {}
    sumi_real_d = {}
    numpix = {}
    overflag = {}

    abox0_l = abox0.tolist()
    idbox2_l = idbox2.tolist()

    for i in range(9, naxis2 - 10):
        row_lab = idbox2_l[i]
        row_abox = abox_l[i]
        row_abox0 = abox0_l[i]
        for j in range(9, naxis1 - 10):
            lab = row_lab[j]
            if lab > 0:
                v = row_abox[j]
                vp = v**pos_method
                if lab in sumx:
                    sumx[lab] += (j + 1) * vp
                    sumy[lab] += (i + 1) * vp
                    sumi_d[lab] += vp
                    sumi_real_d[lab] += v
                    numpix[lab] += 1
                else:
                    sumx[lab] = (j + 1) * vp
                    sumy[lab] = (i + 1) * vp
                    sumi_d[lab] = vp
                    sumi_real_d[lab] = v
                    numpix[lab] = 1
            # overflag 在 lab>0 检查之外：即使 lab=0 也会标 overflag[0]=1（无害）
            if row_abox0[j] >= maxflux:
                overflag[lab] = 1

    # 输出星表：过曝星保留但 overflag=1，最终由 write_reg_file 二次过滤
    detected_stars = []
    for lab in sorted(numpix.keys()):
        n = numpix[lab]
        if not (minpix <= n <= maxpix):
            continue
        s_i = sumi_d[lab]
        if s_i < 1e-9:
            continue
        ofl = 1 if overflag.get(lab, 0) >= 1 else 0
        starx = sumx[lab] / s_i
        stary = sumy[lab] / s_i
        sumi_real = sumi_real_d[lab]
        denom = np.sqrt(sumi_real + n * bkgdsigma**2)
        snr = sumi_real / denom if denom > 0 else 0.0
        detected_stars.append(
            {
                "starx": starx,
                "stary": stary,
                "sumi": sumi_real,
                "snr": snr,
                "star_id": lab,
                "star_pix": n,
                "overflag": ofl,
            }
        )

    # 按亮度降序排序
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
