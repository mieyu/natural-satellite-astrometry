# 功能：03match 星象匹配与天体归算批处理逻辑。
# 逻辑：严格按照 Fortran 03match.f90 实现，与原程序保持一致。

import os

import numpy as np

from adias.io.adias_catalog_io import read_catalog, read_ephemeris
from adias.io.adias_fits_io import read_fits_header
from adias.io.adias_text_io import (
    read_fits_list,
    read_reg_file,
    sort_output_file,
    write_object_result,
    write_ref_file,
)
from adias.utils.adias_math_utils import (
    Q,
    cal_rl,
    extract_field_stars,
    interpolate,
    print_par,
    rade2xieta,
    sol_par,
    xieta2xy,
    xy2rade,
)

MAX_SIZE = 900000


# ─────────────────────────────────────────────
# 核心匹配函数（私有）
# ─────────────────────────────────────────────


def _find_obj_base_angle(
    fitsfile,
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
    """
    基于底片旋转角与 GAIA 星表的盲搜匹配函数。
    严格按照 Fortran find_obj_base_angle 子程序逻辑实现。

    阶段 1（Fortran 199 goto 循环）：
        以每颗检测星为假设目标，将其他星投影到天球，与 GAIA 交叉匹配。
        内层 GAIA 循环无 exit/break，一颗检测星可与多颗 GAIA 星匹配。
        仅当匹配数量严格超过当前最佳时调用 sol_par，不做 sigma 大小比较。

    阶段 2（Fortran 03 段）：
        ① 以 obj_x0/obj_y0 为原点、历表赤经赤纬为球面中心，解算第一版底片常数。
        ② 计算参考星像素质心（x_center, y_center）。
        ③ 用第一版底片常数将质心坐标转换为球面坐标（ra_center, de_center）。
        ④ 以质心像素坐标为原点、ra_center/de_center 为球面中心，解算第二版底片常数。

    阶段 3（Fortran 04 段）：
        用精化后的底片常数全图重新与 GAIA 交叉匹配。内层 GAIA 循环同样无 break。

    阶段 4（Fortran select_obj_xy 子程序）：
        反演历表位置到像素坐标，在 3 像素容差内抓取最近的检测星作为目标。

    阶段 5（Fortran 05 步骤）：
        对比阶段 1 认定的目标位置（obj_x0/obj_y0）与最终抓取位置，打印差异。
    """
    _empty = dict(
        nostar=0,
        nopre=0,
        obj_x=0.0,
        obj_y=0.0,
        obj_flux=0.0,
        snr=0.0,
        obj_obsra=0.0,
        obj_obsde=0.0,
        n_match1=0,
        sig0=0.0,
        par1=np.zeros(30),
        x_center=0.0,
        y_center=0.0,
        ra_center=0.0,
        de_center=0.0,
        ref_x=np.zeros(MAX_SIZE),
        ref_y=np.zeros(MAX_SIZE),
        ref_ra=np.zeros(MAX_SIZE),
        ref_de=np.zeros(MAX_SIZE),
        ref_mag=np.zeros(MAX_SIZE),
    )

    # ── 初始底片常数（基于配置文件中的旋转角）
    # 对应 Fortran：par(1)=cos; par(2)=sin; par(4)=-sin; par(5)=cos
    ca, sa = np.cos(field_angle * Q), np.sin(field_angle * Q)
    par_init = np.zeros(30)
    par_init[0], par_init[1] = ca, sa
    par_init[3], par_init[4] = -sa, ca

    # ── 读取 reg 文件（02detect 的检测结果）
    regfile = fitsfile + ".reg"
    det_x, det_y, det_flux, det_snr = read_reg_file(regfile)
    n_det = len(det_x)

    if n_det < 3:
        print(f"    检测星少于 3 颗，跳过：{os.path.basename(fitsfile)}")
        _empty["nostar"] = 1
        return _empty

    # ════════════════════════════════════════════════════════════════
    # 阶段一：暴力粗匹配（Fortran j=0; 199 j=j+1; … if j<=n_det goto 199）
    # ════════════════════════════════════════════════════════════════
    # best['n'] 对应 Fortran n_match1（初始 0）
    # 用完整键集初始化，避免 pyright 将值类型推断为 float
    best: dict = {
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
        ox, oy = det_x[j], det_y[j]  # 假设第 j 颗为目标（obj_x/obj_y）
        rx, ry, rra, rde, rmag = [], [], [], [], []

        # 遍历所有检测星 k，投影到天球，与 GAIA 交叉匹配
        for k in range(n_det):  # 量度坐标（以第 j 颗为中心）
            xn = (det_x[k] - ox) * pscale / fl
            yn = (det_y[k] - oy) * pscale / fl
            # 用初始旋转角底片常数，配合历表位置，推算赤经赤纬
            ra_k, de_k = xy2rade(par_init[:6], 6, xn, yn, obj_ephra * Q, obj_ephde * Q)
            # 与 GAIA 星表逐一比较
            # Fortran 内层循环无 exit：一颗检测星可与多颗 GAIA 星匹配
            for n in range(n_gaia):
                rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
                if rl / Q * 3600 <= limit_match:
                    rx.append(xn)
                    ry.append(yn)
                    rra.append(gaia_ra[n])
                    rde.append(gaia_de[n])
                    rmag.append(gaia_mag[n])
                    # 无 break，与 Fortran 一致

        nm = len(rx)
        # 匹配数量少于当前最佳或不足 3 颗时直接跳过，无需调用 sol_par
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
            # sig 在合理范围内，且满足以下任一条件才更新最佳候选：
            #   ① 匹配数量严格更多（nm > best["n"]）
            #   ② 匹配数量相同，但 sigma 更小（nm == best["n"] and sig < best["sig"]）
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

    if best["n"] < 3:
        print("    粗匹配失败：未找到足够参考星")
        _empty["nopre"] = 1
        return _empty

    # ════════════════════════════════════════════════════════════════
    # 阶段二：精化参考中心（Fortran 03 段，含两次 sol_par）
    # ════════════════════════════════════════════════════════════════
    # obj_x0, obj_y0 = 粗匹配阶段认定的目标像素坐标
    ox, oy = best["ox"], best["oy"]
    n_m = best["n"]

    # 将标准坐标还原为像素坐标（ref_x0, ref_y0 in Fortran）
    rx0 = np.array([v * fl / pscale + ox for v in best["rx"]])
    ry0 = np.array([v * fl / pscale + oy for v in best["ry"]])
    rra0 = np.array(best["rra"])
    rde0 = np.array(best["rde"])

    # ① 第一次 sol_par：以 obj_x0/obj_y0 为原点，历表位置为球面中心
    #    对应 Fortran：ref_x=(ref_x0-obj_x0)*pscale/fl
    #                   call sol_par(..., obj_ephra, obj_ephde, ...)
    rxn_first = (rx0 - ox) * pscale / fl
    ryn_first = (ry0 - oy) * pscale / fl
    try:
        par1_first, _, _ = sol_par(
            rxn_first, ryn_first, rra0, rde0, n_m, obj_ephra, obj_ephde, modeltype
        )
    except Exception:
        _empty["nopre"] = 1
        return _empty

    # ② 计算参考星像素质心
    #    对应 Fortran：x_center=sum(ref_x0)/n_match1
    x_cen = float(np.sum(rx0)) / n_m
    y_cen = float(np.sum(ry0)) / n_m

    # ③ 用第一版底片常数将质心像素坐标转换为球面坐标
    #    对应 Fortran：obj_xn=(x_center-obj_x0)*pscale/fl
    #                   call xy2rade(par1, obj_xn, obj_yn, obj_ephra, obj_ephde, ra_center, de_center)
    obj_xn = (x_cen - ox) * pscale / fl
    obj_yn = (y_cen - oy) * pscale / fl
    ra_cen, de_cen = xy2rade(
        par1_first[:modeltype], modeltype, obj_xn, obj_yn, obj_ephra * Q, obj_ephde * Q
    )
    print(
        f"    参考星星座中心xyrade：{x_cen:11.3f}{y_cen:11.3f}"
        f"{ra_cen / Q:11.3f}{de_cen / Q:11.3f}"
    )

    # ④ 第二次 sol_par：以质心为原点，ra_center/de_center 为球面中心
    #    对应 Fortran：ref_x=(ref_x0-x_center)*pscale/fl
    #                   call sol_par(..., ra_center/q, de_center/q, ...)
    rxn = (rx0 - x_cen) * pscale / fl
    ryn = (ry0 - y_cen) * pscale / fl
    try:
        par1, sig0, _ = sol_par(
            rxn, ryn, rra0, rde0, n_m, ra_cen / Q, de_cen / Q, modeltype
        )
    except Exception:
        _empty["nopre"] = 1
        return _empty
    sig1 = sig0 / Q * 3600.0

    # ════════════════════════════════════════════════════════════════
    # 阶段三：全图再匹配（Fortran 使用新中心重匹配，内层无 break）
    # ════════════════════════════════════════════════════════════════
    rx_new, ry_new, rra_new, rde_new, rmag_new = [], [], [], [], []
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        # Fortran 内层循环无 exit，允许一颗检测星对应多颗 GAIA 星
        for n in range(n_gaia):
            rl = cal_rl(ra_k, de_k, gaia_ra[n] * Q, gaia_de[n] * Q)
            if rl / Q * 3600 <= limit_match:
                rx_new.append(xn)
                ry_new.append(yn)
                rra_new.append(gaia_ra[n])
                rde_new.append(gaia_de[n])
                rmag_new.append(gaia_mag[n])
                # 无 break，与 Fortran 一致

    n_m = len(rx_new)
    if n_m < 3:
        _empty["nopre"] = 1
        return _empty

    # 用全图匹配参考星重新解算底片常数
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
        _empty["nopre"] = 1
        return _empty
    sig1 = sig0 / Q * 3600.0

    # ════════════════════════════════════════════════════════════════
    # 阶段四：预报并抓取目标天体（Fortran select_obj_xy 子程序）
    # ════════════════════════════════════════════════════════════════
    # 将历表赤经赤纬反演为照片预报像素坐标
    xi, eta = rade2xieta(obj_ephra * Q, obj_ephde * Q, ra_cen, de_cen)
    pre_x, pre_y = xieta2xy(xi, eta, par1[:6])
    pre_x = pre_x * fl / pscale + x_cen
    pre_y = pre_y * fl / pscale + y_cen
    print(
        f"    预报x/y，历表ra/de：{pre_x:11.5f}{pre_y:11.5f}"
        f"{obj_ephra:11.5f}{obj_ephde:11.5f}"
    )

    # Fortran select_obj_xy：dis0=20（初始判断限），最终取 dis<=3 且最近的星
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
        _empty["nopre"] = 1
        return _empty

    # 将目标实测像素坐标归算为赤经赤纬
    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
    print(
        f"    实测x/y，实测ra/de：{obj_x_obs:11.5f}{obj_y_obs:11.5f}"
        f"{obj_obsra / Q:11.5f}{obj_obsde / Q:11.5f}"
    )

    # ════════════════════════════════════════════════════════════════
    # 阶段五：验证（Fortran 05 步骤）
    # 对比粗匹配认定的目标坐标（obj_x0/obj_y0 = ox/oy）与最终坐标
    # ════════════════════════════════════════════════════════════════
    if abs(ox - obj_x_obs) > 0.001 and abs(oy - obj_y_obs) > 0.001:
        print(
            f"    自动检测目标与最终确认目标有差异x/y "
            f"{ox - obj_x_obs:.3f} {oy - obj_y_obs:.3f}"
        )
    else:
        print("    自动检测确认的目标==最终确认的目标")

    # ════════════════════════════════════════════════════════════════
    # 整理结果并返回
    # ════════════════════════════════════════════════════════════════
    # 先用独立 ndarray 变量填充参考星数据，避免 pyright 因 dict 值类型歧义报错
    ref_x_out = np.zeros(MAX_SIZE)
    ref_y_out = np.zeros(MAX_SIZE)
    ref_ra_out = np.zeros(MAX_SIZE)
    ref_de_out = np.zeros(MAX_SIZE)
    ref_mag_out = np.zeros(MAX_SIZE)
    for i in range(n_m):
        ref_x_out[i] = rx_new[i] * fl / pscale + x_cen
        ref_y_out[i] = ry_new[i] * fl / pscale + y_cen
        ref_ra_out[i] = rra_new[i]
        ref_de_out[i] = rde_new[i]
        ref_mag_out[i] = rmag_new[i]

    return dict(
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


def _find_obj_base_prepar(
    fitsfile,
    par1,
    pscale,
    fl,
    modeltype,
    x_cen,
    y_cen,
    ra_cen,
    de_cen,
    limit_match,
    obj_ephra,
    obj_ephde,
):
    """
    利用前一幅图像的底片常数直接寻星归算。
    严格对应 Fortran find_obj_base_prepar 子程序。

    Fortran 子程序只做一件事：
        遍历检测星，将每颗星换算为赤经赤纬，与目标历表位置比较，
        取角距离最小（且在 limit_match 内）的星作为目标。
    不计算参考星，不更新底片常数，不输出 sig0。
    """
    result = dict(
        nopre=1,
        obj_x=0.0,
        obj_y=0.0,
        obj_flux=0.0,
        snr=0.0,
        obj_obsra=0.0,
        obj_obsde=0.0,
        sig0=0.0,
        n_match1=0,
        par1=par1.copy(),
        x_center=x_cen,
        y_center=y_cen,
        ra_center=ra_cen,
        de_center=de_cen,
        ref_x=np.zeros(MAX_SIZE),
        ref_y=np.zeros(MAX_SIZE),
        ref_ra=np.zeros(MAX_SIZE),
        ref_de=np.zeros(MAX_SIZE),
        ref_mag=np.zeros(MAX_SIZE),
    )

    det_x, det_y, det_flux, det_snr = read_reg_file(fitsfile + ".reg")
    n_det = len(det_x)

    # Fortran：初始 rl0=limit_match，取最近的目标
    rl0 = limit_match
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        rl = cal_rl(ra_k, de_k, obj_ephra * Q, obj_ephde * Q) / Q * 3600.0
        # Fortran：rl <= limit_match 且 rl < rl0，取最近的
        if rl <= limit_match and rl < rl0:
            rl0 = rl
            result.update(
                obj_x=det_x[k],
                obj_y=det_y[k],
                obj_flux=det_flux[k],
                snr=det_snr[k],
                obj_obsra=ra_k / Q,
                obj_obsde=de_k / Q,
                nopre=0,
            )

    if result["nopre"]:
        print("    据pre_par，未找到与预报目标位置相近的目标")
    return result


# ─────────────────────────────────────────────
# 对外接口
# ─────────────────────────────────────────────


def run_match(config, fitspath_list):
    """
    对 fitspath_list 中每个观测目录执行星象匹配与天体位置归算。
    严格按照 Fortran 03match.f90 主程序逻辑实现。

    与 Fortran 一致的关键行为
    ────────────────────────
    1. GAIA 星表每日重新读取（Fortran 在 77 goto 循环内每次打开星表文件）。
    2. flag_pre_match 在每幅图像开始时重置为 0（Fortran：flag_pre_match=0 在 555
       标签之后、9999 循环之前），而非每天重置。
       效果：每幅图的第 1 个目标始终走 base_angle 全力搜索；
             成功后同一幅图的后续目标走 prepar 快速归算；
             下一幅图重新从 base_angle 开始。
    3. base_angle 返回 nostar=1 时，跳过该图剩余所有目标（对应 Fortran goto 555）。
    4. prepar 模式写 ref.reg 时，沿用本图最近一次 base_angle 的参考星数据
       （Fortran 中 ref_x/y/n_match1 变量在 prepar 调用后未被清零，保留上次值）。

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    fitspath_list : list[str]，观测目录路径列表
    """
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n{'#' * 10} 本观测时段，第{idx:02d}日：fits文件夹：{fitspath}")

        # ── 01 逐日重新读取 GAIA 星表（与 Fortran 一致，每日重读）
        n_gaia, gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag = read_catalog(
            config["gaiacatpath"], config["min_mag"], config["max_mag"]
        )
        if n_gaia == 0 or gaia_ra is None:
            print("    读取 GAIA 星表失败，跳过本日")
            continue
        print(f"======读取本日配置文件及星表结束，共 {n_gaia} 颗。")

        # ── 读取本日图像列表
        fits_files = read_fits_list(fitspath)
        if not fits_files:
            print(f"    本日图像不足，跳过：{fitspath}")
            continue
        n_total = len(fits_files)
        print(f"======本日观测图像数量共计：{n_total} 幅")

        # ── 02 为每个目标打开输出文件（与 Fortran 在处理前批量 open 一致）
        object_out_files = {}
        for obj in range(1, config["obj_total"] + 1):
            object_out_files[obj] = open(
                os.path.join(fitspath, f"object_{obj}.out"), "w", encoding="utf-8"
            )

        # ── 03 逐幅图像处理（Fortran 555 标签循环）
        for n_fits, fitsfile_path in enumerate(fits_files, 1):
            fitsfile = fitsfile_path.strip()
            print(
                f"\n======当前图像：{n_fits:3d}/{n_total} - {os.path.basename(fitsfile)}"
            )

            hdr = read_fits_header(fitsfile, config["tele_label"])
            if hdr is None:
                continue

            # 计算观测时刻（天内分数日，含时间修正 delta_T）
            obj_T = (
                hdr["day"]
                + (hdr["hh"] * 3600 + hdr["mm"] * 60 + hdr["ss"] + config["delta_t"])
                / 86400.0
            )
            # 用于计算自行的年份（年为单位）
            calpm_epoch = hdr["year"] + ((hdr["month"] - 1) * 30 + hdr["day"]) / 365.0

            # ── 每幅图像开始时重置 flag_pre_match（Fortran 核心逻辑）
            # Fortran：flag_pre_match=0 位于 555 标签之后、9999 循环之前
            flag_pre = 0
            pre_par = np.zeros(30)
            pre_x_cen = 0.0
            pre_y_cen = 0.0
            pre_ra_cen = 0.0
            pre_de_cen = 0.0

            # 用于 prepar 模式写 ref.reg：保存本图最近一次 base_angle 的结果
            # （Fortran：ref_x/y/n_match1 在 prepar 调用后保留上次 base_angle 的值）
            last_base_result = None

            # ── 031 逐目标处理（Fortran 9999 goto 循环）
            skip_image = False  # 对应 Fortran：nostar=1 时 goto 555
            for obj in range(1, config["obj_total"] + 1):
                print(f"\n*****当前处理目标为：{obj}/{config['obj_total']}")

                # ── 032 读取历表，内插当前时刻目标位置
                n_eph, eph_T, eph_ra, eph_de = read_ephemeris(
                    config["ephpath"][obj - 1]
                )
                print(f"    读取该目标IMCCE历表位置数：{n_eph}")
                obj_ephra = interpolate(eph_T, eph_ra, n_eph, obj_T)
                obj_ephde = interpolate(eph_T, eph_de, n_eph, obj_T)

                # ── 从星表中截取视场内参考星，施加自行改正
                n_field, gf_ra, gf_de, gf_mag = extract_field_stars(
                    gaia_ra,
                    gaia_de,
                    gaia_pr,
                    gaia_pd,
                    gaia_mag,
                    n_gaia,
                    obj_ephra,
                    obj_ephde,
                    config["fsize"],
                    calpm_epoch,
                )
                print(f"    用于匹配的恒星数量：{n_field}")

                # ── 033 匹配与归算
                if flag_pre < 1:
                    # ── base_angle 模式：全力搜索底片常数
                    print("    ----自动寻星检测确定底片常数")
                    result = _find_obj_base_angle(
                        fitsfile,
                        config["field_angle"],
                        config["pscale"],
                        config["fl"],
                        config["limit_match"],
                        obj_ephra,
                        obj_ephde,
                        gf_ra,
                        gf_de,
                        gf_mag,
                        n_field,
                        config["modeltype"],
                    )

                    # Fortran：nostar=1 → goto 555（跳过该图所有剩余目标）
                    if result["nostar"] == 1:
                        skip_image = True
                        break

                    if result["nopre"] < 1:
                        print(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result['obj_x']:10.3f}{result['obj_y']:10.3f}"
                            f"{result['obj_obsra']:10.3f}{result['obj_obsde']:10.3f}"
                        )
                        print(f"    成功匹配星数：{result['n_match1']}")
                        print_par(result["par1"], config["modeltype"])
                        print(f"    底片模型归算sigma：{result['sig0']:7.3f}")

                    # 满足精度条件时，保存底片常数供后续目标使用
                    # Fortran：sig0>0.0001 AND sig0<0.06 AND n_match1>10
                    if 0.0001 < result["sig0"] < 0.06 and result["n_match1"] > 10:
                        flag_pre = 1
                        pre_par = result["par1"].copy()
                        pre_x_cen = result["x_center"]
                        pre_y_cen = result["y_center"]
                        pre_ra_cen = result["ra_center"]
                        pre_de_cen = result["de_center"]

                    # 保存本次 base_angle 结果，供后续 prepar 目标写 ref.reg 用
                    last_base_result = result

                else:
                    # ── prepar 模式：使用前一次底片常数快速归算
                    print("    ----使用pre_par归算(sig<0.06 & n_match>10)")
                    result = _find_obj_base_prepar(
                        fitsfile,
                        pre_par,
                        config["pscale"],
                        config["fl"],
                        config["modeltype"],
                        pre_x_cen,
                        pre_y_cen,
                        pre_ra_cen,
                        pre_de_cen,
                        config["limit_match"],
                        obj_ephra,
                        obj_ephde,
                    )

                    if result["nopre"] < 1:
                        print(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result['obj_x']:10.3f}{result['obj_y']:10.3f}"
                            f"{result['obj_obsra']:10.3f}{result['obj_obsde']:10.3f}"
                        )
                        print("    其余参数同前")

                # ── 034 写出参考星文件（*.ref.reg）
                # Fortran 行为：该写出操作在 if/else 之外执行，使用当前 n_match1/ref_x/y。
                # prepar 模式下 ref_x/y/n_match1 未被更新，保留 base_angle 的值。
                # Python 用 last_base_result 模拟这一行为。
                if flag_pre < 1:
                    ref_data = result  # base_angle 模式：用本次结果
                else:
                    ref_data = last_base_result  # prepar 模式：沿用上次 base_angle 结果

                if ref_data is not None and ref_data.get("n_match1", 0) > 0:
                    write_ref_file(f"{fitsfile}{obj}.ref.reg", ref_data)

                # ── 写出目标观测结果到 object_X.out
                # Fortran：abs(sig0)<1.0 AND abs(sig0)>0.0001
                # prepar 模式下 result["sig0"]=0.0，需沿用 last_base_result 的 sig0，
                # 与 Fortran 主程序中 sig0 变量由 find_obj_base_angle 写入、
                # find_obj_base_prepar 不覆盖的行为保持一致。
                if flag_pre < 1:
                    sig_for_write = result.get("sig0", 0.0)
                else:
                    sig_for_write = (
                        last_base_result["sig0"]
                        if last_base_result is not None
                        else 0.0
                    )
                if 0.0001 < abs(sig_for_write) < 1.0:
                    write_object_result(
                        object_out_files[obj],
                        hdr["year"],
                        hdr["month"],
                        obj_T,
                        result["obj_obsra"],
                        result["obj_obsde"],
                        obj_ephra,
                        obj_ephde,
                        sig_for_write,
                        hdr["hh"],
                        hdr["mm"],
                        hdr["ss"],
                        hdr["exptime"],
                        fitsfile,
                        config["field_angle"],
                    )
                    print(f"    写入out文件的结果，文件名：object_{obj}")

                print("=====当前图像处理完毕，处理下一个目标=====")
                # ── 035 处理下一个目标（Fortran goto 9999）

            # skip_image=True 时（nostar=1），跳过本图剩余目标，处理下一幅（goto 555）
            if skip_image:
                print("======本图无检测星，跳过，处理下一幅图像======")
                continue

            print("======本幅图像处理完毕，处理下一幅图像======")
            # ── 处理完一幅图，回到 555 循环读取下一幅

        # ── 05 关闭 object.out 文件，按时间排序（Fortran 05 段）
        for f in object_out_files.values():
            f.close()
        for obj in range(1, config["obj_total"] + 1):
            sort_output_file(os.path.join(fitspath, f"object_{obj}.out"))

        print(f"\n   本日匹配共归算天然卫星目标个数 {config['obj_total']}")
        print("=================================================================")

    print(f"\n   本时段观测任务匹配结束，共匹配天数：{len(fitspath_list)}")
    print("=================================================================")
