"""根据仓库内已有的 outputs/results/**/*N.dat 统计各目标 O-C 离散度并绘图。

    python docs/assets/src/plot_oc_dispersion.py

只读取已提交的 comoc 汇总结果（第 14、15 列：Δα·cosδ、Δδ，单位角秒），
不运行任何处理流程。输出：
    docs/assets/nspa-oc-dispersion.png
    docs/assets/nspa-oc-stats.csv
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "outputs" / "results"
ASSETS = REPO / "docs" / "assets"

# (目录, 目标名前缀, 展示名)；U/2020 与 U/2020_rix 为同一观测期的两套归档结果
DATASETS = [
    ("U/2020", "U", "U/2020"),
    ("U/2020_rix", "U", "U/2020_rix"),
    ("S/2023", "S", "S/2023"),
    ("S9/2024", "S9", "S9/2024"),
    ("S9/2025", "S9", "S9/2025"),
]

C_RA = "#2a78d6"
C_DE = "#eb6834"


def load_stats():
    rows = []
    for rel, prefix, label in DATASETS:
        for fp in sorted((RESULTS / rel).glob("*.dat")):
            if fp.stat().st_size == 0:
                continue
            a = np.loadtxt(fp, usecols=(0, 1, 2, 13, 14), ndmin=2)
            idx = fp.stem[-1]
            name = prefix if prefix == "S9" else f"{prefix}{idx}"
            rows.append(dict(
                dataset=label, target=name, n=len(a),
                year_month=f"{int(a[0, 0])}-{int(a[0, 1]):02d}",
                nights=len(set(np.floor(a[:, 2]).astype(int))),
                mean_ra=a[:, 3].mean(), std_ra=a[:, 3].std(ddof=1),
                mean_de=a[:, 4].mean(), std_de=a[:, 4].std(ddof=1),
            ))
    return rows


def main():
    rows = load_stats()
    with open(ASSETS / "nspa-oc-stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "target", "year_month", "nights", "n",
                    "mean_ra_cosdec_arcsec", "std_ra_cosdec_arcsec",
                    "mean_dec_arcsec", "std_dec_arcsec"])
        for r in rows:
            w.writerow([r["dataset"], r["target"], r["year_month"], r["nights"], r["n"],
                        f"{r['mean_ra']:.3f}", f"{r['std_ra']:.3f}",
                        f"{r['mean_de']:.3f}", f"{r['std_de']:.3f}"])

    plt.rcParams.update({
        "font.family": ["Noto Sans CJK SC", "Noto Sans CJK JP", "Source Han Sans SC", "Microsoft YaHei",
                        "PingFang SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
    })
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10, 0.36 * n + 1.9), dpi=160)
    fig.patch.set_facecolor("#ffffff")
    ys = np.arange(n)[::-1]
    prev = None
    for y, r in zip(ys, rows):
        if prev is not None and r["dataset"] != prev:
            ax.axhline(y + 0.5, color="#d0d7de", lw=0.8)
        prev = r["dataset"]
        ax.plot([r["std_ra"], r["std_de"]], [y, y], color="#c9d1d9", lw=1.5, zorder=1)
        ax.scatter(r["std_ra"], y, s=46, color=C_RA, marker="o", zorder=3,
                   edgecolor="white", linewidth=1.2)
        ax.scatter(r["std_de"], y, s=46, color=C_DE, marker="s", zorder=3,
                   edgecolor="white", linewidth=1.2)
        ax.text(1.01, y, f"n={r['n']}", va="center", ha="left", fontsize=8.5,
                color="#59636e", transform=ax.get_yaxis_transform())
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{r['dataset']}  {r['target']}" for r in rows], fontsize=9.5,
                       color="#1f2328")
    ax.set_xlim(0, 0.2)
    ax.set_xlabel("剔除野值后 O-C 标准差（角秒）", fontsize=10, color="#1f2328")
    ax.grid(axis="x", color="#eaeef2", lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#8c959f")
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors="#59636e")
    h1 = ax.scatter([], [], s=46, color=C_RA, marker="o", label="σ(Δα·cosδ)")
    h2 = ax.scatter([], [], s=46, color=C_DE, marker="s", label="σ(Δδ)")
    ax.legend(handles=[h1, h2], loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2,
              frameon=False, fontsize=9.5)
    fig.suptitle("仓库已归档 O-C 结果：各目标剔除野值后的标准差", x=0.02, ha="left",
                 fontsize=12.5, fontweight="bold", color="#1f2328")
    fig.text(0.02, 0.005, "数据：outputs/results/**/*N.dat 第 14、15 列；各数据集观测条件与参数不同，"
             "不宜横向比较优劣。", fontsize=8.5, color="#59636e")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(ASSETS / "nspa-oc-dispersion.png", facecolor="#ffffff")
    print("written:", ASSETS / "nspa-oc-dispersion.png", ASSETS / "nspa-oc-stats.csv")


if __name__ == "__main__":
    main()
