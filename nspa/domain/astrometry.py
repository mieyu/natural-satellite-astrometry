"""天文测量领域算法：坐标变换、底片常数解算、视场恒星筛选。

实现要点：
  - 角度统一以弧度参与三角运算；DEG2RAD 为度→弧度换算常数。
  - 底片常数模型阶数 nm ∈ {6, 12, 20, 30}；ksi/yit 各占一半。
  - 最小二乘解算迭代剔除残差超过 2.6σ 的观测对，最多 30 次。
"""

import numpy as np

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
                    p[off+10]*x**4 + p[off+11]*x**3*y + p[off+12]*x**2*y**2 +
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
                   xi**4, xi**3*yi, xi**2*yi**2, xi*yi**3, yi**4]
        else:
            raise ValueError(f"不支持的底片模型：{nm}")
        A[2*i,   :h] = row
        A[2*i+1, h:] = row
    return A


def least_squares(A, Y, K, n):
    """列缩放后的 SVD 最小二乘，保留原坐标下的底片常数。

    剔除残差超过 2.6σ 的观测对，最多迭代 30 次。
    缩放矩阵的奇异值比低于 1e-10 时拒绝解算，避免病态解进入后续归算。
    返回 (par, sigma, n_used)；数据不足或退化时抛出 LinAlgError。
    """
    A = np.asarray(A, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64).reshape(-1)
    if A.shape != (2 * n, K) or Y.shape != (2 * n,):
        raise ValueError("底片解算矩阵与观测数据维度不一致")
    if not np.isfinite(A).all() or not np.isfinite(Y).all():
        raise np.linalg.LinAlgError("底片解算含非有限值")
    keep = np.ones(n, dtype=bool)
    previous_sigma = None
    for iteration in range(30):
        rows = np.repeat(keep, 2)
        used = int(keep.sum())
        if 2 * used <= K:
            raise np.linalg.LinAlgError(
                f"有效参考星不足：{used} 颗，{K} 参数模型需至少 {K // 2 + 1} 颗以估计残差")
        active = A[rows]
        scales = np.linalg.norm(active, axis=0)
        if np.any(scales == 0) or not np.isfinite(scales).all():
            raise np.linalg.LinAlgError("底片矩阵退化：存在零列或无效列")
        coefficients, _, rank, singular = np.linalg.lstsq(
            active / scales, Y[rows], rcond=1e-10)
        if rank < K:
            raise np.linalg.LinAlgError(
                f"底片矩阵病态或秩不足：秩 {rank}/{K}，"
                f"缩放后奇异值比 {singular[-1] / singular[0]:.3e}；请检查参考星分布及匹配")
        X = coefficients / scales
        V = A @ X - Y
        sigma = float(np.linalg.norm(V[rows]) / np.sqrt(2 * used - K))
        # 精确拟合的舍入误差不应触发剔星，尤其不能在 sigma=0 时剔除全部星。
        roundoff = 64 * np.finfo(float).eps * max(
            float(np.max(np.abs(Y[rows]))), np.finfo(float).tiny)
        if (sigma <= roundoff or iteration == 29 or
                (previous_sigma is not None and
                 abs(sigma - previous_sigma) < 0.01 * previous_sigma)):
            break
        next_keep = np.all(np.abs(V.reshape(n, 2)) < 2.6 * sigma, axis=1)
        if np.array_equal(next_keep, keep):
            break
        previous_sigma = sigma
        keep = next_keep
    return X, sigma, used


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
