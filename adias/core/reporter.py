"""05report：扫 comoc 产物 .dat，绘制 O-C 散点图。

读取：comoc.output_dir 下由 04comoc 生成的 *N.dat 文件。
输出：outdir/OC_summary.png  以及每颗卫星单独的 OC_UN.png。

.dat 列说明（space-delimited，1-based 与上游 MATLAB 脚本对齐）：
  col 1  : year
  col 2  : month
  col 3  : day.fraction  （观测时刻，UTC 天的小数）
  col 4-6: RA  h m s
  col 7-9: DE  ±d m s
  col 10 : obs_ra  (deg)
  col 11 : obs_de  (deg)
  col 12 : eph_ra  (deg)
  col 13 : eph_de  (deg)
  col 14 : Δα·cosδ  O-C (arcsec)
  col 15 : Δδ       O-C (arcsec)
  col 16 : sig0
  col 17 : obs_hh
  col 18 : obs_mm
  col 19 : obs_ss
  col 20 : exptime
  col 21+: filename ...
"""

import re
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

from adias.application.log import get_logger
from adias.application.pipeline import StepResult

matplotlib.use("Agg")  # 非交互后端，适合服务器/脚本环境
import matplotlib.pyplot as plt

_log = get_logger("report")

# ── 颜色 / 时间偏移 / 卫星标签（与上游脚本对应） ──────────────────────────
_COLORS = ["r", "b", "k", "g", "c"]
_T_OFFSET = [0.00, 0.15, 0.30, 0.45, 0.60]  # 各卫星时间轴错开量（天）
_MONTH_EN = {
    1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.", 5: "May", 6: "Jun.",
    7: "Jul.", 8: "Aug.", 9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dec.",
}


# ── 内部工具函数 ──────────────────────────────────────────────────────────


def _load_dat(filepath):
    """读取单个 .dat 文件，返回记录列表，每条含 year/month/t/ra_oc/de_oc/exptime。"""
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
                            "t": float(parts[2]),
                            "ra_oc": float(parts[13]),
                            "de_oc": float(parts[14]),
                            "exptime": float(parts[19]),
                        }
                    )
                except (ValueError, IndexError) as e:
                    _log.info(f"  警告：{Path(filepath).name} 第 {lineno} 行解析失败：{e}")
    except Exception as e:
        _log.info(f"  错误：无法读取 {filepath}：{e}")
    return records


def _discover_dat_files(outdir, obj_total):
    """按 .dat 文件名末尾数字归类到卫星编号，返回 {obj_idx: [path,...]}。"""
    found = {obj: [] for obj in range(1, obj_total + 1)}
    pat = re.compile(r"^(.+?)(\d)$")  # 末尾一位数字 = 卫星编号

    for fp in sorted(outdir.glob("*.dat")):
        stem = fp.stem
        m = pat.match(stem)
        if not m:
            continue
        idx = int(m.group(2))
        if 1 <= idx <= obj_total:
            found[idx].append(fp)

    return found


def _collect_by_period(dat_files, obj_total):
    """读入 .dat 并按 (year, month) → obj_idx → {t, ra, de} 分组（值为 ndarray）。"""
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


# ── 绘图函数 ──────────────────────────────────────────────────────────────


def _plot_period_row(ax_ra, ax_de, period_data, obj_total, year, month):
    """在 (ax_ra, ax_de) 子图对上绘制单个观测时段的 O-C 散点。"""
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

    ax_de.set_xlabel(xlabel, fontsize=8)
    ax_de.set_ylabel(r"$\Delta\delta$ (\")", fontsize=9)
    ax_de.grid(True, linewidth=0.5, alpha=0.7)


def _build_summary_figure(all_period_data, periods, obj_total, outdir):
    """生成多时段汇总图（n_periods 行 × 2 列），保存为 OC_summary.png。"""
    n = len(periods)
    fig, axes = plt.subplots(n, 2, figsize=(14, 3.8 * n), squeeze=False)
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
    out_path = outdir / "OC_summary.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    _log.info(f"  汇总图已保存：{out_path}")
    return out_path


def _build_per_satellite_figures(all_period_data, periods, obj_total, outdir):
    """为每颗卫星生成单独的多时段图（可选），保存为 OC_UN.png。"""
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
        out_path = outdir / f"OC_U{obj_idx}.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        saved.append(out_path)
        _log.info(f"  U{obj_idx} 图已保存：{out_path}")

    return saved


# ── 公开入口 ──────────────────────────────────────────────────────────────


def run_report(config, outdir=None):
    """读取 comoc 的 .dat 文件，生成 OC_summary.png 及各卫星单独图。

    outdir 默认取 config.comoc.output_dir；per_satellite 由 config.report 控制。
    """
    result = StepResult("report")
    if outdir is None:
        outdir = Path(config.comoc.output_dir)
    else:
        outdir = Path(outdir)

    obj_total = config.match.obj_total or 5
    per_satellite = config.report.per_satellite

    _log.info(f"\n{'=' * 50}")
    _log.info(f"05report 开始 — 读取目录：{outdir}")

    if not outdir.is_dir():
        _log.info(f"  错误：输出目录不存在：{outdir}")
        _log.info("05report 跳过。")
        result.warnings.append(f"report: 输出目录不存在 {outdir}")
        result.failed_items.append(str(outdir))
        return result

    dat_files = _discover_dat_files(outdir, obj_total)

    total_files = sum(len(v) for v in dat_files.values())
    if total_files == 0:
        _log.info(f"  警告：在 {outdir} 中未找到任何 .dat 文件，跳过绘图。")
        result.warnings.append(f"report: 未发现 .dat {outdir}")
        return result

    _log.info(f"  发现 .dat 文件共 {total_files} 个：")
    for obj_idx in range(1, obj_total + 1):
        flist = dat_files[obj_idx]
        if flist:
            names = ", ".join(p.name for p in flist)
            _log.info(f"    U{obj_idx}: {names}")

    all_period_data = _collect_by_period(dat_files, obj_total)

    if not all_period_data:
        _log.info("  警告：所有文件均无有效数据行，跳过绘图。")
        result.warnings.append(f"report: 无有效数据行 {outdir}")
        return result

    periods = sorted(all_period_data.keys())

    _log.info(f"\n  数据概要（共 {len(periods)} 个观测时段）：")
    for year, month in periods:
        month_str = _MONTH_EN.get(month, str(month))
        counts = [
            len(all_period_data[(year, month)][obj]["t"])
            for obj in range(1, obj_total + 1)
        ]
        count_str = "  ".join(f"U{o}:{c}" for o, c in enumerate(counts, 1) if c > 0)
        _log.info(f"    {year} {month_str:4s}  —  {count_str}")

    summary_path = _build_summary_figure(all_period_data, periods, obj_total, outdir)
    result.output_files.append(str(summary_path))

    if per_satellite:
        result.output_files.extend(
            str(p) for p in _build_per_satellite_figures(
                all_period_data, periods, obj_total, outdir
            )
        )

    _log.info(f"\n{'=' * 50}")
    _log.info("05report 完成。")
    return result
