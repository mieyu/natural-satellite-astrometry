"""流水线各阶段的文本/区域文件 IO。
包含：.reg（DS9 region）、object_X.out（匹配结果）、final_oc / final_object（comoc）。
"""

import numpy as np

from adias.utils.math_utils import am2hms


# ── DS9 region 文件（.reg / .ref.reg） ───────────────────────────────────

def write_reg_file(reg_path, stars, bkgd, bkgdsigma, snr_threshold):
    """将检测星表写为 DS9 region 文件，并按 snr/star_pix/overflag 三重过滤。"""
    n_out = 0
    with open(reg_path, "w") as f:
        f.write(
            'global color=green font="helvetica 10 normal" '
            "select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n"
        )
        f.write("physical\n")
        for s in stars:
            if s["snr"] > snr_threshold and s["star_pix"] > 5 and s["overflag"] < 1:
                f.write(
                    f"ellipse {s['starx']:11.3f}{s['stary']:11.3f}"
                    f"{10.0:6.1f}{10.0:6.1f}   #  "
                    f"{s['sumi']:21.4f}{s['snr']:10.2f}"
                    f"{s['star_id']:5d}{s['star_pix']:5d}{s['overflag']:5d}"
                    f"{bkgd:15.3f}{bkgdsigma:15.3f}\n"
                )
                n_out += 1
    return n_out


def read_reg_file(regfile):
    """读取 02detect 生成的 .reg 文件，返回 (det_x, det_y, det_flux, snr) 四个 ndarray。"""
    det_x, det_y, det_flux, snr = [], [], [], []
    try:
        with open(regfile, "r") as f:
            lines = f.readlines()
        for line in lines[2:]:
            line = line.strip()
            if not line or "ellipse" not in line.lower():
                continue
            try:
                parts = line.split()
                x, y = float(parts[1]), float(parts[2])
                hi = line.find("#")
                if hi != -1:
                    ap = line[hi + 1:].split()
                    if len(ap) >= 2:
                        det_x.append(x)
                        det_y.append(y)
                        det_flux.append(float(ap[0]))
                        snr.append(float(ap[1]))
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"读取 reg 文件错误：{regfile}，{e}")
    return np.array(det_x), np.array(det_y), np.array(det_flux), np.array(snr)


def write_ref_file(filename, result):
    """写参考星 DS9 region 文件（*.ref.reg）。result 由 matcher 返回。"""
    n = result.get("n_match1", 0)
    if n == 0:
        return
    try:
        with open(filename, "w") as f:
            f.write(
                'global color=red font="helvetica 10 normal" '
                "select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n"
            )
            f.write("physical\n")
            for i in range(n):
                f.write(
                    f"ellipse{result['ref_x'][i]:11.3f}{result['ref_y'][i]:11.3f}"
                    f"{15.0:6.1f}{15.0:6.1f}  #  "
                    f"{result['ref_ra'][i]:15.8f}{result['ref_de'][i]:8.3f}"
                    f"{result['ref_mag'][i]:20.10f}\n"
                )
    except Exception as e:
        print(f"写入参考星文件错误：{e}")


# ── object_X.out / final_oc / comoc 写出 ────────────────────────────────

def write_object_result(
    file_handle,
    year,
    month,
    obj_T,
    obj_obsra,
    obj_obsde,
    obj_ephra,
    obj_ephde,
    sig0,
    hh,
    mm,
    ss,
    exptime,
    objfitsfile,
    field_angle,
):
    """向已打开的 object_X.out 追加一行观测结果（|残差| ≥ 10″ 时丢弃）。"""
    Q = np.pi / 180.0
    obj_resra = (obj_obsra - obj_ephra) * 3600.0 * np.cos(obj_ephde * Q)
    obj_resde = (obj_obsde - obj_ephde) * 3600.0
    if abs(obj_resra) >= 10 or abs(obj_resde) >= 10:
        return
    i1, i2, ff, cc, j1, j2, fff = am2hms(obj_obsra * 60.0, obj_obsde * 60.0)
    line = (
        f"{year:6d} {month:02d}{obj_T:10.6f}"
        f"{i1:3d}{i2:3d}{ff:8.4f} {cc}{j1:02d}{j2:3d}{fff:7.3f}"
        f"{obj_obsra:12.7f}{obj_obsde:12.7f}"
        f"{obj_ephra:12.7f}{obj_ephde:12.7f}"
        f"{obj_resra:10.4f}{obj_resde:10.4f}{sig0:10.4f}"
        f"{hh:3d}{mm:3d}{ss:6.2f}{exptime:9.2f} {objfitsfile}{field_angle:7.2f}\n"
    )
    file_handle.write(line)
    print(f"    写入残差 ra/de：{obj_resra:10.4f} / {obj_resde:10.4f}")


def sort_output_file(filename):
    """按观测时刻列对 object_X.out 排序（列 [9:19] = obj_T 浮点字段）。"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
        times = []
        for l in lines:
            try:
                times.append(float(l[9:19]))
            except (ValueError, IndexError):
                times.append(0.0)
        idx = np.argsort(times)
        with open(filename, "w", encoding="utf-8") as f:
            for i in idx:
                f.write(lines[i] + "\n")
    except Exception:
        pass


def read_object_out(filepath):
    """读 object_X.out。RA 残差在 [95:105]，DE 残差在 [105:115]（固定列宽）。"""
    lines, res_ra, res_de = [], [], []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                text = line.rstrip("\n")
                if len(line) >= 115:
                    try:
                        ra = float(line[95:105])
                        de = float(line[105:115])
                        lines.append(text)
                        res_ra.append(ra)
                        res_de.append(de)
                    except ValueError as e:
                        print(f"  警告：第 {i + 1} 行解析失败：{e}")
    except FileNotFoundError:
        pass
    return lines, res_ra, res_de


def write_oc_stat(
    filepath,
    n_raw,
    mean_ra0,
    mean_de0,
    std_ra0,
    std_de0,
    n_new,
    mean_ra,
    mean_de,
    std_ra,
    std_de,
    iloop,
    oc_limit,
    mean_limit,
):
    """写单日单目标的 O-C 统计报告（final_oc_X.out）。"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=================res数据统计结果=================\n")
        f.write(f"  原始数据数量n_obj：{n_raw:4d}\n")
        f.write(f"  原始数据均值ra,de：{mean_ra0:12.4f}{mean_de0:12.4f}\n")
        f.write(f"  原始数据方差ra,de：{std_ra0:12.4f}{std_de0:12.4f}\n")
        if oc_limit > 0.0:
            f.write(f"**** 剔除标准(oc_limit)：{oc_limit:5.2f} ****\n")
        else:
            f.write(f"**** 剔除标准(mean_limit)：{mean_limit:5.2f} ****\n")
        f.write(f"  剔除后数据数量n_new：{n_new:4d}\n")
        f.write(f"  剔除后均值ra,de：{mean_ra:12.4f}{mean_de:12.4f}\n")
        f.write(f"  剔除后方差ra,de：{std_ra:12.4f}{std_de:12.4f}\n")
        f.write(f"  迭代次数：{iloop:2d}\n")


def write_comoc_lines(f_out, f_final, f_obsdata, f_month, kept_lines):
    """剔除野值后的行同时写入 4 个流：day_out / final / obsdata(48 列) / month(147 列)。"""
    for line in kept_lines:
        out147 = (line[:147] if len(line) >= 147 else line) + "\n"
        out48 = (line[:48] if len(line) >= 48 else line) + "\n"
        f_out.write(out147)
        f_final.write(line + "\n")
        f_obsdata.write(out48)
        f_month.write(out147)
