"""匹配领域算法：单幅图像内的盲搜匹配与 prepar 复用。

对外接口：
  - find_obj_base_angle(...)  → MatchResult   全力盲搜（首目标 / 底片常数解算）
  - find_obj_base_prepar(...) → MatchResult   复用底片常数（同图后续目标）

本模块纯算法 + MatchResult 进出，不涉及 StepResult / 文件 I/O。

阶段一粗匹配与阶段三全图匹配默认走 KDTree 矢量化快路径：
GAIA 参考星投影到 tangent-plane 一次性建树，检测星批量半径查询；
半径放大 1% 容投影误差，候选再用 cal_rl 严格复核，候选集合与暴力实现一致。
快路径异常或未给出 ≥3 匹配时自动回退暴力实现。
"""

import numpy as np
from scipy.spatial import cKDTree

from nspa.application.log import get_logger
from nspa.domain.astrometry import (
    DEG2RAD,
    cal_rl,
    rade2xieta,
    sol_par,
    xieta2xy,
    xy2rade,
)
from nspa.domain.models import MatchResult

_log = get_logger("matching")

# KDTree 半径放大系数：小角近似下 tangent-plane Euclidean ≈ 角距，
# 1% 余量足够覆盖投影误差，候选再用 cal_rl 严格复核。
_KDTREE_RADIUS_INFLATE = 1.01


# ── 内部 helper ───────────────────────────────────────────────────────────

def _empty_result(n_match1=0, par1=None, x_cen=0.0, y_cen=0.0, ra_cen=0.0, de_cen=0.0):
    """构造默认/失败时的 MatchResult，参考星数组按 0 长创建。"""
    return MatchResult(
        n_match1=n_match1,
        par1=par1 if par1 is not None else np.zeros(30),
        x_center=x_cen,
        y_center=y_cen,
        ra_center=ra_cen,
        de_center=de_cen,
        ref_x=np.zeros(0),
        ref_y=np.zeros(0),
        ref_ra=np.zeros(0),
        ref_de=np.zeros(0),
        ref_mag=np.zeros(0),
    )


def _initial_plate_par(field_angle):
    """初始底片常数：仅含旋转角 par(1)=cos par(2)=sin par(4)=-sin par(5)=cos。"""
    ca, sa = np.cos(field_angle * DEG2RAD), np.sin(field_angle * DEG2RAD)
    par_init = np.zeros(30)
    par_init[0], par_init[1] = ca, sa
    par_init[3], par_init[4] = -sa, ca
    return par_init


def _rade2ky_vec(ra, de, ra0, de0):
    """rade2ky 矢量版本，所有输入为弧度，返回 (ksi, eta) 数组。"""
    sin_de = np.sin(de)
    cos_de = np.cos(de)
    sin_de0 = np.sin(de0)
    cos_de0 = np.cos(de0)
    sin_dra = np.sin(ra - ra0)
    cos_dra = np.cos(ra - ra0)
    denom = sin_de * sin_de0 + cos_de * cos_de0 * cos_dra
    ksi = cos_de * sin_dra / denom
    eta = (sin_de * cos_de0 - cos_de * sin_de0 * cos_dra) / denom
    return ksi, eta


def _xy2rade_linear_vec(par6, x, y, ra0, de0):
    """xy2rade 矢量版（nm=6 线性模型），ra0/de0 为弧度，x/y 为数组。"""
    ksi = par6[0] * x + par6[1] * y + par6[2]
    eta = par6[3] * x + par6[4] * y + par6[5]
    tand1 = ksi / np.cos(de0) / (1.0 - eta * np.tan(de0))
    ra = ra0 + np.arctan(tand1)
    tand2 = (eta + np.tan(de0)) * np.cos(np.arctan(tand1)) / (1.0 - eta * np.tan(de0))
    de = np.arctan(tand2)
    return ra, de


def _xy2rade_poly_vec(par, nm, x, y, ra0, de0):
    """xy2rade 矢量版，支持 nm in {6,12,20}；其他阶数回退到逐点 xy2rade。"""
    half = nm // 2

    def _poly(off):
        if nm == 6:
            return par[off] * x + par[off + 1] * y + par[off + 2]
        if nm == 12:
            return (par[off] * x + par[off + 1] * y + par[off + 2]
                    + par[off + 3] * x * x + par[off + 4] * x * y + par[off + 5] * y * y)
        if nm == 20:
            x2 = x * x
            y2 = y * y
            return (par[off] * x + par[off + 1] * y + par[off + 2]
                    + par[off + 3] * x2 + par[off + 4] * x * y + par[off + 5] * y2
                    + par[off + 6] * x2 * x + par[off + 7] * x2 * y
                    + par[off + 8] * x * y2 + par[off + 9] * y2 * y)
        return None

    ksi = _poly(0)
    if ksi is None:
        # nm=30 或未支持阶数：逐点回退
        ra_arr = np.empty_like(np.asarray(x, dtype=float))
        de_arr = np.empty_like(ra_arr)
        for i in range(len(ra_arr)):
            ra_arr[i], de_arr[i] = xy2rade(par[:nm], nm, float(x[i]), float(y[i]), ra0, de0)
        return ra_arr, de_arr

    eta = _poly(half)
    tand1 = ksi / np.cos(de0) / (1.0 - eta * np.tan(de0))
    ra = ra0 + np.arctan(tand1)
    tand2 = (eta + np.tan(de0)) * np.cos(np.arctan(tand1)) / (1.0 - eta * np.tan(de0))
    de = np.arctan(tand2)
    return ra, de


def _angular_distance_vec(ra, de, ra_ref, de_ref):
    """成对角距（弧度），全部弧度输入，形状可广播。"""
    cos_rl = (np.sin(de) * np.sin(de_ref)
              + np.cos(de) * np.cos(de_ref) * np.cos(ra - ra_ref))
    np.clip(cos_rl, -1.0, 1.0, out=cos_rl)
    return np.arccos(cos_rl)


def _empty_best():
    return {
        "n": 0,
        "sig": 999.0,
        "par": np.zeros(30),
        "rx": [],
        "ry": [],
        "rra": [],
        "rde": [],
        "rmag": [],
        "ox": 0.0,
        "oy": 0.0,
    }


def _coarse_match_base_angle_fast(
    det_x,
    det_y,
    par_init,
    pscale,
    fl,
    limit_match,
    obj_ephra,
    obj_ephde,
    gaia_ra,
    gaia_de,
    gaia_mag,
    n_gaia,
    modeltype,
):
    """阶段一 KDTree 快路径：GAIA 投影建树一次，每个候选目标批量查询。

    候选集合经 cal_rl 严格复核，与暴力实现一致。best 更新语义与暴力路径完全相同。
    """
    n_det = len(det_x)
    best = _empty_best()
    if n_det == 0 or n_gaia == 0:
        return best

    det_x_arr = np.asarray(det_x, dtype=float)
    det_y_arr = np.asarray(det_y, dtype=float)

    ra0 = obj_ephra * DEG2RAD
    de0 = obj_ephde * DEG2RAD
    gaia_ra_arr = np.asarray(gaia_ra, dtype=float)
    gaia_de_arr = np.asarray(gaia_de, dtype=float)
    gaia_mag_arr = np.asarray(gaia_mag, dtype=float)
    gaia_ksi, gaia_eta = _rade2ky_vec(gaia_ra_arr * DEG2RAD, gaia_de_arr * DEG2RAD, ra0, de0)
    tree = cKDTree(np.column_stack([gaia_ksi, gaia_eta]))

    p0 = par_init[:6]
    radius = (limit_match / 3600.0) * DEG2RAD * _KDTREE_RADIUS_INFLATE

    for j in range(n_det):
        ox, oy = det_x_arr[j], det_y_arr[j]
        xn_all = (det_x_arr - ox) * pscale / fl
        yn_all = (det_y_arr - oy) * pscale / fl

        # 与暴力实现一致：所有 k 都参与（暴力路径无 det_x[k]>0 过滤）
        ksi_det = p0[0] * xn_all + p0[1] * yn_all + p0[2]
        eta_det = p0[3] * xn_all + p0[4] * yn_all + p0[5]
        ra_det, de_det = _xy2rade_linear_vec(p0, xn_all, yn_all, ra0, de0)

        idx_lists = tree.query_ball_point(np.column_stack([ksi_det, eta_det]), r=radius)

        rx, ry, rra, rde, rmag = [], [], [], [], []
        for k in range(n_det):
            cand = idx_lists[k]
            if not cand:
                continue
            cand = np.asarray(cand, dtype=int)
            rl = _angular_distance_vec(
                ra_det[k], de_det[k],
                gaia_ra_arr[cand] * DEG2RAD, gaia_de_arr[cand] * DEG2RAD,
            )
            ok = (rl / DEG2RAD * 3600.0) <= limit_match
            sel = cand[ok]
            if sel.size == 0:
                continue
            xn_k = xn_all[k]
            yn_k = yn_all[k]
            for n in sel:
                rx.append(xn_k)
                ry.append(yn_k)
                rra.append(gaia_ra_arr[n])
                rde.append(gaia_de_arr[n])
                rmag.append(gaia_mag_arr[n])

        nm = len(rx)
        if nm < best["n"] or nm < 3:
            continue

        par_tmp, sig0, _ = sol_par(
            np.array(rx), np.array(ry), np.array(rra), np.array(rde),
            nm, obj_ephra, obj_ephde, modeltype,
        )
        sig0_arcsec = sig0 / DEG2RAD * 3600.0
        if 0.001 < sig0_arcsec < 0.5 and (
            nm > best["n"] or sig0_arcsec < best["sig"]
        ):
            best.update(
                n=nm,
                sig=sig0_arcsec,
                par=par_tmp.copy(),
                rx=list(rx),
                ry=list(ry),
                rra=list(rra),
                rde=list(rde),
                rmag=list(rmag),
                ox=ox,
                oy=oy,
            )

    return best


def _coarse_match_base_angle(
    det_x,
    det_y,
    par_init,
    pscale,
    fl,
    limit_match,
    obj_ephra,
    obj_ephde,
    gaia_ra,
    gaia_de,
    gaia_mag,
    n_gaia,
    modeltype,
):
    """阶段一粗匹配：先走 KDTree 快路径，命中失败或异常自动回退暴力实现。"""
    try:
        best = _coarse_match_base_angle_fast(
            det_x, det_y, par_init, pscale, fl, limit_match,
            obj_ephra, obj_ephde, gaia_ra, gaia_de, gaia_mag, n_gaia, modeltype,
        )
        if best["n"] >= 3:
            return best
    except Exception as exc:
        _log.info(f"    快路径粗匹配异常，回退暴力实现：{exc}")
    return _coarse_match_base_angle_brute(
        det_x, det_y, par_init, pscale, fl, limit_match,
        obj_ephra, obj_ephde, gaia_ra, gaia_de, gaia_mag, n_gaia, modeltype,
    )


def _coarse_match_base_angle_brute(
    det_x,
    det_y,
    par_init,
    pscale,
    fl,
    limit_match,
    obj_ephra,
    obj_ephde,
    gaia_ra,
    gaia_de,
    gaia_mag,
    n_gaia,
    modeltype,
):
    """阶段一：暴力粗匹配。返回与原实现一致的 best 字典。"""
    n_det = len(det_x)
    best = {
        "n": 0,
        "sig": 999.0,
        "par": np.zeros(30),
        "rx": [],
        "ry": [],
        "rra": [],
        "rde": [],
        "rmag": [],
        "ox": 0.0,
        "oy": 0.0,
    }

    for j in range(n_det):
        ox, oy = det_x[j], det_y[j]
        rx, ry, rra, rde, rmag = [], [], [], [], []

        for k in range(n_det):
            xn = (det_x[k] - ox) * pscale / fl
            yn = (det_y[k] - oy) * pscale / fl
            ra_k, de_k = xy2rade(par_init[:6], 6, xn, yn, obj_ephra * DEG2RAD, obj_ephde * DEG2RAD)
            for n in range(n_gaia):
                rl = cal_rl(ra_k, de_k, gaia_ra[n] * DEG2RAD, gaia_de[n] * DEG2RAD)
                if rl / DEG2RAD * 3600 <= limit_match:
                    rx.append(xn)
                    ry.append(yn)
                    rra.append(gaia_ra[n])
                    rde.append(gaia_de[n])
                    rmag.append(gaia_mag[n])

        nm = len(rx)
        if nm < best["n"] or nm < 3:
            continue

        try:
            par_tmp, sig0, _ = sol_par(
                np.array(rx),
                np.array(ry),
                np.array(rra),
                np.array(rde),
                nm,
                obj_ephra,
                obj_ephde,
                modeltype,
            )
            sig0_arcsec = sig0 / DEG2RAD * 3600.0
            # 更新最佳候选：sig 在合理范围内且 (匹配更多) 或 (同匹配但 sigma 更小)
            if 0.001 < sig0_arcsec < 0.5 and (
                nm > best["n"] or sig0_arcsec < best["sig"]
            ):
                best.update(
                    n=nm,
                    sig=sig0_arcsec,
                    par=par_tmp.copy(),
                    rx=list(rx),
                    ry=list(ry),
                    rra=list(rra),
                    rde=list(rde),
                    rmag=list(rmag),
                    ox=ox,
                    oy=oy,
                )
        except Exception:
            continue

    return best


def _refine_base_angle_center(best, pscale, fl, obj_ephra, obj_ephde, modeltype):
    """阶段二：粗匹配参考星精化中心并解第二版底片常数。"""
    ox, oy = best["ox"], best["oy"]
    n_m = best["n"]

    # 标准坐标还原为像素坐标
    rx0 = np.array([v * fl / pscale + ox for v in best["rx"]])
    ry0 = np.array([v * fl / pscale + oy for v in best["ry"]])
    rra0 = np.array(best["rra"])
    rde0 = np.array(best["rde"])

    # 第一次：以 obj_x0/obj_y0 为原点，历表位置为球面中心
    rxn_first = (rx0 - ox) * pscale / fl
    ryn_first = (ry0 - oy) * pscale / fl
    try:
        par1_first, _, _ = sol_par(
            rxn_first, ryn_first, rra0, rde0, n_m, obj_ephra, obj_ephde, modeltype
        )
    except Exception:
        return None

    # 参考星像素质心，作为下一次的原点
    x_cen = float(np.sum(rx0)) / n_m
    y_cen = float(np.sum(ry0)) / n_m

    obj_xn = (x_cen - ox) * pscale / fl
    obj_yn = (y_cen - oy) * pscale / fl
    ra_cen, de_cen = xy2rade(
        par1_first[:modeltype], modeltype, obj_xn, obj_yn, obj_ephra * DEG2RAD, obj_ephde * DEG2RAD
    )
    _log.info(
        f"    参考星星座中心xyrade：{x_cen:11.3f}{y_cen:11.3f}"
        f"{ra_cen / DEG2RAD:11.3f}{de_cen / DEG2RAD:11.3f}"
    )

    # 第二次：以质心为原点，ra_center/de_center 为球面中心
    rxn = (rx0 - x_cen) * pscale / fl
    ryn = (ry0 - y_cen) * pscale / fl
    try:
        par1, sig0, _ = sol_par(
            rxn, ryn, rra0, rde0, n_m, ra_cen / DEG2RAD, de_cen / DEG2RAD, modeltype
        )
    except Exception:
        return None

    return dict(
        ox=ox,
        oy=oy,
        n_m=n_m,
        par1=par1,
        sig0=sig0,
        x_cen=x_cen,
        y_cen=y_cen,
        ra_cen=ra_cen,
        de_cen=de_cen,
    )


def _rematch_field_candidates_fast(
    det_x_arr, det_y_arr, par1, modeltype, pscale, fl,
    x_cen, y_cen, ra_cen, de_cen,
    gaia_ra_arr, gaia_de_arr, gaia_mag_arr, limit_match,
):
    """KDTree 矢量化候选收集：返回与暴力实现等价的 (rx, ry, rra, rde, rmag)。

    暴力路径里检测星按 k 升序追加，候选 GAIA 按 n 升序追加；本实现保留同样顺序，
    保证后续 sol_par 的输入数组与暴力实现逐位一致。
    """
    n_det = len(det_x_arr)
    valid = (det_x_arr > 0) & (det_y_arr > 0)

    xn_all = (det_x_arr - x_cen) * pscale / fl
    yn_all = (det_y_arr - y_cen) * pscale / fl
    ra_arr, de_arr = _xy2rade_poly_vec(par1[:modeltype], modeltype, xn_all, yn_all, ra_cen, de_cen)

    det_ksi, det_eta = _rade2ky_vec(ra_arr, de_arr, ra_cen, de_cen)
    tree = cKDTree(
        np.column_stack(_rade2ky_vec(gaia_ra_arr * DEG2RAD, gaia_de_arr * DEG2RAD, ra_cen, de_cen))
    )
    radius = (limit_match / 3600.0) * DEG2RAD * _KDTREE_RADIUS_INFLATE
    idx_lists = tree.query_ball_point(np.column_stack([det_ksi, det_eta]), r=radius)

    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    for k in range(n_det):
        if not valid[k]:
            continue
        cand = idx_lists[k]
        if not cand:
            continue
        cand = np.sort(np.asarray(cand, dtype=int))  # 与暴力 n 升序一致
        rl = _angular_distance_vec(
            ra_arr[k], de_arr[k],
            gaia_ra_arr[cand] * DEG2RAD, gaia_de_arr[cand] * DEG2RAD,
        )
        ok = (rl / DEG2RAD * 3600.0) <= limit_match
        sel = cand[ok]
        if sel.size == 0:
            continue
        xn_k = xn_all[k]
        yn_k = yn_all[k]
        for n in sel:
            rx_new.append(xn_k)
            ry_new.append(yn_k)
            rra_new.append(gaia_ra_arr[n])
            rde_new.append(gaia_de_arr[n])
            rmag_new.append(gaia_mag_arr[n])
    return rx_new, ry_new, rra_new, rde_new, rmag_new


def _rematch_field_candidates_brute(
    det_x, det_y, par1, modeltype, pscale, fl,
    x_cen, y_cen, ra_cen, de_cen,
    gaia_ra, gaia_de, gaia_mag, n_gaia, limit_match,
):
    """暴力候选收集（fallback）。"""
    n_det = len(det_x)
    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        for n in range(n_gaia):
            rl = cal_rl(ra_k, de_k, gaia_ra[n] * DEG2RAD, gaia_de[n] * DEG2RAD)
            if rl / DEG2RAD * 3600 <= limit_match:
                rx_new.append(xn)
                ry_new.append(yn)
                rra_new.append(gaia_ra[n])
                rde_new.append(gaia_de[n])
                rmag_new.append(gaia_mag[n])
    return rx_new, ry_new, rra_new, rde_new, rmag_new


def _rematch_base_angle_field(
    det_x,
    det_y,
    gaia_ra,
    gaia_de,
    gaia_mag,
    n_gaia,
    limit_match,
    modeltype,
    pscale,
    fl,
    par1,
    x_cen,
    y_cen,
    ra_cen,
    de_cen,
):
    """阶段三：用精化常数对全图检测星重新匹配 GAIA。

    默认走 KDTree 快路径；异常或未给出 ≥3 匹配时回退暴力实现。
    """
    det_x_arr = np.asarray(det_x, dtype=float)
    det_y_arr = np.asarray(det_y, dtype=float)
    gaia_ra_arr = np.asarray(gaia_ra, dtype=float)
    gaia_de_arr = np.asarray(gaia_de, dtype=float)
    gaia_mag_arr = np.asarray(gaia_mag, dtype=float)

    rx_new = ry_new = rra_new = rde_new = rmag_new = None
    if n_gaia > 0 and det_x_arr.size > 0:
        try:
            rx_new, ry_new, rra_new, rde_new, rmag_new = _rematch_field_candidates_fast(
                det_x_arr, det_y_arr, par1, modeltype, pscale, fl,
                x_cen, y_cen, ra_cen, de_cen,
                gaia_ra_arr, gaia_de_arr, gaia_mag_arr, limit_match,
            )
            if len(rx_new) < 3:
                rx_new = None
        except Exception as exc:
            _log.info(f"    快路径全图匹配异常，回退暴力实现：{exc}")
            rx_new = None

    if rx_new is None:
        rx_new, ry_new, rra_new, rde_new, rmag_new = _rematch_field_candidates_brute(
            det_x, det_y, par1, modeltype, pscale, fl,
            x_cen, y_cen, ra_cen, de_cen,
            gaia_ra, gaia_de, gaia_mag, n_gaia, limit_match,
        )

    n_m = len(rx_new)
    if n_m < 3:
        return None

    try:
        par1, sig0, _ = sol_par(
            np.array(rx_new),
            np.array(ry_new),
            np.array(rra_new),
            np.array(rde_new),
            n_m,
            ra_cen / DEG2RAD,
            de_cen / DEG2RAD,
            modeltype,
        )
    except Exception:
        return None

    return dict(
        rx_new=rx_new,
        ry_new=ry_new,
        rra_new=rra_new,
        rde_new=rde_new,
        rmag_new=rmag_new,
        n_m=n_m,
        par1=par1,
        sig1=sig0 / DEG2RAD * 3600.0,
    )


def _locate_base_angle_target(
    det_x,
    det_y,
    det_flux,
    det_snr,
    par1,
    pscale,
    fl,
    modeltype,
    x_cen,
    y_cen,
    ra_cen,
    de_cen,
    obj_ephra,
    obj_ephde,
):
    """阶段四：历表位置反演到像素坐标，并在 3 像素内抓取目标。"""
    n_det = len(det_x)
    xi, eta = rade2xieta(obj_ephra * DEG2RAD, obj_ephde * DEG2RAD, ra_cen, de_cen)
    pre_x, pre_y = xieta2xy(xi, eta, par1[:6])
    pre_x = pre_x * fl / pscale + x_cen
    pre_y = pre_y * fl / pscale + y_cen
    _log.info(
        f"    预报x/y，历表ra/de：{pre_x:11.5f}{pre_y:11.5f}"
        f"{obj_ephra:11.5f}{obj_ephde:11.5f}"
    )

    # dis0=20 初始判断限，最终取 dis<=3 且最近的星
    dis0, selectflag = 20.0, 0
    obj_x_obs = obj_y_obs = obj_flux_obs = snr_obs = 0.0
    for i in range(n_det):
        dis = np.hypot(det_x[i] - pre_x, det_y[i] - pre_y)
        if dis <= 3.0 and dis < dis0:
            dis0 = dis
            obj_x_obs = det_x[i]
            obj_y_obs = det_y[i]
            obj_flux_obs = det_flux[i]
            snr_obs = det_snr[i]
            selectflag = 1

    if not selectflag:
        _log.info("    此图像未找到与预报目标位置相近的目标")
        return None

    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
    _log.info(
        f"    实测x/y，实测ra/de：{obj_x_obs:11.5f}{obj_y_obs:11.5f}"
        f"{obj_obsra / DEG2RAD:11.5f}{obj_obsde / DEG2RAD:11.5f}"
    )

    return dict(
        obj_x_obs=obj_x_obs,
        obj_y_obs=obj_y_obs,
        obj_flux_obs=obj_flux_obs,
        snr_obs=snr_obs,
        obj_obsra=obj_obsra,
        obj_obsde=obj_obsde,
    )


# ── 对外接口 ──────────────────────────────────────────────────────────────

def find_obj_base_angle(
    det_x,
    det_y,
    det_flux,
    det_snr,
    label,
    field_angle,
    pscale,
    fl,
    limit_match,
    obj_ephra,
    obj_ephde,
    gaia_ra,
    gaia_de,
    gaia_mag,
    n_gaia,
    modeltype,
):
    """全力盲搜：以每颗检测星为假设目标，解算底片常数与目标位置。

    阶段：
      1. 暴力粗匹配  : 每颗检测星都试一次假设目标，与 GAIA 交叉匹配次数最多者获胜
      2. 精化中心    : 用粗匹配参考星解第一版常数，再以参考星质心为新中心解第二版
      3. 全图再匹配  : 用精化常数把所有检测星重新与 GAIA 交叉匹配
      4. 预报抓目标  : 把历表反演到像素坐标，3 像素容差内取最近的检测星作为目标
      5. 验证        : 对比粗匹配认定的目标与最终抓取目标的差异

    内层 GAIA 循环不 break：一颗检测星可与多颗 GAIA 星匹配（与 Fortran 行为一致）。
    """
    n_det = len(det_x)
    if n_det < 3:
        _log.info(f"    检测星少于 3 颗，跳过：{label}")
        r = _empty_result()
        r.nostar = 1
        return r

    # ── 阶段一：暴力粗匹配 ────────────────────────────────────────────────
    par_init = _initial_plate_par(field_angle)
    best = _coarse_match_base_angle(
        det_x,
        det_y,
        par_init,
        pscale,
        fl,
        limit_match,
        obj_ephra,
        obj_ephde,
        gaia_ra,
        gaia_de,
        gaia_mag,
        n_gaia,
        modeltype,
    )

    if best["n"] < 3:
        _log.info("    粗匹配失败：未找到足够参考星")
        r = _empty_result()
        r.nopre = 1
        return r

    # ── 阶段二：精化中心（两次 sol_par） ──────────────────────────────────
    refined = _refine_base_angle_center(best, pscale, fl, obj_ephra, obj_ephde, modeltype)
    if refined is None:
        r = _empty_result()
        r.nopre = 1
        return r
    ox, oy = refined["ox"], refined["oy"]
    x_cen = refined["x_cen"]
    y_cen = refined["y_cen"]
    ra_cen = refined["ra_cen"]
    de_cen = refined["de_cen"]
    par1 = refined["par1"]

    # ── 阶段三：全图再匹配 ────────────────────────────────────────────────
    rematched = _rematch_base_angle_field(
        det_x,
        det_y,
        gaia_ra,
        gaia_de,
        gaia_mag,
        n_gaia,
        limit_match,
        modeltype,
        pscale,
        fl,
        par1,
        x_cen,
        y_cen,
        ra_cen,
        de_cen,
    )
    if rematched is None:
        r = _empty_result()
        r.nopre = 1
        return r
    rx_new = rematched["rx_new"]
    ry_new = rematched["ry_new"]
    rra_new = rematched["rra_new"]
    rde_new = rematched["rde_new"]
    rmag_new = rematched["rmag_new"]
    n_m = rematched["n_m"]
    par1 = rematched["par1"]
    sig1 = rematched["sig1"]

    # ── 阶段四：预报并抓取目标 ────────────────────────────────────────────
    target = _locate_base_angle_target(
        det_x,
        det_y,
        det_flux,
        det_snr,
        par1,
        pscale,
        fl,
        modeltype,
        x_cen,
        y_cen,
        ra_cen,
        de_cen,
        obj_ephra,
        obj_ephde,
    )
    if target is None:
        r = _empty_result()
        r.nopre = 1
        return r
    obj_x_obs = target["obj_x_obs"]
    obj_y_obs = target["obj_y_obs"]
    obj_flux_obs = target["obj_flux_obs"]
    snr_obs = target["snr_obs"]
    obj_obsra = target["obj_obsra"]
    obj_obsde = target["obj_obsde"]

    # ── 阶段五：粗匹配 vs 最终位置差异 ────────────────────────────────────
    if abs(ox - obj_x_obs) > 0.001 and abs(oy - obj_y_obs) > 0.001:
        _log.info(
            f"    自动检测目标与最终确认目标有差异x/y "
            f"{ox - obj_x_obs:.3f} {oy - obj_y_obs:.3f}"
        )
    else:
        _log.info("    自动检测确认的目标==最终确认的目标")

    # ── 参考星像素坐标输出（按 n_m 切片，不再预分配 90 万） ───────────────
    ref_x_out = np.array(rx_new) * fl / pscale + x_cen
    ref_y_out = np.array(ry_new) * fl / pscale + y_cen
    ref_ra_out = np.array(rra_new)
    ref_de_out = np.array(rde_new)
    ref_mag_out = np.array(rmag_new)

    return MatchResult(
        nostar=0,
        nopre=0,
        obj_x=obj_x_obs,
        obj_y=obj_y_obs,
        obj_flux=obj_flux_obs,
        snr=snr_obs,
        obj_obsra=obj_obsra / DEG2RAD,
        obj_obsde=obj_obsde / DEG2RAD,
        n_match1=n_m,
        sig0=sig1,
        par1=par1.copy(),
        x_center=x_cen,
        y_center=y_cen,
        ra_center=ra_cen,
        de_center=de_cen,
        ref_x=ref_x_out,
        ref_y=ref_y_out,
        ref_ra=ref_ra_out,
        ref_de=ref_de_out,
        ref_mag=ref_mag_out,
    )


def find_obj_base_prepar(
    det_x,
    det_y,
    det_flux,
    det_snr,
    plate,
    pscale,
    fl,
    modeltype,
    limit_match,
    obj_ephra,
    obj_ephde,
):
    """复用前一目标的底片常数 plate.par，直接挑选距离历表位置最近的检测星作为目标。

    不重算底片常数，不输出参考星与 sig0。
    """
    result = _empty_result(
        par1=plate.par.copy(),
        x_cen=plate.x_center,
        y_cen=plate.y_center,
        ra_cen=plate.ra_center,
        de_cen=plate.de_center,
    )
    result.nopre = 1
    n_det = len(det_x)

    rl0 = limit_match
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - plate.x_center) * pscale / fl
        yn = (det_y[k] - plate.y_center) * pscale / fl
        ra_k, de_k = xy2rade(
            plate.par[:modeltype], modeltype, xn, yn, plate.ra_center, plate.de_center
        )
        rl = cal_rl(ra_k, de_k, obj_ephra * DEG2RAD, obj_ephde * DEG2RAD) / DEG2RAD * 3600.0
        if rl <= limit_match and rl < rl0:
            rl0 = rl
            result.obj_x = det_x[k]
            result.obj_y = det_y[k]
            result.obj_flux = det_flux[k]
            result.snr = det_snr[k]
            result.obj_obsra = ra_k / DEG2RAD
            result.obj_obsde = de_k / DEG2RAD
            result.nopre = 0

    if result.nopre:
        _log.info("    据pre_par，未找到与预报目标位置相近的目标")
    return result
