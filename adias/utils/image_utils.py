"""图像统计与滤波工具：背景估计、超级背景扣除、连通域标号、星象检测。

实现要点：
  - calculate_background 使用迭代 sigma-clipping，约定收敛时返回旧均值/旋差。
  - 连通域 fortran 路径完整移植原算法（含 nr=250 子区域合并），与 scipy
    路径在算法等价但在罕见复杂形状下精度不同；切换由 cfg 控制。
  - 星象检测仅扫内边距 [10, naxis-10) 内的像素累加形心。
  - 中值滤波带状核优先走 bottleneck.move_median（C 实现的滚动中值），
    scipy_threaded 是切块多线程备路，scipy 是最稳的兜底。
"""

from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from scipy.ndimage import generate_binary_structure, median_filter, uniform_filter
from scipy.ndimage import label as ndimage_label

try:
    import bottleneck as _bn
    _HAS_BOTTLENECK = True
except ImportError:
    _HAS_BOTTLENECK = False

try:
    import numba as _numba
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False


def calculate_background(data, sigma_factor=2.6, convergence=0.01, max_iter=100):
    """迭代 Sigma-Clipping 计算背景均值与 sigma。

    关键约定（不可破坏的不变量）：
      - 每轮用 OLD mean/sigma 做剔除，剔除后再算 NEW mean2/sigma2
      - 收敛判据：|sigma2 - sigma| < convergence * sigma2（分母是 NEW sigma2）
      - 收敛或 sigma2 ≤ 1e-6 时输出 OLD mean/sigma（用作剔除基准的那对），不是 NEW

    max_iter 仅为安全保护，正常 5 次内收敛。整张图只算一对统计量，
    f32 精度已足够；用 mean/std + np.fabs(out=tmp) 复用 buffer 避免重复 alloc。
    """
    flat = np.asarray(data, dtype=np.float32).ravel()
    n = len(flat)
    if n < 2:
        return (float(flat[0]) if n == 1 else 0.0), 0.0

    avervalue = float(flat.mean())
    sigma = float(flat.std(ddof=1))

    tmp = np.empty_like(flat)
    for _ in range(max_iter):
        np.subtract(flat, np.float32(avervalue), out=tmp)
        np.fabs(tmp, out=tmp)
        mask = tmp <= np.float32(sigma_factor * sigma)
        clipped = flat[mask]
        k = clipped.size
        if k < 2:
            break

        avervalue2 = float(clipped.mean())
        sigma2 = float(clipped.std(ddof=1))

        # 退化：图像极平坦，直接输出 OLD
        if sigma2 <= 1e-6:
            break
        # 收敛：差异 < convergence * NEW sigma2，输出 OLD
        if abs(sigma2 - sigma) < convergence * sigma2:
            break

        avervalue = avervalue2
        sigma = sigma2

    return avervalue, sigma


def _median_filter_1d_bn(data, window, axis):
    """bottleneck.move_median 中心对齐版本。

    bottleneck 输出右对齐 lag（result[i] 是窗口 [i-w+1, i] 的中值），先对
    data 在该轴做 reflect padding 把窗口转成中心对齐，再切片回原尺寸。
    与 scipy.ndimage.median_filter(mode='reflect') 在内部像素逐位一致，
    边界处因 reflect 语义差异 ≤1 个像素的最小偏差。
    """
    pad_left = window // 2
    pad_right = window - 1 - pad_left
    pad_width = [(0, 0), (0, 0)]
    pad_width[axis] = (pad_left, pad_right)
    padded = np.pad(data, pad_width, mode="reflect")
    out = _bn.move_median(padded, window=window, axis=axis)
    sl = [slice(None), slice(None)]
    sl[axis] = slice(window - 1, window - 1 + data.shape[axis])
    return out[tuple(sl)].astype(data.dtype, copy=False)


def _median_filter_strip_threaded(data, kernel, n_threads):
    """带状核 (N,1) 或 (1,N) 沿正交方向切块多线程 median_filter。

    与单线程 median_filter(data, size=kernel) 逐位一致：带状核中每列（或每行）
    的中值仅依赖该列/行自身，沿正交方向切块不会改变任何参与排序的元素集合。
    scipy.ndimage 在 C 层释放 GIL，可真并行。

    n_threads<=1 或非带状核退化为单线程调用。
    """
    if n_threads <= 1:
        return median_filter(data, size=kernel)

    h, w = data.shape
    if kernel[0] > 1 and kernel[1] == 1:
        slices = np.array_split(np.arange(w), n_threads)
        out = np.empty_like(data)

        def _work(idx):
            j0, j1 = int(idx[0]), int(idx[-1]) + 1
            out[:, j0:j1] = median_filter(data[:, j0:j1], size=kernel)

        with ThreadPoolExecutor(max_workers=n_threads) as ex:
            list(ex.map(_work, [s for s in slices if s.size > 0]))
        return out

    if kernel[0] == 1 and kernel[1] > 1:
        slices = np.array_split(np.arange(h), n_threads)
        out = np.empty_like(data)

        def _work(idx):
            i0, i1 = int(idx[0]), int(idx[-1]) + 1
            out[i0:i1, :] = median_filter(data[i0:i1, :], size=kernel)

        with ThreadPoolExecutor(max_workers=n_threads) as ex:
            list(ex.map(_work, [s for s in slices if s.size > 0]))
        return out

    return median_filter(data, size=kernel)


def apply_superbkgd(data, bkgd0, med_length, med_width, bkgdmode,
                    median_impl="scipy", n_threads=1):
    """中值滤波后按 bkgdmode 扣除背景（1=除法归一化，2=减法扣除）。

    工作 dtype 收敛到 f32，bg 也是 f32。med_width>1 走竖窗口（kernel=(W,1)），
    否则走横窗口（kernel=(1,L)）。
    median_impl="bottleneck" 走 move_median；"scipy_threaded" 切块多线程；
    "scipy" 单线程兜底。非带状核（两维均>1）一律走 scipy。
    """
    data = np.asarray(data, dtype=np.float32)

    if med_width > 1:
        kernel = (med_width, 1)
    else:
        kernel = (1, med_length)
    banded = (kernel[0] == 1) ^ (kernel[1] == 1)

    if median_impl == "bottleneck" and banded:
        if not _HAS_BOTTLENECK:
            raise RuntimeError("median_impl='bottleneck' 但未安装 bottleneck。")
        window = kernel[0] if kernel[0] > 1 else kernel[1]
        axis = 0 if kernel[0] > 1 else 1
        bg = _median_filter_1d_bn(data, window, axis)
    elif median_impl == "scipy_threaded":
        bg = _median_filter_strip_threaded(data, kernel, n_threads).astype(np.float32, copy=False)
    elif median_impl == "scipy" or (median_impl == "bottleneck" and not banded):
        bg = median_filter(data, size=kernel).astype(np.float32, copy=False)
    else:
        raise ValueError(f"未知 median_impl: {median_impl!r}")

    if bkgdmode == 1:
        return data / bg * np.float32(bkgd0)
    else:
        return data - bg + np.float32(bkgd0)


def apply_smooth(data):
    """3×3 均值滤波轻微降噪（对应 enhance_flag=1）。"""
    return uniform_filter(data, size=3)


def label_connectivity_fortran(abox, naxis2, naxis1, EPS=1e-9):
    """三段式连通域标号（保留原算法的行为不变量）。

      Pass A: 首遍 4 邻居优先级标号（右上 > 正上 > 左上 > 左），
              用 elseif 链继承第一个非零邻居 label
      Pass B: 在 ±250 像素方框内就地合并水平相邻的不同 label
      Pass C: 8 邻接等价表 → 去重 → 简化合并 → 再去重 → 替换

    与 scipy 标准 8 连通的差异：Pass B 的 nr=250 局部合并属原算法特性，
    在简化合并失败的极少数复杂形状下，scipy 结果反而更稳健。

    注：Pass A 的循环上界用了 naxis1/naxis2 反置（原算法 bug），
    对方图 naxis1==naxis2 无影响，这里完整保留以匹配原行为。

    numba 可用时走 JIT 路径，否则回退到 Python list 兜底。
    """
    if _HAS_NUMBA:
        return _label_connectivity_fortran_numba(abox, naxis2, naxis1, EPS)
    return _label_connectivity_fortran_python(abox, naxis2, naxis1, EPS)


if _HAS_NUMBA:
    @_numba.njit(cache=True)
    def _pass_ab_numba(abox, naxis2, naxis1, EPS):
        idbox = np.zeros((naxis2, naxis1), dtype=np.int32)
        numobj = 0
        # Pass A：naxis1/naxis2 反置是原算法 bug，对方图无影响，完整保留
        for i in range(1, naxis1 - 1):
            for j in range(1, naxis2 - 1):
                v = abox[i, j]
                if v > EPS:
                    lty1 = abox[i - 1, j + 1]
                    lty2 = abox[i - 1, j]
                    lty3 = abox[i - 1, j - 1]
                    lty4 = abox[i, j - 1]
                    if lty1 + lty2 + lty3 + lty4 <= EPS:
                        numobj += 1
                        idbox[i, j] = numobj
                    elif lty1 > EPS:
                        idbox[i, j] = idbox[i - 1, j + 1]
                    elif lty2 > EPS:
                        idbox[i, j] = idbox[i - 1, j]
                    elif lty3 > EPS:
                        idbox[i, j] = idbox[i - 1, j - 1]
                    elif lty4 > EPS:
                        idbox[i, j] = idbox[i, j - 1]

        # Pass B：±nr=250 方框合并水平相邻的不同 label
        nr = 250
        for i in range(1, naxis2 - 1):
            for j in range(naxis1 - 2, 0, -1):
                if abox[i, j] > EPS and abox[i, j - 1] > EPS:
                    lab_left = idbox[i, j - 1]
                    lab_cur = idbox[i, j]
                    if lab_cur != lab_left:
                        ni1 = i - nr if i - nr > 0 else 0
                        ni2 = i + nr if i + nr < naxis2 - 1 else naxis2 - 1
                        nj1 = j - nr if j - nr > 0 else 0
                        nj2 = j + nr if j + nr < naxis1 - 1 else naxis1 - 1
                        for i1 in range(ni1, ni2 + 1):
                            if i1 == i:
                                continue
                            for j1 in range(nj1, nj2 + 1):
                                if j1 == j - 1:
                                    continue
                                if idbox[i1, j1] == lab_left:
                                    idbox[i1, j1] = lab_cur
                        idbox[i, j - 1] = lab_cur
        return idbox

    @_numba.njit(cache=True)
    def _pass_c_count_numba(abox, idbox2, naxis2, naxis1, EPS):
        count = 0
        for i in range(1, naxis2 - 1):
            for j in range(1, naxis1 - 1):
                if abox[i, j] > EPS:
                    cur = idbox2[i, j]
                    # 邻居顺序：左、右、左上、上、右上、左下、下、右下
                    for kk in range(8):
                        if kk == 0:
                            nb = idbox2[i, j - 1]
                        elif kk == 1:
                            nb = idbox2[i, j + 1]
                        elif kk == 2:
                            nb = idbox2[i - 1, j - 1]
                        elif kk == 3:
                            nb = idbox2[i - 1, j]
                        elif kk == 4:
                            nb = idbox2[i - 1, j + 1]
                        elif kk == 5:
                            nb = idbox2[i + 1, j - 1]
                        elif kk == 6:
                            nb = idbox2[i + 1, j]
                        else:
                            nb = idbox2[i + 1, j + 1]
                        if cur != nb and nb > 0:
                            count += 1
        return count

    @_numba.njit(cache=True)
    def _pass_c_fill_numba(abox, idbox2, naxis2, naxis1, EPS, pairs):
        count = 0
        for i in range(1, naxis2 - 1):
            for j in range(1, naxis1 - 1):
                if abox[i, j] > EPS:
                    cur = idbox2[i, j]
                    for kk in range(8):
                        if kk == 0:
                            nb = idbox2[i, j - 1]
                        elif kk == 1:
                            nb = idbox2[i, j + 1]
                        elif kk == 2:
                            nb = idbox2[i - 1, j - 1]
                        elif kk == 3:
                            nb = idbox2[i - 1, j]
                        elif kk == 4:
                            nb = idbox2[i - 1, j + 1]
                        elif kk == 5:
                            nb = idbox2[i + 1, j - 1]
                        elif kk == 6:
                            nb = idbox2[i + 1, j]
                        else:
                            nb = idbox2[i + 1, j + 1]
                        if cur != nb and nb > 0:
                            if cur < nb:
                                pairs[count, 0] = cur
                                pairs[count, 1] = nb
                            else:
                                pairs[count, 0] = nb
                                pairs[count, 1] = cur
                            count += 1


def _label_connectivity_fortran_numba(abox, naxis2, naxis1, EPS):
    """numba JIT 实现：Pass A/B + Pass C 步骤 1 numba 化；
    步骤 2-4（pair 去重 / 简化合并 / 再去重）在 Python 上做（典型 100 对量级，
    Python set 已足够快）；步骤 5 用 numpy 向量化替换。"""
    abox = np.ascontiguousarray(abox)
    idbox2 = _pass_ab_numba(abox, naxis2, naxis1, EPS)

    n_raw = _pass_c_count_numba(abox, idbox2, naxis2, naxis1, EPS)
    if n_raw == 0:
        return idbox2

    pairs_arr = np.empty((n_raw, 2), dtype=np.int32)
    _pass_c_fill_numba(abox, idbox2, naxis2, naxis1, EPS, pairs_arr)

    # 步骤 2：去重，保首次出现顺序
    seen = set()
    pairs2 = []
    for k in range(n_raw):
        tup = (int(pairs_arr[k, 0]), int(pairs_arr[k, 1]))
        if tup not in seen:
            seen.add(tup)
            pairs2.append(tup)

    # 步骤 3：简化合并（单遍扫描，保留原算法语义——在罕见复杂形状下会合并不完整）
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

    # 步骤 5：按 pair 顺序把 idbox2 中的 e2 替换为 e1
    if pairs4:
        mask_pos = abox > EPS
        for e1, e2 in pairs4:
            replace_mask = (idbox2 == e2) & mask_pos
            if replace_mask.any():
                idbox2[replace_mask] = e1

    return idbox2


def _label_connectivity_fortran_python(abox, naxis2, naxis1, EPS=1e-9):
    """三段式连通域标号（Python list 实现，作为 numba 不可用时的兜底）。"""
    abox_l = abox.tolist()

    # ── Pass A：4 邻居优先级标号 ──────────────────────────────────────────
    idbox = [[0] * naxis1 for _ in range(naxis2)]
    numobj = 0
    for i in range(1, naxis1 - 1):
        row_im1 = abox_l[i - 1]
        row_i = abox_l[i]
        idbox_im1 = idbox[i - 1]
        idbox_i = idbox[i]
        for j in range(1, naxis2 - 1):
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

    idbox2 = np.array(idbox, dtype=np.int32)

    # ── Pass B：±250 像素方框内合并水平相邻的不同 label ───────────────────
    nr = 250
    for i in range(1, naxis2 - 1):
        row_abox_i = abox_l[i]
        for j in range(naxis1 - 2, 0, -1):
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
                    # 排除整行 i 与整列 j-1（原条件 i1≠i AND j1≠j-1）
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

    # ── Pass C：8 邻接等价表合并 ──────────────────────────────────────────
    # 步骤 1：扫每个 >0 像素，记录与 8 邻居中不同 label 的等价对 (min, max)
    # 邻居顺序：左、右、左上、上、右上、左下、下、右下
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
    # 合并不完整——但行为与原算法一致，scipy 路径可绕开此限制）
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
    """scipy 标准 8 连通标号（不含 nr=250 子区域合并）。

    与 fortran 路径在算法上等价，但 scipy 用严格 Union-Find，
    在 fortran 简化单遍合并可能不完整的复杂形状下更稳健。
    naxis1 仅为签名一致而保留；返回 int32 标号矩阵。
    """
    structure = generate_binary_structure(2, 2)
    labels, _ = ndimage_label(abox > EPS, structure=structure)
    return labels.astype(np.int32)


def detect_stars_by_moments(
    data, bkgd_threshold, pos_method, bitpix=16, connectivity="fortran"
):
    """连通域星象检测 + 修正矩定中心，返回 (按亮度降序的星表, bkgd, bkgdsigma)。

    bitpix 用于动态计算饱和阈值 maxflux=2**bitpix-1（仅整型 FITS 有效）。
    connectivity="fortran" 走完整三段式（含 nr=250 合并），"scipy" 走标准
    8 连通。每颗星 dict：starx/stary/sumi/snr/star_id/star_pix/overflag。
    """
    naxis2, naxis1 = data.shape  # FITS 标准：data.shape[0]=NAXIS2(行), [1]=NAXIS1(列)

    # maxflux：2**bitpix-1 仅对整型 FITS（BITPIX>0）有意义；
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
    v_inner = abox[9:naxis2 - 10, 9:naxis1 - 10]
    v0_inner = abox0[9:naxis2 - 10, 9:naxis1 - 10]
    lab_inner = idbox2[9:naxis2 - 10, 9:naxis1 - 10]
    ih, iw = v_inner.shape

    # 求和用 f64 累加，避免大量浮点累加带来的精度漂移
    v_flat = v_inner.ravel().astype(np.float64, copy=False)
    v0_flat = v0_inner.ravel()
    lab_flat = lab_inner.ravel().astype(np.int64, copy=False)
    rr_flat = np.broadcast_to(
        (np.arange(ih, dtype=np.float64) + 10.0).reshape(-1, 1), (ih, iw)
    ).ravel()
    cc_flat = np.broadcast_to(
        (np.arange(iw, dtype=np.float64) + 10.0).reshape(1, -1), (ih, iw)
    ).ravel()

    if pos_method == 1:
        vp_flat = v_flat
    else:
        vp_flat = v_flat**pos_method

    mask = lab_flat > 0
    n_labels = int(lab_inner.max()) if mask.any() else 0
    minlen = n_labels + 1

    lab_used = lab_flat[mask]
    vp_used = vp_flat[mask]
    sumx_arr = np.bincount(lab_used, weights=cc_flat[mask] * vp_used, minlength=minlen)
    sumy_arr = np.bincount(lab_used, weights=rr_flat[mask] * vp_used, minlength=minlen)
    sumi_arr = np.bincount(lab_used, weights=vp_used, minlength=minlen)
    sumi_real_arr = np.bincount(lab_used, weights=v_flat[mask], minlength=minlen)
    numpix_arr = np.bincount(lab_used, minlength=minlen)

    # overflag：保留原行为——lab=0 处达到 maxflux 也会标 overflag[0]=1
    # （下游 sorted(numpix.keys()) 不含 0，故对结果无害）。
    overflag_arr = np.zeros(minlen, dtype=np.int32)
    overflag_mask = v0_flat >= maxflux
    if overflag_mask.any():
        labs_over = np.unique(lab_flat[overflag_mask])
        if labs_over.size and labs_over.max() < minlen:
            overflag_arr[labs_over] = 1

    detected_stars = []
    bkgdsigma_sq = bkgdsigma ** 2
    for lab in range(1, minlen):
        n = int(numpix_arr[lab])
        if not (minpix <= n <= maxpix):
            continue
        s_i = float(sumi_arr[lab])
        if s_i < 1e-9:
            continue
        sumi_real = float(sumi_real_arr[lab])
        denom = np.sqrt(sumi_real + n * bkgdsigma_sq)
        snr = sumi_real / denom if denom > 0 else 0.0
        detected_stars.append(
            {
                "starx": float(sumx_arr[lab]) / s_i,
                "stary": float(sumy_arr[lab]) / s_i,
                "sumi": sumi_real,
                "snr": float(snr),
                "star_id": lab,
                "star_pix": n,
                "overflag": 1 if overflag_arr[lab] >= 1 else 0,
            }
        )

    detected_stars.sort(key=lambda s: s["sumi"], reverse=True)
    return detected_stars, bkgd, bkgdsigma


def homomorphic_filter(data, gamma_low=0.2, gamma_high=3.5, cutoff=50, c=0.5):
    """同态滤波：对数域高斯高通压低频光照、增强高频细节。

    gamma_low<1 压背景，gamma_high>1 增细节，cutoff 截止频率（像素）。
    输出灰度值域恢复到与输入一致。
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
    """双边 Retinex：对数域双边滤波分离 (反射, 光照) 分量。

    输出已分别归一化回原始 ADU 值域。d 为双边滤波邻域直径。
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

    def _norm_to_range(arr, target_max):
        a_min, a_max = arr.min(), arr.max()
        if a_max - a_min < 1e-9:
            return arr
        return (arr - a_min) / (a_max - a_min) * target_max

    reflectance = _norm_to_range(reflectance, max_val)
    illumination = _norm_to_range(illumination, max_val)

    return reflectance, illumination
