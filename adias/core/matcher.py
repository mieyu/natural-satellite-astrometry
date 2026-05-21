# 03match：星象与 GAIA 星表交叉匹配，解算底片常数后归算目标天体位置。
#
# 主流程对单幅 .fit：
#   1. 读检测星表 fits_reg/*.fit.reg（由 02detect 产出）
#   2. 第 1 个目标走 base_angle 全力盲搜，得到底片常数 par1；满足精度则保存
#   3. 同图像后续目标走 prepar 复用 par1 快速归算
#   4. 参考星写到 fits_ref/*.fitN.ref.reg；目标观测结果追加到 fits_out/object_N.out
#   5. 全部归算完成后按观测时刻对 object_N.out 排序

import os

import numpy as np

from adias.io.catalog_io import read_catalog, read_ephemeris
from adias.io.fits_io import read_fits_header
from adias.io.text_io import (
    read_reg_file,
    sort_output_file,
    write_object_result,
    write_ref_file,
)
from adias.paths import (
    OUT_DIR,
    REF_DIR,
    ensure_dir,
    list_fits,
    ref_path,
    reg_path,
    stage_dirs,
)
from adias.utils.math_utils import (
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


def _empty_result(n_match1=0, par1=None, x_cen=0.0, y_cen=0.0, ra_cen=0.0, de_cen=0.0):
    """构造默认/失败时的结果 dict，参考星数组按 0 长创建（按需扩容由 caller 做）。"""
    return dict(
        nostar=0,
        nopre=0,
        obj_x=0.0,
        obj_y=0.0,
        obj_flux=0.0,
        snr=0.0,
        obj_obsra=0.0,
        obj_obsde=0.0,
        n_match1=n_match1,
        sig0=0.0,
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


def _find_obj_base_angle(
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
        r["nostar"] = 1
        return r

    # 初始底片常数：仅含旋转角 par(1)=cos par(2)=sin par(4)=-sin par(5)=cos
    ca, sa = np.cos(field_angle * Q), np.sin(field_angle * Q)
    par_init = np.zeros(30)
    par_init[0], par_init[1] = ca, sa
    par_init[3], par_init[4] = -sa, ca

    # ── 阶段一：暴力粗匹配 ────────────────────────────────────────────
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

    if best["n"] < 3:
        print("    粗匹配失败：未找到足够参考星")
        r = _empty_result()
        r["nopre"] = 1
        return r

    # ── 阶段二：精化中心（两次 sol_par） ─────────────────────────────
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
        r = _empty_result()
        r["nopre"] = 1
        return r

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
        r = _empty_result()
        r["nopre"] = 1
        return r

    # ── 阶段三：全图再匹配 ────────────────────────────────────────────
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
        r = _empty_result()
        r["nopre"] = 1
        return r

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
        r = _empty_result()
        r["nopre"] = 1
        return r
    sig1 = sig0 / Q * 3600.0

    # ── 阶段四：预报并抓取目标 ────────────────────────────────────────
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
        r = _empty_result()
        r["nopre"] = 1
        return r

    xn = (obj_x_obs - x_cen) * pscale / fl
    yn = (obj_y_obs - y_cen) * pscale / fl
    obj_obsra, obj_obsde = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
    print(
        f"    实测x/y，实测ra/de：{obj_x_obs:11.5f}{obj_y_obs:11.5f}"
        f"{obj_obsra / Q:11.5f}{obj_obsde / Q:11.5f}"
    )

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
    limit_match,
    obj_ephra,
    obj_ephde,
):
    """复用前一目标的底片常数 par1，直接挑选距离历表位置最近的检测星作为目标。

    不重算底片常数，不输出参考星与 sig0。
    """
    result = _empty_result(
        par1=par1.copy(), x_cen=x_cen, y_cen=y_cen, ra_cen=ra_cen, de_cen=de_cen
    )
    result["nopre"] = 1
    n_det = len(det_x)

    rl0 = limit_match
    for k in range(n_det):
        if det_x[k] <= 0 or det_y[k] <= 0:
            continue
        xn = (det_x[k] - x_cen) * pscale / fl
        yn = (det_y[k] - y_cen) * pscale / fl
        ra_k, de_k = xy2rade(par1[:modeltype], modeltype, xn, yn, ra_cen, de_cen)
        rl = cal_rl(ra_k, de_k, obj_ephra * Q, obj_ephde * Q) / Q * 3600.0
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


# ─────────────────────────────────────────────────────────────────────────
# 对外接口
# ─────────────────────────────────────────────────────────────────────────


def run_match(config, fitspath_list):
    """对每个观测目录的每张原始 .fit 执行匹配归算。

    关键行为（与 Fortran 一致）：
      - GAIA 星表每日重读
      - flag_pre 每幅图重置：每张图的第 1 个目标走 base_angle，后续目标走 prepar
      - base_angle 返回 nostar=1 时，本图剩余目标全部跳过
      - prepar 写 ref.reg 时沿用本图最近一次 base_angle 的参考星数据
      - 写 object_X.out 时 sig0 始终用 base_angle 的值（prepar 不覆盖）
    """
    for idx, fitspath in enumerate(fitspath_list, 1):
        print(f"\n{'#' * 10} 本观测时段，第{idx:02d}日：fits文件夹：{fitspath}")

        # 逐日重读 GAIA 星表
        n_gaia, gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag = read_catalog(
            config["gaiacatpath"], config["min_mag"], config["max_mag"]
        )
        if n_gaia == 0 or gaia_ra is None:
            print("    读取 GAIA 星表失败，跳过本日")
            continue
        print(f"======读取本日配置文件及星表结束，共 {n_gaia} 颗。")

        fits_files = list_fits(fitspath)
        if not fits_files:
            print(f"    本日图像不足，跳过：{fitspath}")
            continue
        n_total = len(fits_files)
        print(f"======本日观测图像数量共计：{n_total} 幅")

        # 产物目录就位
        stages = stage_dirs(fitspath)
        ensure_dir(stages[REF_DIR])
        out_directory = ensure_dir(stages[OUT_DIR])

        # 批量打开 object_N.out
        object_out_files = {}
        for obj in range(1, config["obj_total"] + 1):
            object_out_files[obj] = open(
                os.path.join(out_directory, f"object_{obj}.out"), "w", encoding="utf-8"
            )

        # 逐幅图像
        for n_fits, fitsfile in enumerate(fits_files, 1):
            print(f"\n======当前图像：{n_fits:3d}/{n_total} - {os.path.basename(fitsfile)}")

            hdr = read_fits_header(fitsfile, config["tele_label"])
            if hdr is None:
                continue

            obj_T = (
                hdr["day"]
                + (hdr["hh"] * 3600 + hdr["mm"] * 60 + hdr["ss"] + config["delta_t"])
                / 86400.0
            )
            calpm_epoch = hdr["year"] + ((hdr["month"] - 1) * 30 + hdr["day"]) / 365.0

            # 一次性读检测星表，供本图全部目标共用
            regfile = reg_path(fitspath, os.path.basename(fitsfile))
            det_x, det_y, det_flux, det_snr = read_reg_file(regfile)

            # 每幅图重置 flag_pre
            flag_pre = 0
            pre_par = np.zeros(30)
            pre_x_cen = 0.0
            pre_y_cen = 0.0
            pre_ra_cen = 0.0
            pre_de_cen = 0.0
            last_base_result = None

            skip_image = False
            for obj in range(1, config["obj_total"] + 1):
                print(f"\n*****当前处理目标为：{obj}/{config['obj_total']}")

                n_eph, eph_T, eph_ra, eph_de = read_ephemeris(
                    config["ephpath"][obj - 1]
                )
                print(f"    读取该目标IMCCE历表位置数：{n_eph}")
                obj_ephra = interpolate(eph_T, eph_ra, n_eph, obj_T)
                obj_ephde = interpolate(eph_T, eph_de, n_eph, obj_T)

                n_field, gf_ra, gf_de, gf_mag = extract_field_stars(
                    gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag,
                    n_gaia, obj_ephra, obj_ephde, config["fsize"], calpm_epoch,
                )
                print(f"    用于匹配的恒星数量：{n_field}")

                if flag_pre < 1:
                    print("    ----自动寻星检测确定底片常数")
                    result = _find_obj_base_angle(
                        det_x, det_y, det_flux, det_snr,
                        os.path.basename(fitsfile),
                        config["field_angle"], config["pscale"], config["fl"],
                        config["limit_match"], obj_ephra, obj_ephde,
                        gf_ra, gf_de, gf_mag, n_field, config["modeltype"],
                    )

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

                    # 精度达标则保存底片常数给后续目标使用
                    if 0.0001 < result["sig0"] < 0.06 and result["n_match1"] > 10:
                        flag_pre = 1
                        pre_par = result["par1"].copy()
                        pre_x_cen = result["x_center"]
                        pre_y_cen = result["y_center"]
                        pre_ra_cen = result["ra_center"]
                        pre_de_cen = result["de_center"]

                    last_base_result = result
                else:
                    print("    ----使用pre_par归算(sig<0.06 & n_match>10)")
                    result = _find_obj_base_prepar(
                        det_x, det_y, det_flux, det_snr,
                        pre_par, config["pscale"], config["fl"], config["modeltype"],
                        pre_x_cen, pre_y_cen, pre_ra_cen, pre_de_cen,
                        config["limit_match"], obj_ephra, obj_ephde,
                    )

                    if result["nopre"] < 1:
                        print(
                            f"    目标星x/y/obsra/obsde位置："
                            f"{result['obj_x']:10.3f}{result['obj_y']:10.3f}"
                            f"{result['obj_obsra']:10.3f}{result['obj_obsde']:10.3f}"
                        )
                        print("    其余参数同前")

                # 写 ref.reg：prepar 模式沿用本图最近一次 base_angle 的参考星
                ref_data = result if flag_pre < 1 else last_base_result
                if ref_data is not None and ref_data.get("n_match1", 0) > 0:
                    write_ref_file(
                        ref_path(fitspath, os.path.basename(fitsfile), obj), ref_data
                    )

                # 写 object_N.out：sig0 始终用 base_angle 的值
                if flag_pre < 1:
                    sig_for_write = result.get("sig0", 0.0)
                else:
                    sig_for_write = (
                        last_base_result["sig0"] if last_base_result is not None else 0.0
                    )
                if 0.0001 < abs(sig_for_write) < 1.0:
                    write_object_result(
                        object_out_files[obj],
                        hdr["year"], hdr["month"], obj_T,
                        result["obj_obsra"], result["obj_obsde"],
                        obj_ephra, obj_ephde, sig_for_write,
                        hdr["hh"], hdr["mm"], hdr["ss"], hdr["exptime"],
                        fitsfile, config["field_angle"],
                    )
                    print(f"    写入out文件的结果，文件名：object_{obj}")

                print("=====当前图像处理完毕，处理下一个目标=====")

            if skip_image:
                print("======本图无检测星，跳过，处理下一幅图像======")
                continue
            print("======本幅图像处理完毕，处理下一幅图像======")

        # 关闭 + 按观测时刻排序
        for f in object_out_files.values():
            f.close()
        for obj in range(1, config["obj_total"] + 1):
            sort_output_file(os.path.join(out_directory, f"object_{obj}.out"))

        print(f"\n   本日匹配共归算天然卫星目标个数 {config['obj_total']}")
        print("=================================================================")

    print(f"\n   本时段观测任务匹配结束，共匹配天数：{len(fitspath_list)}")
    print("=================================================================")
