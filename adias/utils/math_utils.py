# 功能：天文数学工具函数（坐标变换、底片常数解算、拉格朗日插值等）。
# 使用：from adias.utils.math_utils import (
#           cal_rl, interpolate, extract_field_stars,
#           rade2ky, rade2xieta, xy2rade, xieta2xy,
#           sol_par, am2hms, print_par)

import numpy as np
import math
from scipy.linalg import inv

Q = np.pi / 180.0       # 角度 -> 弧度换算常数


# ─────────────────────────────────────────────
# 球面几何
# ─────────────────────────────────────────────

def cal_rl(ra1, dec1, ra2, dec2):
    """
    计算两点之间的大圆弧长（弧度）。
    输入均为弧度。
    """
    cos_rl = (np.sin(dec1) * np.sin(dec2) +
              np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
    return np.arccos(np.clip(cos_rl, -1.0, 1.0))


def interpolate(x, y, n, t):
    """
    拉格朗日插值（对应 Fortran ENLGR 子程序）。

    Parameters
    ----------
    x, y : np.ndarray，已知节点
    n    : int，节点数
    t    : float，插值点

    Returns
    -------
    float，插值结果
    """
    if n <= 0:
        return 0.0
    if n == 1:
        return float(y[0])
    if n == 2:
        return (y[0] * (t - x[1]) - y[1] * (t - x[0])) / (x[0] - x[1])

    i = 1
    while i < n and x[i] < t:
        i += 1
    k = max(0, i - 4)
    m = min(n - 1, i + 3)

    z = 0.0
    for i in range(k, m + 1):
        s = 1.0
        for j in range(k, m + 1):
            if j != i:
                s *= (t - x[j]) / (x[i] - x[j])
        z += s * y[i]
    return z


def extract_field_stars(gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag, n_gaia,
                        obj_ra, obj_de, fsize, epoch):
    """
    从 GAIA 全天星表中截取视场内参考星并进行自行改正。

    Parameters
    ----------
    gaia_* : np.ndarray，全天星表数组
    n_gaia : int，星表总数
    obj_ra, obj_de : float，目标赤经赤纬（度）
    fsize  : int，视场半宽（角分）
    epoch  : float，观测历元（年）

    Returns
    -------
    n_field, ra, de, mag : int, np.ndarray x3
    """
    ra, de, mag = [], [], []
    hw = fsize / 60.0       # 半宽，转换为度
    for i in range(n_gaia):
        if (obj_ra - hw < gaia_ra[i] < obj_ra + hw and
                obj_de - hw < gaia_de[i] < obj_de + hw):
            dt = epoch - 2016.0
            de_c = gaia_de[i] + dt * gaia_pd[i] / 3.6e6
            ra_c = gaia_ra[i] + dt * gaia_pr[i] / 3.6e6 / np.cos(de_c * Q)
            ra.append(ra_c)
            de.append(de_c)
            mag.append(gaia_mag[i])
    n = len(ra)
    return n, np.array(ra), np.array(de), np.array(mag)


# ─────────────────────────────────────────────
# 坐标变换
# ─────────────────────────────────────────────

def rade2ky(ra, de, ra0, de0):
    """
    赤道坐标 -> 理想坐标（ksi, yit）。
    输入均为弧度，输出为无量纲理想坐标。
    """
    ksi = np.cos(de) * np.sin(ra - ra0) / (
          np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0))
    yit = (np.sin(de) * np.cos(de0) - np.cos(de) * np.sin(de0) * np.cos(ra - ra0)) / (
          np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0))
    return ksi, yit


def rade2xieta(ra, de, ra0, de0):
    """
    赤道坐标 -> 理想坐标（xi, eta），另一种实现。
    输入均为弧度。
    """
    a = np.cos(de) * np.sin(ra - ra0)
    b = np.cos(de0) * np.sin(de) - np.sin(de0) * np.cos(de) * np.cos(ra - ra0)
    c = np.sin(de0) * np.sin(de) + np.cos(de0) * np.cos(de) * np.cos(ra - ra0)
    return a / c, b / c


def xy2rade(par, nm, x, y, ra0, de0):
    """
    量度坐标 (x, y) -> 赤道坐标 (ra, de)（弧度）。
    par 为底片常数数组，nm 为模型阶数（6/12/20/30）。
    """
    def _poly(p, off):
        if nm == 6:
            return p[off] * x + p[off+1] * y + p[off+2]
        if nm == 12:
            return (p[off]*x + p[off+1]*y + p[off+2] +
                    p[off+3]*x**2 + p[off+4]*x*y + p[off+5]*y**2)
        if nm == 20:
            return (p[off]*x + p[off+1]*y + p[off+2] +
                    p[off+3]*x**2 + p[off+4]*x*y + p[off+5]*y**2 +
                    p[off+6]*x**3 + p[off+7]*x**2*y + p[off+8]*x*y**2 + p[off+9]*y**3)
        if nm == 30:
            return (p[off]*x + p[off+1]*y + p[off+2] +
                    p[off+3]*x**2 + p[off+4]*x*y + p[off+5]*y**2 +
                    p[off+6]*x**3 + p[off+7]*x**2*y + p[off+8]*x*y**2 + p[off+9]*y**3 +
                    p[off+10]*y**4 + p[off+11]*x**3*y + p[off+12]*x**2*y**2 +
                    p[off+13]*x*y**3 + p[off+14]*y**4)
        return 0.0

    half = nm // 2
    ksi = _poly(par, 0)
    yit = _poly(par, half)

    tand1 = ksi / np.cos(de0) / (1.0 - yit * np.tan(de0))
    ra = ra0 + np.arctan(tand1)
    tand2 = (yit + np.tan(de0)) * np.cos(np.arctan(tand1)) / (1.0 - yit * np.tan(de0))
    de = np.arctan(tand2)
    return ra, de


def xieta2xy(xi, eta, par):
    """
    理想坐标 (xi, eta) -> 量度坐标 (x, y)，仅使用 par 前 6 个线性参数。
    """
    a, b, c, d, e, f = par[0], par[1], par[2], par[3], par[4], par[5]
    denom = a * e - b * d
    if abs(denom) < 1e-10:
        return 0.0, 0.0
    sx = (e * xi - b * eta + b * f - c * e) / denom
    sy = (d * xi - a * eta + a * f - c * d) / (b * d - a * e)
    return sx, sy


# ─────────────────────────────────────────────
# 底片常数解算
# ─────────────────────────────────────────────

def _build_design_matrix(x, y, n, nm):
    """构造设计矩阵 A（内部函数）。"""
    A = np.zeros((2 * n, nm))
    h = nm // 2
    for i in range(n):
        xi, yi = x[i], y[i]
        if nm == 6:
            row = [xi, yi, 1.0]
        elif nm == 12:
            row = [xi, yi, 1.0, xi**2, xi*yi, yi**2]
        elif nm == 20:
            row = [xi, yi, 1.0, xi**2, xi*yi, yi**2,
                   xi**3, xi**2*yi, xi*yi**2, yi**3]
        elif nm == 30:
            row = [xi, yi, 1.0, xi**2, xi*yi, yi**2,
                   xi**3, xi**2*yi, xi*yi**2, yi**3,
                   yi**4, xi**3*yi, xi**2*yi**2, xi*yi**3, yi**4]
        else:
            row = []
        A[2*i,   :h] = row
        A[2*i+1, h:] = row
    return A


def least_squares(A, Y, K, n):
    """
    带权迭代最小二乘（对应 Fortran LEAST + MATINV 子程序）。
    剔除残差超过 2.6σ 的观测对，最多迭代 30 次。

    Returns
    -------
    par   : np.ndarray，底片常数
    sig0  : float，归算 sigma（弧度）
    nused : int，有效使用星数
    """
    NE, SFA, SFB = 2 * n, 2.6, 0.01
    P = np.ones(NE)
    SITA20, NBIG, ILOOP = 0.0, 0, 0

    while True:
        ILOOP += 1
        NEP = NE - NBIG * 2
        AT = A.T.copy()
        for i in range(NE):
            AT[:, i] *= P[i]
        try:
            X = inv(AT @ A) @ AT @ Y
        except Exception:
            return np.zeros(K), 0.0, 0

        V = A @ X - Y
        SITA2 = np.sqrt(sum(V[i, 0]**2 * P[i] for i in range(NE)) / max(NEP - K, 1)) if NEP != K else 0.0

        if abs(SITA2 - SITA20) >= SFB * SITA20 and ILOOP <= 30:
            SITA20 = SITA2
            NBIG = 0
            P = np.ones(NE)
            for i in range(1, NE, 2):
                if abs(V[i, 0]) >= SFA * SITA2 or abs(V[i-1, 0]) >= SFA * SITA2:
                    P[i-1] = P[i] = 0.0
                    NBIG += 1
        else:
            break
        if ILOOP > 30:
            break

    return X.flatten(), SITA2, NE // 2 - NBIG


def sol_par(x, y, ra, de, n, ra0, de0, nm):
    """
    解算底片常数。

    Parameters
    ----------
    x, y   : np.ndarray，量度坐标
    ra, de : np.ndarray，参考星赤经赤纬（度）
    n      : int，参考星数
    ra0, de0 : float，视场中心（度）
    nm     : int，模型阶数

    Returns
    -------
    par  : np.ndarray
    sig0 : float，sigma（弧度）
    nused: int
    """
    ksi = np.zeros(n)
    yit = np.zeros(n)
    for i in range(n):
        ksi[i], yit[i] = rade2ky(ra[i] * Q, de[i] * Q, ra0 * Q, de0 * Q)

    A = _build_design_matrix(x, y, n, nm)
    C = np.zeros((2 * n, 1))
    for i in range(n):
        C[2*i,   0] = ksi[i]
        C[2*i+1, 0] = yit[i]

    return least_squares(A, C, nm, n)


# ─────────────────────────────────────────────
# 格式化输出
# ─────────────────────────────────────────────

def am2hms(ra_arcmin, de_arcmin):
    """
    赤经赤纬（角分）-> 时分秒 / 度分秒。

    Parameters
    ----------
    ra_arcmin : float，赤经（角分）
    de_arcmin : float，赤纬（角分）

    Returns
    -------
    hh, mm, ss, sign, ddd, dmm, dss
    """
    hh  = int(ra_arcmin / 60.0 / 15.0)
    mm  = int((ra_arcmin - hh * 900.0) / 15.0)
    ss  = (ra_arcmin - hh * 900.0 - mm * 15.0) * 4.0

    sign = '+' if de_arcmin >= 0 else '-'
    de1  = abs(de_arcmin)
    ddd  = int(de1 / 60.0)
    dmm  = int(de1 - ddd * 60.0)
    dss  = (de1 - ddd * 60.0 - dmm) * 60.0
    return hh, mm, ss, sign, ddd, dmm, dss


def print_par(par, modeltype):
    """打印底片常数。"""
    print(f'...底片常数（{modeltype}项）：', end='')
    for i in range(modeltype):
        print(f'{par[i]:10.4f}', end='')
    print()

def initial_stats(res_ra, res_de):
    """O-C 残差的原始均值/标准差。样本数 < 2 时一律返回 999.999 占位。"""
    n = len(res_ra)
    if n < 2:
        return 999.999, 999.999, 999.999, 999.999
    m_ra = sum(res_ra) / n
    m_de = sum(res_de) / n
    s_ra = math.sqrt(sum((v - m_ra) ** 2 for v in res_ra) / (n - 1))
    s_de = math.sqrt(sum((v - m_de) ** 2 for v in res_de) / (n - 1))
    return m_ra, m_de, s_ra, s_de


def sigma_clip_oc(res_ra, res_de, lines, oc_limit, mean_limit, eps):
    """
    迭代剔除 O-C 野值，对应 Fortran comoc 核心循环。

    剔除策略
    --------
    - oc_limit > 0：按 |data - mean| < oc_limit * sigma 且 |data| < eps 剔除；
    - oc_limit == 0：按 |data - mean| < mean_limit 剔除。

    Parameters
    ----------
    res_ra, res_de : list[float]，O-C 残差（角秒）
    lines          : list[str]，与残差一一对应的原始行文本
    oc_limit       : float，sigma 倍数阈值（0 表示使用 mean_limit 模式）
    mean_limit     : float，绝对残差阈值
    eps            : float，残差绝对值上限

    Returns
    -------
    new_lines  : list[str]，剔除后保留的行
    new_ra     : list[float]
    new_de     : list[float]
    mean_ra    : float，剔除后均值
    mean_de    : float
    std_ra     : float，剔除后标准差
    std_de     : float
    iloop      : int，迭代次数
    """
    cur_ra = list(res_ra)
    cur_de = list(res_de)
    cur_lines = list(lines)
    n = len(cur_ra)
    iloop = 0

    def _stats(ra_arr, de_arr):
        k = len(ra_arr)
        if k == 0:
            return 0.0, 0.0, 0.0, 0.0
        m_ra = sum(ra_arr) / k
        m_de = sum(de_arr) / k
        if k > 1:
            s_ra = math.sqrt(sum((v - m_ra)**2 for v in ra_arr) / (k - 1))
            s_de = math.sqrt(sum((v - m_de)**2 for v in de_arr) / (k - 1))
        else:
            s_ra = s_de = 0.0
        return m_ra, m_de, s_ra, s_de

    mean_ra, mean_de, std_ra, std_de = _stats(cur_ra, cur_de)

    while True:
        iloop += 1
        new_ra, new_de, new_lines = [], [], []

        for i in range(len(cur_ra)):
            ra_i, de_i = cur_ra[i], cur_de[i]
            if oc_limit > 0.0:
                keep = (abs(ra_i - mean_ra) < oc_limit * std_ra and
                        abs(de_i - mean_de) < oc_limit * std_de and
                        abs(ra_i) < eps and abs(de_i) < eps)
            else:
                keep = (abs(ra_i - mean_ra) < mean_limit and
                        abs(de_i - mean_de) < mean_limit)
            if keep:
                new_ra.append(ra_i)
                new_de.append(de_i)
                new_lines.append(cur_lines[i])

        mean_ra, mean_de, std_ra, std_de = _stats(new_ra, new_de)

        if len(new_ra) >= len(cur_ra):   # 无变化，收敛
            break
        cur_ra, cur_de, cur_lines = new_ra, new_de, new_lines

    return new_lines, new_ra, new_de, mean_ra, mean_de, std_ra, std_de, iloop