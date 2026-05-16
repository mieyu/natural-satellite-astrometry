# 功能：图像统计与滤波工具函数（背景估计、中值滤波、均值滤波）。
# 使用：from adias.utils.image_utils import calculate_background, apply_superbkgd

import cv2
import numpy as np
from scipy.ndimage import label as ndimage_label
from scipy.ndimage import median_filter, uniform_filter


def calculate_background(data, sigma_factor=2.6, convergence=0.01, max_iter=100):
    """
    迭代 Sigma-Clipping 计算背景均值与起伏，严格对齐 Fortran 02detect.f90:1074
    的 cal_b 子程序逻辑。

    与 Fortran 一致的关键细节：
      1. 初始 mean / sigma 使用全图像素（ddof=1）。
      2. 每轮用 OLD avervalue 与 OLD sigma 作为剔除阈值；
         随后用剔除后的子集计算 NEW avervalue2 与 NEW sigma2（用 NEW avervalue2 计算）。
      3. 收敛判据：|sigma2 - sigma| < convergence * sigma2（注意分母是 NEW sigma2）。
      4. 收敛或 sigma2 ≤ 1e-6 时，**输出 OLD avervalue 与 OLD sigma**（即上一轮的值，
         也就是本轮用作剔除基准的那对统计量），而不是 NEW avervalue2 / sigma2。
      5. Fortran 无最大迭代上限；这里加 max_iter=100 仅作安全保护，正常 5 次内收敛。

    Parameters
    ----------
    data         : np.ndarray，输入图像（任意形状）
    sigma_factor : float，剔除阈值倍数，默认 2.6（对应 Fortran 参数 sfa）
    convergence  : float，sigma 相对变化收敛阈值，默认 0.01
    max_iter     : int，最大迭代次数（安全上限），默认 100

    Returns
    -------
    avervalue : float，背景均值
    sigma     : float，背景标准差
    """
    flat = np.asarray(data, dtype=np.float64).ravel()
    n = len(flat)
    if n < 2:
        return (float(flat[0]) if n == 1 else 0.0), 0.0

    # 初始 mean / sigma：全图，对应 Fortran 1091-1100 行
    avervalue = np.sum(flat) / n
    sigma = np.sqrt(np.sum((flat - avervalue) ** 2) / (n - 1))

    for _ in range(max_iter):
        # 用 OLD avervalue 与 OLD sigma 做剔除（Fortran 1102-1110 行）
        mask = np.abs(flat - avervalue) <= sigma_factor * sigma
        clipped = flat[mask]
        k = len(clipped)
        if k < 2:
            break

        # NEW avervalue2 / sigma2：sigma2 用 NEW avervalue2 计算（Fortran 1111-1119 行）
        avervalue2 = np.sum(clipped) / k
        sigma2 = np.sqrt(np.sum((clipped - avervalue2) ** 2) / (k - 1))

        # 退化分支：图像极平坦，直接输出 OLD 值（Fortran 1121-1124 行 → goto 20）
        if sigma2 <= 1e-6:
            break

        # 收敛分支：差异 < 1% NEW sigma2 时，直接输出 OLD 值（Fortran 1126 行 fall-through）
        if abs(sigma2 - sigma) < convergence * sigma2:
            break

        # 未收敛：用 NEW 值替换后再迭代（Fortran 1128-1130 行）
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
    """
    【A 函数】完全按照 Fortran 02detect.f90 三段式连通域算法实现的连通域标号。

      Pass A（02detect.f90:255-340）：
        首遍 4 邻居优先级标号（lty1=右上, lty2=正上, lty3=左上, lty4=左）
        elseif 链——找到第一个非零邻居就继承其 label
      Pass B（02detect.f90:344-377）：
        nr=250 像素半径就地合并——针对水平相邻不同 label，
        在 ±250 像素方框内把 idbox2 等于左侧 label 的所有像素改为右侧 label
      Pass C（02detect.f90:380-554）：
        8 邻接等价表收集 → 去重 → 简化合并 → 再去重 → 替换

    Parameters
    ----------
    abox    : np.ndarray，阈值分割后的 float 图像（已边缘清零）
    naxis2  : int，行数
    naxis1  : int，列数
    EPS     : float，零值判定阈值（默认 1e-9）

    Returns
    -------
    idbox2 : np.ndarray (int32, shape=(naxis2, naxis1))，最终连通域标号
    """
    abox_l = abox.tolist()

    # ============== Pass A：首遍 4 邻居优先级标号 ==============
    # 完全对应 Fortran 02detect.f90:255-340
    # Fortran 循环：do i=2,naxis1-1; do j=2,naxis2-1
    # 注：Fortran 这里的 i/j 是行/列索引，但循环上界用了 naxis1/naxis2
    # 反置——Fortran 自身 bug，对方图（naxis1==naxis2）无影响。
    # 这里完全保留 Fortran 原貌（包括循环上界）。
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

    # ============== Pass B：nr=250 局部合并 ==============
    # 完全对应 Fortran 02detect.f90:344-377
    # 循环：do i=2,naxis2-1; do j=naxis1-1,2,-1（j 从右向左）
    nr = 250
    for i in range(1, naxis2 - 1):  # Fortran i=2..naxis2-1
        row_abox_i = abox_l[i]
        for j in range(naxis1 - 2, 0, -1):  # Fortran j=naxis1-1..2 反向
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
                    # Fortran 条件 (i1.ne.i .and. j1.ne.j-1)：
                    # 是 AND，排除整行 i 与整列 j-1（保留 Fortran 原貌）
                    row_mask = np.ones(nrows, dtype=bool)
                    if 0 <= i - ni1 < nrows:
                        row_mask[i - ni1] = False
                    col_mask = np.ones(ncols, dtype=bool)
                    if 0 <= (j - 1) - nj1 < ncols:
                        col_mask[(j - 1) - nj1] = False
                    keep = row_mask[:, None] & col_mask[None, :]
                    sub_mask = (sub == lab_left) & keep
                    sub[sub_mask] = lab_cur
                    # Fortran 02detect.f90:372：手动设置 (i, j-1) 这一点
                    idbox2[i, j - 1] = lab_cur

    # ============== Pass C：8 邻接等价表合并 ==============
    # 完全对应 Fortran 02detect.f90:380-554
    # 步骤 1：扫描每个 >0 像素，对 8 邻居中 label 不同且 >0 的，
    #        记录等价对 (min_label, max_label) 到 pairs1
    # 顺序与 Fortran 一致：左、右、左上、上、右上、左下、下、右下
    pairs1 = []
    for i in range(1, naxis2 - 1):  # Fortran i=2..naxis2-1
        row_abox_i = abox_l[i]
        idbox2_im1 = idbox2[i - 1].tolist()
        idbox2_i = idbox2[i].tolist()
        idbox2_ip1 = idbox2[i + 1].tolist()
        for j in range(1, naxis1 - 1):  # Fortran j=2..naxis1-1
            if row_abox_i[j] > EPS:
                cur = idbox2_i[j]
                # Fortran 02detect.f90:389-451 顺序
                for nb in (
                    idbox2_i[j - 1],  # 左
                    idbox2_i[j + 1],  # 右
                    idbox2_im1[j - 1],  # 左上
                    idbox2_im1[j],  # 上
                    idbox2_im1[j + 1],  # 右上
                    idbox2_ip1[j - 1],  # 左下
                    idbox2_ip1[j],  # 下
                    idbox2_ip1[j + 1],  # 右下
                ):
                    if cur != nb and nb > 0:
                        if cur < nb:
                            pairs1.append((cur, nb))
                        else:
                            pairs1.append((nb, cur))

    # 步骤 2：去重 1（Fortran 02detect.f90:459-475，按字符串去重，保首次出现顺序）
    seen = set()
    pairs2 = []
    for p in pairs1:
        if p not in seen:
            seen.add(p)
            pairs2.append(p)

    # 步骤 3：简化合并（Fortran 02detect.f90:491-512）
    # 对每个 pair (t1, t2)，扫描已存的 (eid1[j], eid2[j])：
    #   - 若 t1 == eid2[j]：t1 = eid1[j]，break
    #   - 否则若 t2 == eid2[j]：t2 = t1；t1 = eid1[j]，break
    # 然后将 (t1, t2) 加入缓冲。即使无匹配也加入。
    pairs3 = []
    eid1_buf = []
    eid2_buf = []
    for idx, (t1, t2) in enumerate(pairs2):
        if idx > 0:  # Fortran 第一对直接写入，从第二对开始查找
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

    # 步骤 4：去重 2（Fortran 02detect.f90:514-535）
    seen = set()
    pairs4 = []
    for p in pairs3:
        if p not in seen:
            seen.add(p)
            pairs4.append(p)

    # 步骤 5：替换（Fortran 02detect.f90:546-554）
    # Fortran：对每个 >0 像素，按等价表顺序逐 pair 检查并替换。
    # 等价于：按 pair 顺序，每对将所有匹配 e2 的 >0 像素改为 e1。
    # （单像素视角：先 p1 后 p2 ... 与全图视角先全图 p1 再全图 p2 等价）
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
    structure = np.ones((3, 3), dtype=int)
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

    # 阈值分割（Fortran 02detect.f90:222-225）
    abox = data - (bkgd + bkgd_threshold * bkgdsigma)
    abox[abox < 0] = 0
    abox0 = data  # 原始数据（用于 overflag 判断）

    # 边缘清零（Fortran 02detect.f90:233-240，对方图与 Fortran 完全等价）
    abox[0, :] = 0
    abox[naxis2 - 1, :] = 0
    abox[:, 0] = 0
    abox[:, naxis1 - 1] = 0

    abox_l = abox.tolist()

    # ============== 连通域标号（A/B 二选一）==============
    if connectivity == "fortran":
        idbox2 = label_connectivity_fortran(abox, naxis2, naxis1, EPS)
    elif connectivity == "scipy":
        idbox2 = label_connectivity_scipy(abox, naxis2, naxis1, EPS)
    else:
        raise ValueError(
            f"connectivity 必须为 'fortran' 或 'scipy'，收到：{connectivity!r}"
        )

    # ============== 形心累加（Fortran 02detect.f90:570-625）==============
    # numpix/sumx/sumy/sumi/sumi_real/overflag 全部从内边距区域累加。
    # Fortran 02detect.f90:570 处 numpix=0 重置——所以 numpix 是内边距像素数，
    # 不是 Pass A 标号阶段的全连通域像素数。
    sumx = {}
    sumy = {}
    sumi_d = {}
    sumi_real_d = {}
    numpix = {}
    overflag = {}

    abox0_l = abox0.tolist()
    idbox2_l = idbox2.tolist()

    # Fortran：do i=10,naxis2-10; do j=10,naxis1-10（1-based 包含两端）
    # Python 0-based：i=9..naxis2-11，即 range(9, naxis2-10)
    for i in range(9, naxis2 - 10):
        row_lab = idbox2_l[i]
        row_abox = abox_l[i]
        row_abox0 = abox0_l[i]
        for j in range(9, naxis1 - 10):
            lab = row_lab[j]
            if lab > 0:
                v = row_abox[j]
                vp = v**pos_method
                # Fortran 累加用 1-based 行/列号（j+1, i+1）
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
            # Fortran 02detect.f90:582：overflag 在 if(idbox2>0) 之外
            # 即使 lab=0 也会写 overflag[0]=1（无害，下游不会使用 lab=0）
            if row_abox0[j] >= maxflux:
                overflag[lab] = 1

    # ============== 输出星表（Fortran 02detect.f90:589-625）==============
    # Fortran 用 overflag<1 直接过滤；这里保留过曝星到列表（标 overflag=1），
    # 由 write_reg_file 按 overflag<1 二次过滤——最终 .reg 输出与 Fortran 一致。
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

    # 按亮度 sumi_real 降序排序（Fortran 02detect.f90:629 sorting_7terms）
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
