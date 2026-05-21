# 功能：05report O-C 散点图绘制，复现 all_data.m 的功能。
# 输入：config['newoutfile0'] 目录下由 04comoc 生成的 *N.dat 文件。
# 输出：outdir/OC_summary.png  （以及可选的每颗卫星单独图）
#
# .dat 文件列说明（space-delimited，1-based与 MATLAB 对齐）：
#   col 1  : year
#   col 2  : month
#   col 3  : day.fraction  （观测时刻，UTC 天的小数）
#   col 4-6: RA  h m s
#   col 7-9: DE  ±d m s
#   col 10 : obs_ra  (deg)
#   col 11 : obs_de  (deg)
#   col 12 : eph_ra  (deg)
#   col 13 : eph_de  (deg)
#   col 14 : Δα·cosδ  O-C (arcsec)   ← MATLAB a(:,14)
#   col 15 : Δδ       O-C (arcsec)   ← MATLAB a(:,15)
#   col 16 : sig0
#   col 17 : obs_hh
#   col 18 : obs_mm
#   col 19 : obs_ss
#   col 20 : exptime                  ← MATLAB a(:,20)
#   col 21+: filename ...

import glob
import os
import re
from collections import defaultdict

import matplotlib
import numpy as np

matplotlib.use("Agg")  # 非交互后端，适合服务器/脚本环境
import matplotlib.pyplot as plt

# ── 颜色 / 时间偏移 / 卫星标签（与 MATLAB 脚本完全对应）────────────────────
_COLORS = ["r", "b", "k", "g", "c"]
_T_OFFSET = [0.00, 0.15, 0.30, 0.45, 0.60]  # 各卫星时间轴错开量（天）
_MONTH_EN = {
    1: "Jan.",
    2: "Feb.",
    3: "Mar.",
    4: "Apr.",
    5: "May",
    6: "Jun.",
    7: "Jul.",
    8: "Aug.",
    9: "Sep.",
    10: "Oct.",
    11: "Nov.",
    12: "Dec.",
}


# ─────────────────────────────────────────────────────────────────────────────
# 内部工具函数
# ─────────────────────────────────────────────────────────────────────────────


def _load_dat(filepath):
    """
    读取单个 .dat 文件，返回记录列表。

    Parameters
    ----------
    filepath : str

    Returns
    -------
    list[dict]，每条记录含：year, month, t, ra_oc, de_oc, exptime
    """
    records = []
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 20:
                    continue
                try:
                    records.append(
                        {
                            "year": int(parts[0]),
                            "month": int(parts[1]),
                            "t": float(parts[2]),  # col 3  : day fraction
                            "ra_oc": float(parts[13]),  # col 14 : Δα·cosδ (")
                            "de_oc": float(parts[14]),  # col 15 : Δδ (")
                            "exptime": float(parts[19]),  # col 20 : exptime
                        }
                    )
                except (ValueError, IndexError) as e:
                    print(
                        f"  [警告] {os.path.basename(filepath)} 第 {lineno} 行解析失败：{e}"
                    )
    except Exception as e:
        print(f"  [错误] 无法读取 {filepath}：{e}")
    return records


def _discover_dat_files(outdir, obj_total):
    """
    在 outdir 中发现各卫星编号对应的 .dat 数据文件。

    支持两种命名规则（自动识别）：
    - MATLAB 风格  : ``YYYYMMN.dat``  (7 位前缀 + 卫星编号)
    - 当前项目风格 : ``<任意前缀>N.dat``  (末尾数字 = 卫星编号)

    Parameters
    ----------
    outdir    : str，comoc 输出目录
    obj_total : int，卫星总数

    Returns
    -------
    dict  {obj_idx(int): list[str]}，每颗卫星对应的文件路径列表（已排序）
    """
    found = {obj: [] for obj in range(1, obj_total + 1)}
    pat = re.compile(r"^(.+?)(\d)$")  # 末尾一位数字 = 卫星编号

    for fp in sorted(glob.glob(os.path.join(outdir, "*.dat"))):
        stem = os.path.splitext(os.path.basename(fp))[0]
        m = pat.match(stem)
        if not m:
            continue
        idx = int(m.group(2))
        if 1 <= idx <= obj_total:
            found[idx].append(fp)

    return found


def _collect_by_period(dat_files, obj_total):
    """
    读入所有 .dat 文件并按 (year, month) 分组。

    Returns
    -------
    dict  { (year, month): { obj_idx: {'t': ndarray, 'ra': ndarray, 'de': ndarray} } }
    """
    # 用 defaultdict 先收集 list，之后转 ndarray
    raw = defaultdict(
        lambda: {obj: {"t": [], "ra": [], "de": []} for obj in range(1, obj_total + 1)}
    )

    for obj_idx in range(1, obj_total + 1):
        for fp in dat_files[obj_idx]:
            for rec in _load_dat(fp):
                key = (rec["year"], rec["month"])
                raw[key][obj_idx]["t"].append(rec["t"])
                raw[key][obj_idx]["ra"].append(rec["ra_oc"])
                raw[key][obj_idx]["de"].append(rec["de_oc"])

    # list → ndarray
    result = {}
    for key, sats in raw.items():
        result[key] = {
            obj: {
                "t": np.array(v["t"]),
                "ra": np.array(v["ra"]),
                "de": np.array(v["de"]),
            }
            for obj, v in sats.items()
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 绘图函数
# ─────────────────────────────────────────────────────────────────────────────


def _plot_period_row(ax_ra, ax_de, period_data, obj_total, year, month):
    """
    在一对子图（ax_ra / ax_de）上绘制单个观测时段的 O-C 散点。

    Parameters
    ----------
    ax_ra, ax_de : matplotlib Axes
    period_data  : dict  { obj_idx: {'t', 'ra', 'de'} }
    obj_total    : int
    year, month  : int
    """
    month_str = _MONTH_EN.get(month, str(month))
    xlabel = f"Time in day (UTC) in {month_str} {year}"
    legend_handles = []

    for obj_idx in range(1, obj_total + 1):
        seg = period_data.get(obj_idx, {})
        t_arr = seg.get("t", np.array([]))
        ra_arr = seg.get("ra", np.array([]))
        de_arr = seg.get("de", np.array([]))

        if t_arr.size == 0:
            continue

        color = _COLORS[obj_idx - 1]
        offset = _T_OFFSET[obj_idx - 1]
        label = f"U{obj_idx}"

        (h,) = ax_ra.plot(
            t_arr + offset, ra_arr, ".", color=color, markersize=6, label=label
        )
        ax_de.plot(t_arr + offset, de_arr, ".", color=color, markersize=6, label=label)
        legend_handles.append(h)

    # 装饰 RA 子图
    ax_ra.set_xlabel(xlabel, fontsize=8)
    ax_ra.set_ylabel(r"$\Delta\alpha\cos\delta$ (\")", fontsize=9)
    ax_ra.grid(True, linewidth=0.5, alpha=0.7)
    if legend_handles:
        ax_ra.legend(
            handles=legend_handles,
            fontsize=7,
            loc="upper right",
            markerscale=1.5,
            framealpha=0.6,
        )

    # 装饰 DE 子图
    ax_de.set_xlabel(xlabel, fontsize=8)
    ax_de.set_ylabel(r"$\Delta\delta$ (\")", fontsize=9)
    ax_de.grid(True, linewidth=0.5, alpha=0.7)


def _build_summary_figure(all_period_data, periods, obj_total, outdir):
    """
    生成多时段汇总图（n_periods 行 × 2 列），保存为 OC_summary.png。
    """
    n = len(periods)
    fig, axes = plt.subplots(
        n,
        2,
        figsize=(14, 3.8 * n),
        squeeze=False,
    )
    fig.suptitle("O-C Residuals Summary", fontsize=13, y=1.01)

    for row, (year, month) in enumerate(periods):
        _plot_period_row(
            axes[row, 0],
            axes[row, 1],
            all_period_data[(year, month)],
            obj_total,
            year,
            month,
        )

    fig.tight_layout()
    out_path = os.path.join(outdir, "OC_summary.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  汇总图已保存：{out_path}")
    return out_path


def _build_per_satellite_figures(all_period_data, periods, obj_total, outdir):
    """
    为每颗卫星生成单独的多时段图（可选），保存为 OC_UN.png。
    """
    saved = []
    for obj_idx in range(1, obj_total + 1):
        n = len(periods)
        fig, axes = plt.subplots(n, 2, figsize=(14, 3.5 * n), squeeze=False)
        fig.suptitle(f"O-C Residuals — U{obj_idx}", fontsize=12, y=1.01)

        for row, (year, month) in enumerate(periods):
            seg = all_period_data[(year, month)].get(obj_idx, {})
            month_str = _MONTH_EN.get(month, str(month))
            xlabel = f"Time in day (UTC) in {month_str} {year}"
            color = _COLORS[obj_idx - 1]

            t_arr = seg.get("t", np.array([]))
            ra_arr = seg.get("ra", np.array([]))
            de_arr = seg.get("de", np.array([]))

            ax_ra, ax_de = axes[row, 0], axes[row, 1]

            if t_arr.size > 0:
                ax_ra.plot(t_arr, ra_arr, ".", color=color, markersize=6)
                ax_de.plot(t_arr, de_arr, ".", color=color, markersize=6)

            ax_ra.set_xlabel(xlabel, fontsize=8)
            ax_ra.set_ylabel(r"$\Delta\alpha\cos\delta$ (\")", fontsize=9)
            ax_ra.grid(True, linewidth=0.5, alpha=0.7)

            ax_de.set_xlabel(xlabel, fontsize=8)
            ax_de.set_ylabel(r"$\Delta\delta$ (\")", fontsize=9)
            ax_de.grid(True, linewidth=0.5, alpha=0.7)

        fig.tight_layout()
        out_path = os.path.join(outdir, f"OC_U{obj_idx}.png")
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        saved.append(out_path)
        print(f"  U{obj_idx} 图已保存：{out_path}")

    return saved


# ─────────────────────────────────────────────────────────────────────────────
# 公开入口
# ─────────────────────────────────────────────────────────────────────────────


def run_report(config, outdir=None, per_satellite=True):
    """
    读取 comoc 输出的 .dat 文件，生成 O-C 散点图。

    生成文件
    --------
    - ``outdir/OC_summary.png``      所有时段、所有卫星的汇总图
    - ``outdir/OC_U1.png`` ~ ``OC_U5.png``  各卫星单独图（per_satellite=True 时）

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    outdir        : str | None，数据目录，默认使用 config['newoutfile0']
    per_satellite : bool，是否额外生成每颗卫星的单独图（默认 True）
    """
    if outdir is None:
        outdir = config["newoutfile0"]

    obj_total = config.get("obj_total", 5)

    print(f"\n{'=' * 50}")
    print(f"05report 开始 — 读取目录：{outdir}")

    if not os.path.isdir(outdir):
        print(f"  [错误] 输出目录不存在：{outdir}")
        print("05report 跳过。")
        return

    # ── 发现数据文件 ──────────────────────────────────────────────────────────
    dat_files = _discover_dat_files(outdir, obj_total)

    total_files = sum(len(v) for v in dat_files.values())
    if total_files == 0:
        print(f"  [警告] 在 {outdir} 中未找到任何 .dat 文件，跳过绘图。")
        return

    print(f"  发现 .dat 文件共 {total_files} 个：")
    for obj_idx in range(1, obj_total + 1):
        flist = dat_files[obj_idx]
        if flist:
            names = ", ".join(os.path.basename(f) for f in flist)
            print(f"    U{obj_idx}: {names}")

    # ── 读取数据并按时段分组 ─────────────────────────────────────────────────
    all_period_data = _collect_by_period(dat_files, obj_total)

    if not all_period_data:
        print("  [警告] 所有文件均无有效数据行，跳过绘图。")
        return

    periods = sorted(all_period_data.keys())  # 按 (year, month) 升序

    # 统计概要
    print(f"\n  数据概要（共 {len(periods)} 个观测时段）：")
    for year, month in periods:
        month_str = _MONTH_EN.get(month, str(month))
        counts = [
            len(all_period_data[(year, month)][obj]["t"])
            for obj in range(1, obj_total + 1)
        ]
        count_str = "  ".join(f"U{o}:{c}" for o, c in enumerate(counts, 1) if c > 0)
        print(f"    {year} {month_str:4s}  —  {count_str}")

    # ── 生成汇总图 ────────────────────────────────────────────────────────────
    _build_summary_figure(all_period_data, periods, obj_total, outdir)

    # ── 生成各卫星单独图（可选）──────────────────────────────────────────────
    if per_satellite:
        _build_per_satellite_figures(all_period_data, periods, obj_total, outdir)

    print(f"\n{'=' * 50}")
    print("05report 完成。")
