"""天文测量领域算法：坐标变换、底片常数解算、视场恒星筛选。

实现要点：
  - 角度统一以弧度参与三角运算；DEG2RAD 为度→弧度换算常数。
  - 底片常数模型阶数 nm ∈ {6, 12, 20, 30}；ksi/yit 各占一半。
  - 最小二乘解算迭代剔除残差超过 2.6σ 的观测对，最多 30 次。
"""

import numpy as np
from scipy.linalg import inv

from nspa.application.log import get_logger

DEG2RAD = np.pi / 180.0

_log = get_logger("astrometry")


# ── 球面几何 ──────────────────────────────────────────────────────────────

def cal_rl(ra1, dec1, ra2, dec2):
    """大圆弧长（弧度）。输入均为弧度。"""
    cosrl = (np.sin(dec1) * np.sin(dec2) +
             np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
    cosrl = max(-1.0, min(1.0, cosrl))
    return np.arccos(cosrl)


# ── 视场恒星筛选（含自行改正） ────────────────────────────────────────────

def extract_field_stars(gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag, n_gaia,
                        obj_ra, obj_de, fsize, epoch):
    """从全天星表截取以 (obj_ra, obj_de) 为中心、fsize 角分为半宽的方框内参考星，
    并按 GAIA 自行参数把位置改正到观测历元。
    """
    ra, de, mag = [], [], []
    hw = fsize / 60.0
    for i in range(n_gaia):
        if (obj_ra - hw < gaia_ra[i] < obj_ra + hw and
                obj_de - hw < gaia_de[i] < obj_de + hw):
            dt = epoch - 2016.0
            de_c = gaia_de[i] + dt * gaia_pd[i] / 3.6e6
            ra_c = gaia_ra[i] + dt * gaia_pr[i] / 3.6e6 / np.cos(de_c * DEG2RAD)
            ra.append(ra_c)
            de.append(de_c)
            mag.append(gaia_mag[i])
    n = len(ra)
    return n, np.array(ra), np.array(de), np.array(mag)


# ── 坐标变换 ──────────────────────────────────────────────────────────────

def rade2ky(ra, de, ra0, de0):
    """赤道坐标 → 理想坐标 (ksi, yit)。输入均为弧度。"""
    ksi = np.cos(de) * np.sin(ra - ra0) / (
          np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0))
    yit = (np.sin(de) * np.cos(de0) - np.cos(de) * np.sin(de0) * np.cos(ra - ra0)) / (
          np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0))
    return ksi, yit


def rade2xieta(ra, de, ra0, de0):
    """赤道坐标 → 理想坐标 (xi, eta)，另一种实现。"""
    a = np.cos(de) * np.sin(ra - ra0)
    b = np.cos(de0) * np.sin(de) - np.sin(de0) * np.cos(de) * np.cos(ra - ra0)
    c = np.sin(de0) * np.sin(de) + np.cos(de0) * np.cos(de) * np.cos(ra - ra0)
    return a / c, b / c


def xy2rade(par, nm, x, y, ra0, de0):
    """量度坐标 (x, y) → 赤道坐标 (ra, de)（弧度）。par 长度需 ≥ nm。"""
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
    """理想坐标 (xi, eta) → 量度坐标 (x, y)；仅使用 par 前 6 项线性参数。"""
    a, b, c, d, e, f = par[0], par[1], par[2], par[3], par[4], par[5]
    denom = a * e - b * d
    if abs(denom) < 1e-10:
        return 0.0, 0.0
    sx = (e * xi - b * eta + b * f - c * e) / denom
    sy = (d * xi - a * eta + a * f - c * d) / (b * d - a * e)
    return sx, sy


# ── 底片常数解算 ──────────────────────────────────────────────────────────

def _build_design_matrix(x, y, n, nm):
    """构造 2n×nm 设计矩阵 A。"""
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
    """带权迭代最小二乘（对应 Fortran LEAST+MATINV）。

    剔除残差超过 2.6σ 的观测对，最多迭代 30 次。
    Returns (par, sigma, n_used)。
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
    """解算底片常数；返回 (par, sigma_rad, n_used)。"""
    ksi = np.zeros(n)
    yit = np.zeros(n)
    for i in range(n):
        ksi[i], yit[i] = rade2ky(ra[i] * DEG2RAD, de[i] * DEG2RAD, ra0 * DEG2RAD, de0 * DEG2RAD)

    A = _build_design_matrix(x, y, n, nm)
    C = np.zeros((2 * n, 1))
    for i in range(n):
        C[2*i,   0] = ksi[i]
        C[2*i+1, 0] = yit[i]

    return least_squares(A, C, nm, n)


# ── 调试输出 ──────────────────────────────────────────────────────────────

def print_par(par, modeltype):
    parts = "".join(f"{par[i]:10.4f}" for i in range(modeltype))
    _log.info(f"...底片常数（{modeltype}项）：{parts}")
