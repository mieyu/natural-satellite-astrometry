"""匹配领域算法：单幅图像内的盲搜匹配与 prepar 复用。

对外接口：
  - find_obj_base_angle(...)  → MatchResult   全力盲搜（首目标 / 底片常数解算）
  - find_obj_base_prepar(...) → MatchResult   复用底片常数（同图后续目标）
  - match_result_from_legacy / match_result_to_legacy  legacy dict 互转

阶段编排由 adias.core.matcher 负责。本模块纯算法 + MatchResult 进出，不涉及
StepResult / 文件 I/O。
"""

import numpy as np

from adias.domain.astrometry import (
    Q,
    cal_rl,
    rade2xieta,
    sol_par,
    xieta2xy,
    xy2rade,
)
from adias.domain.models import MatchResult


# ─── legacy 兼容 ──────────────────────────────────────────────────────────

def match_result_from_legacy(data):
    return MatchResult.from_legacy_dict(data)


def match_result_to_legacy(result):
    if isinstance(result, MatchResult):
        return result.to_legacy_dict()
    return result


# ─── 内部 helper ──────────────────────────────────────────────────────────

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
    ca, sa = np.cos(field_angle * Q), np.sin(field_angle * Q)
    par_init = np.zeros(30)
    par_init[0], par_init[1] = ca, sa
    par_init[3], par_init[4] = -sa, ca
    return par_init


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
            ra_k, de_k = xy2rade(par_init[:6], 6, xn, yn, obj_ephra * Q, obj_ephde * Q)
            for n in range(n_gaia):
                rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
                if rl / Q * 3600 <= limit_match:
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
            sig0_arcsec = sig0 / Q * 3600.0
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
        par1_first[:modeltype], modeltype, obj_xn, obj_yn, obj_ephra * Q, obj_ephde * Q
    )
    print(
        f"    参考星星座中心xyrade：{x_cen:11.3f}{y_cen:11.3f}"
        f"{ra_cen / Q:11.3f}{de_cen / Q:11.3f}"
    )

    # 第二次：以质心为原点，ra_center/de_center 为球面中心
    rxn = (rx0 - x_cen) * pscale / fl
    ryn = (ry0 - y_cen) * pscale / fl
    try:
        par1, sig0, _ = sol_par(
            rxn, ryn, rra0, rde0, n_m, ra_cen / Q, de_cen / Q, modeltype
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
    """阶段三：用精化常数对全图检测星重新匹配 GAIA。"""
    n_det = len(det_x)
    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        for n in range(n_gaia):
            rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
            if rl / Q * 3600 <= limit_match:
                rx_new.append(xn)
                ry_new.append(yn)
                rra_new.append(gaia_ra[n])
                rde_new.append(gaia_de[n])
                rmag_new.append(gaia_mag[n])

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
            ra_cen / Q,
            de_cen / Q,
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
        sig1=sig0 / Q * 3600.0,
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
    xi, eta = rade2xieta(obj_ephra * Q, obj_ephde * Q, ra_cen, de_cen)
    pre_x, pre_y = xieta2xy(xi, eta, par1[:6])
    pre_x = pre_x * fl / pscale + x_cen
    pre_y = pre_y * fl / pscale + y_cen
    print(
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
        print("    此图像未找到与预报目标位置相近的目标")
        return None

    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
    print(
        f"    实测x/y，实测ra/de：{obj_x_obs:11.5f}{obj_y_obs:11.5f}"
        f"{obj_obsra / Q:11.5f}{obj_obsde / Q:11.5f}"
    )

    return dict(
        obj_x_obs=obj_x_obs,
        obj_y_obs=obj_y_obs,
        obj_flux_obs=obj_flux_obs,
        snr_obs=snr_obs,
        obj_obsra=obj_obsra,
        obj_obsde=obj_obsde,
    )


# ─── 对外接口 ────────────────────────────────────────────────────────────

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
        print(f"    检测星少于 3 颗，跳过：{label}")
        r = _empty_result()
        r.nostar = 1
        return r

    # ── 阶段一：暴力粗匹配 ────────────────────────────────────────────
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
        print("    粗匹配失败：未找到足够参考星")
        r = _empty_result()
        r.nopre = 1
        return r

    # ── 阶段二：精化中心（两次 sol_par） ─────────────────────────────
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

    # ── 阶段三：全图再匹配 ────────────────────────────────────────────
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

    # ── 阶段四：预报并抓取目标 ────────────────────────────────────────
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

    # ── 阶段五：粗匹配 vs 最终位置差异 ────────────────────────────────
    if abs(ox - obj_x_obs) > 0.001 and abs(oy - obj_y_obs) > 0.001:
        print(
            f"    自动检测目标与最终确认目标有差异x/y "
            f"{ox - obj_x_obs:.3f} {oy - obj_y_obs:.3f}"
        )
    else:
        print("    自动检测确认的目标==最终确认的目标")

    # ── 参考星像素坐标输出（按 n_m 切片，不再预分配 90 万）─────────────
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
        obj_obsra=obj_obsra / Q,
        obj_obsde=obj_obsde / Q,
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
        rl = cal_rl(ra_k, de_k, obj_ephra * Q, obj_ephde * Q) / Q * 3600.0
        if rl <= limit_match and rl < rl0:
            rl0 = rl
            result.obj_x = det_x[k]
            result.obj_y = det_y[k]
            result.obj_flux = det_flux[k]
            result.snr = det_snr[k]
            result.obj_obsra = ra_k / Q
            result.obj_obsde = de_k / Q
            result.nopre = 0

    if result.nopre:
        print("    据pre_par，未找到与预报目标位置相近的目标")
    return result


__all__ = [
    "find_obj_base_angle",
    "find_obj_base_prepar",
    "match_result_from_legacy",
    "match_result_to_legacy",
]
