"""用仓库自身的匹配函数，对单帧归档产物重建底片常数与目标定位（只读，不改算法）。

    python docs/assets/src/reconstruct_frame.py --materials <含 inputs/ 的归档目录>

输入（均为归档产物，不重跑 pre/detect）：
    <materials>/inputs/images/S9/2024/202411/20241103/fits/20241103S9001I.fit       原始 FITS（只读头）
    <materials>/inputs/images/S9/2024/202411/20241103/fits_reg/20241103S9001I.fit.reg 检测星
    <materials>/inputs/images/S9/2024/202411/20241103/fits_ref/20241103S9001I.fit1.ref.reg 归档参考星
    <materials>/inputs/images/S9/2024/202411/20241103/fits_out/object_1.out          归档归算结果
    inputs/configs/nspa2024.cfg、GAIA3_S9_202410.DAT、EPH_S9_202411.DAT

流程与 core/matcher.py 对单帧第 1 个目标完全相同：
    读 FITS 头 → 曝光中点 → 历表插值 → 视场 GAIA 截取 + 自行改正 → find_obj_base_angle。
然后把重建结果与归档 object_1.out、ref.reg 逐项比对，写出
    docs/assets/nspa-frame-solution.json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from nspa.config import load_config  # noqa: E402
from nspa.domain.astrometry import DEG2RAD, extract_field_stars, sol_par, xy2rade  # noqa: E402
from nspa.domain.matching import find_obj_base_angle  # noqa: E402
from nspa.io.catalog_io import read_catalog, read_ephemeris  # noqa: E402
from nspa.io.fits_io import read_fits_header  # noqa: E402
from nspa.io.text_io import read_reg_file  # noqa: E402
from nspa.utils.math_utils import interpolate  # noqa: E402

FRAME = "20241103S9001I"
DAY = Path("inputs/images/S9/2024/202411/20241103")
OUT_JSON = REPO / "docs" / "assets" / "nspa-frame-solution.json"


def read_ref_reg(path):
    """归档 ref.reg：x, y, RA(8 位小数), Dec(仅 3 位小数), G。"""
    rows = []
    for line in Path(path).read_text().splitlines()[2:]:
        if "ellipse" not in line:
            continue
        head, tail = line.split("#")
        p, q = head.split(), tail.split()
        rows.append((float(p[1]), float(p[2]), float(q[0]), float(q[1]), float(q[2])))
    return np.array(rows)


def read_object_out_line(path, frame):
    for line in Path(path).read_text().splitlines():
        if frame in line:
            p = line.split()
            # year month dayfrac  h m s  d m s  obsra obsde ephra ephde  resra resde sigma ...
            return dict(day_fraction=float(p[2]), obs_ra=float(p[9]), obs_de=float(p[10]),
                        eph_ra=float(p[11]), eph_de=float(p[12]),
                        res_ra=float(p[13]), res_de=float(p[14]), sigma=float(p[15]))
    raise ValueError(f"{frame} not in {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", required=True, type=Path)
    args = ap.parse_args()
    mat = args.materials.resolve()
    day = mat / DAY

    cfg = load_config(str(REPO / "inputs/configs/nspa2024.cfg"), steps=["match"]).match
    hdr = read_fits_header(str(day / "fits" / f"{FRAME}.fit"), cfg.tele_label)
    obj_t = hdr["day"] + (hdr["hh"] * 3600 + hdr["mm"] * 60 + hdr["ss"] + cfg.delta_t) / 86400.0
    epoch = hdr["year"] + ((hdr["month"] - 1) * 30 + hdr["day"]) / 365.0

    gaia_file = REPO / cfg.gaia_catfile
    eph_file = REPO / cfg.eph_files[0]
    n_g, g_ra, g_de, g_pr, g_pd, g_mag = read_catalog(str(gaia_file), cfg.min_mag, cfg.max_mag)
    n_e, e_t, e_ra, e_de = read_ephemeris(str(eph_file))
    eph_ra = interpolate(e_t, e_ra, n_e, obj_t)
    eph_de = interpolate(e_t, e_de, n_e, obj_t)
    n_f, f_ra, f_de, f_mag = extract_field_stars(
        g_ra, g_de, g_pr, g_pd, g_mag, n_g, eph_ra, eph_de, cfg.field_size, epoch)

    det_x, det_y, det_flux, det_snr = read_reg_file(str(day / "fits_reg" / f"{FRAME}.fit.reg"))
    r = find_obj_base_angle(
        det_x, det_y, det_flux, det_snr, FRAME, cfg.plate_angle, cfg.pixel_scale,
        cfg.focal_length, cfg.match_limit, eph_ra, eph_de, f_ra, f_de, f_mag, n_f,
        cfg.model_type)

    nm = cfg.model_type
    pscale, fl = cfg.pixel_scale, cfg.focal_length

    def pix2sky(x, y):
        ra, de = xy2rade(r.par1[:nm], nm, (x - r.x_center) * pscale / fl,
                         (y - r.y_center) * pscale / fl, r.ra_center, r.de_center)
        return ra / DEG2RAD, de / DEG2RAD

    # 参考星拟合残差（像素 → 天球 与 GAIA 历元位置之差）
    refs = []
    for i in range(r.n_match1):
        ra_fit, de_fit = pix2sky(r.ref_x[i], r.ref_y[i])
        refs.append(dict(
            x=round(float(r.ref_x[i]), 3), y=round(float(r.ref_y[i]), 3),
            ra_gaia=float(r.ref_ra[i]), de_gaia=float(r.ref_de[i]), g=round(float(r.ref_mag[i]), 3),
            dra_cosd=round((ra_fit - r.ref_ra[i]) * 3600 * np.cos(r.ref_de[i] * DEG2RAD), 4),
            dde=round((de_fit - r.ref_de[i]) * 3600, 4)))

    # 以最终参考星重算一次 sol_par，得到 2.6σ 迭代后实际参与拟合的星数（与 par1 应一致）
    par_chk, sig_chk, n_used = sol_par(
        (r.ref_x - r.x_center) * pscale / fl, (r.ref_y - r.y_center) * pscale / fl,
        r.ref_ra, r.ref_de, r.n_match1, r.ra_center / DEG2RAD, r.de_center / DEG2RAD, nm)
    lim = 2.6 * sig_chk / DEG2RAD * 3600
    for ref in refs:
        ref["used_in_fit"] = bool(abs(ref["dra_cosd"]) < lim and abs(ref["dde"]) < lim)

    # 历表位置反推到像素（完整模型牛顿迭代，仅用于作图标注）
    x, y = r.obj_x, r.obj_y
    for _ in range(20):
        ra0, de0 = pix2sky(x, y)
        h = 0.5
        rx, dx = pix2sky(x + h, y)
        ry, dy = pix2sky(x, y + h)
        J = np.array([[(rx - ra0) / h, (ry - ra0) / h], [(dx - de0) / h, (dy - de0) / h]])
        step = np.linalg.solve(J, np.array([eph_ra - ra0, eph_de - de0]))
        x, y = x + step[0], y + step[1]
    eph_x, eph_y = float(x), float(y)

    # ---- 与归档产物比对 ----
    arch_ref = read_ref_reg(day / "fits_ref" / f"{FRAME}.fit1.ref.reg")
    arch_out = read_object_out_line(day / "fits_out" / "object_1.out", FRAME)
    ref_xy_maxdiff = None
    if len(arch_ref) == r.n_match1:
        ref_xy_maxdiff = float(np.max(np.abs(arch_ref[:, :2] - np.c_[r.ref_x, r.ref_y])))

    # 归档 ref.reg 的 Dec 只有 3 位小数：用 RA(8 位) + 粗 Dec 在历元化 GAIA 中找唯一对应
    uniq = []
    for xr, yr, ra_a, de_a, g_a in arch_ref:
        d = np.hypot((f_ra - ra_a) * 3600 * np.cos(de_a * DEG2RAD), (f_de - de_a) * 3600)
        cand = np.where((np.abs(f_ra - ra_a) * 3600 < 0.01) & (np.abs(f_de - de_a) < 0.0006))[0]
        uniq.append(dict(n_candidates=int(len(cand)),
                         gaia_de=float(f_de[cand[0]]) if len(cand) == 1 else None,
                         nearest_arcsec=round(float(d.min()), 3)))

    cos_d = np.cos(eph_de * DEG2RAD)
    res_ra = (r.obj_obsra - eph_ra) * 3600 * cos_d
    res_de = (r.obj_obsde - eph_de) * 3600
    out = dict(
        frame=FRAME,
        sources=dict(
            raw_fits=str(DAY / "fits" / f"{FRAME}.fit"),
            detection_reg=str(DAY / "fits_reg" / f"{FRAME}.fit.reg"),
            reference_reg=str(DAY / "fits_ref" / f"{FRAME}.fit1.ref.reg"),
            object_out=str(DAY / "fits_out" / "object_1.out"),
            config="inputs/configs/nspa2024.cfg",
            gaia=cfg.gaia_catfile, ephemeris=cfg.eph_files[0],
            function="nspa.domain.matching.find_obj_base_angle",
        ),
        exposure_mid_utc=f"{hdr['year']}-{hdr['month']:02d}-{hdr['day']:02d} "
                         f"{hdr['hh']:02d}:{hdr['mm']:02d}:{hdr['ss']:05.2f}",
        day_fraction=obj_t,
        pm_epoch=epoch,
        n_detected=int(len(det_x)),
        n_gaia_in_field=int(n_f),
        n_reference=int(r.n_match1),
        n_reference_used_in_fit=int(n_used),
        par_recheck_max_abs_diff=float(np.max(np.abs(par_chk[:nm] - r.par1[:nm]))),
        model_type=nm,
        plate_sigma_arcsec=round(float(r.sig0), 4),
        plate_center=dict(x=r.x_center, y=r.y_center,
                          ra=r.ra_center / DEG2RAD, de=r.de_center / DEG2RAD),
        plate_par=[float(v) for v in r.par1[:nm]],
        pixel_scale_arcsec=float(pscale / fl / DEG2RAD * 3600),
        target=dict(x=r.obj_x, y=r.obj_y, snr=r.snr, obs_ra=r.obj_obsra, obs_de=r.obj_obsde,
                    eph_ra=eph_ra, eph_de=eph_de, eph_x=eph_x, eph_y=eph_y,
                    oc_ra_cosd_arcsec=round(float(res_ra), 4), oc_de_arcsec=round(float(res_de), 4)),
        references=refs,
        gaia_field=[dict(ra=float(a), de=float(b), g=round(float(c), 3))
                    for a, b, c in zip(f_ra, f_de, f_mag)],
        check_vs_archive=dict(
            archived_object_out=arch_out,
            d_obs_ra_arcsec=round((r.obj_obsra - arch_out["obs_ra"]) * 3600 * cos_d, 4),
            d_obs_de_arcsec=round((r.obj_obsde - arch_out["obs_de"]) * 3600, 4),
            d_eph_ra_arcsec=round((eph_ra - arch_out["eph_ra"]) * 3600 * cos_d, 4),
            d_eph_de_arcsec=round((eph_de - arch_out["eph_de"]) * 3600, 4),
            d_sigma_arcsec=round(float(r.sig0) - arch_out["sigma"], 4),
            archived_ref_count=int(len(arch_ref)),
            ref_xy_max_abs_diff_px=ref_xy_maxdiff,
            ref_unique_gaia=uniq,
        ),
    )
    OUT_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    c = out["check_vs_archive"]
    print(f"refs {r.n_match1} / archived {len(arch_ref)}; ref xy maxdiff {ref_xy_maxdiff}")
    print(f"sigma {r.sig0:.4f} vs archived {arch_out['sigma']}")
    print(f"target x/y {r.obj_x:.3f} {r.obj_y:.3f}; eph x/y {eph_x:.3f} {eph_y:.3f}")
    print(f"O-C {res_ra:.4f} {res_de:.4f} vs archived {arch_out['res_ra']} {arch_out['res_de']}")
    print("d_obs", c["d_obs_ra_arcsec"], c["d_obs_de_arcsec"], "d_eph", c["d_eph_ra_arcsec"], c["d_eph_de_arcsec"])
    print("n_used", n_used, "par recheck", out["par_recheck_max_abs_diff"], [x["used_in_fit"] for x in refs])
    print("unique GAIA candidates per ref:", [u["n_candidates"] for u in uniq])
    print("wrote", OUT_JSON)


if __name__ == "__main__":
    main()
