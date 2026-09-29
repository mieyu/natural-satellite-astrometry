"""README 单帧逐阶段证据图：同一帧 20241103S9001I 的 pre / detect / match 与 S9/2024 O-C。

    python docs/assets/src/reconstruct_frame.py  --materials <归档目录>   # 先生成 nspa-frame-solution.json
    python docs/assets/src/make_frame_figures.py --materials <归档目录>

<归档目录> 下需有 inputs/images/S9/2024/202411/20241103/{fits,fits_n,fits_reg,fits_ref}。
原始 FITS 不入库，只读取不改写。所有圈、坐标、计数都直接来自归档 .reg 与重建的底片常数。

像素坐标约定：DS9 physical，1-based。numpy 数组 data[j, i] 的像素中心在 (x, y) = (i + 1, j + 1)，
因此 imshow 使用 origin="lower"、extent=(0.5, N + 0.5, 0.5, N + 0.5)。

输出 docs/assets/：
    nspa-pre-fullframe.png   nspa-pre-zoom.png
    nspa-detect-overlay.png
    nspa-match-overlay.png   nspa-match-sky.png
    nspa-oc-s9-2024.png
并更新 docs/assets/provenance.json。
"""

import argparse
import logging
import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.io import fits  # noqa: E402
from astropy.stats import sigma_clipped_stats  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from nspa.domain.astrometry import DEG2RAD, xy2rade  # noqa: E402

ASSETS = REPO / "docs" / "assets"
FRAME = "20241103S9001I"
DAY = Path("inputs/images/S9/2024/202411/20241103")

VMIN, VMAX = 670.0, 715.0          # 所有原始/预处理图共用的线性灰度（ADU）
ZMIN, ZMAX = 675.0, 760.0          # 检测局部放大（原始/预处理共用）
ZOOM = (300, 1100, 600, 1250)      # 预处理局部对照区域 x0, x1, y0, y1（physical）
CUT_Y = 871                        # 剖面所在行（经过 S9 目标）

C_DET = "#19c24a"                  # 检测星：绿色（与 .reg 的 color=green 一致）
C_REF = "#ff3b30"                  # 参考星：红色（与 .ref.reg 的 color=red 一致）
C_TGT = "#00c8ff"                  # 目标实测
C_EPH = "#ffcc00"                  # 历表位置
C_MISS = "#ff9f1a"                 # 复查标出、未写入 .reg 的源
C_RAW = "#5b6770"
C_PRE = "#1f77d0"

# 中文字体：优先简体中文字形；可用环境变量 NSPA_FONT_DIR 指向含 .otf/.ttf 的目录
for _f in [*Path(os.environ.get("NSPA_FONT_DIR", "/nonexistent")).glob("*.[ot]tf"),
           Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]:
    if _f.exists():
        font_manager.fontManager.addfont(str(_f))
plt.rcParams.update({
    "font.family": ["Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC",
                    "Noto Sans CJK JP", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 13,
    "axes.titlesize": 15,
    "axes.labelsize": 13,
    "savefig.facecolor": "white",
})
XLAB = "x（像素，DS9 physical）"
YLAB = "y（像素，DS9 physical）"


# ── 读取 ──────────────────────────────────────────────────────────────────

def read_reg(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("ellipse"):
            head, tail = line.split("#")
            p, q = head.split(), tail.split()
            rows.append([float(p[1]), float(p[2]), float(p[3])] + [float(v) for v in q])
    return np.array(rows)


def show(ax, img, ext=None):
    n2, n1 = img.shape
    ext = ext or (0.5, n1 + 0.5, 0.5, n2 + 0.5)
    return ax.imshow(img, origin="lower", cmap="gray", vmin=VMIN, vmax=VMAX,
                     extent=ext, interpolation="nearest")


def cut(img, x0, x1, y0, y1):
    """physical 闭区间 [x0,x1]×[y0,y1] 的子图与对应 extent。"""
    sub = img[y0 - 1:y1, x0 - 1:x1]
    return sub, (x0 - 0.5, x1 + 0.5, y0 - 0.5, y1 + 0.5)


def save(fig, name):
    fig.savefig(ASSETS / name, dpi=100)
    plt.close(fig)
    print("wrote", name)


class Plate:
    """重建的 6 参数底片常数：像素 ↔ 天球（调用仓库 xy2rade）。"""

    def __init__(self, sol):
        self.par = np.array(sol["plate_par"])
        self.nm = sol["model_type"]
        c = sol["plate_center"]
        self.xc, self.yc = c["x"], c["y"]
        self.ra0, self.de0 = c["ra"] * DEG2RAD, c["de"] * DEG2RAD
        self.k = 0.0135 / 13300.0   # ccd_scale / tele_focal（nspa2024.cfg）

    def sky(self, x, y):
        ra, de = xy2rade(self.par, self.nm, (np.asarray(x) - self.xc) * self.k,
                         (np.asarray(y) - self.yc) * self.k, self.ra0, self.de0)
        return ra / DEG2RAD, de / DEG2RAD

    def pix(self, ra, de):
        x, y = self.xc, self.yc
        for _ in range(30):
            r0, d0 = self.sky(x, y)
            r1, d1 = self.sky(x + 1, y)
            r2, d2 = self.sky(x, y + 1)
            J = np.array([[r1 - r0, r2 - r0], [d1 - d0, d2 - d0]])
            dx, dy = np.linalg.solve(J, [ra - r0, de - d0])
            x, y = x + dx, y + dy
        return x, y

    def compass(self, x, y):
        """返回像素平面上指向北(+Dec) 与东(+RA) 的单位向量。"""
        ra, de = self.sky(x, y)
        n = np.array(self.pix(ra, de + 1 / 3600)) - [x, y]
        e = np.array(self.pix(ra + 1 / 3600 / np.cos(de * DEG2RAD), de)) - [x, y]
        return n / np.hypot(*n), e / np.hypot(*e)


def draw_compass(ax, plate, x, y, L=170, color="white"):
    n, e = plate.compass(1024, 1024)
    for v, lab in ((n, "N"), (e, "E")):
        ax.annotate("", xy=(x + L * v[0], y + L * v[1]), xytext=(x, y),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=2.2))
        ax.text(x + (L + 55) * v[0], y + (L + 55) * v[1], lab, color=color,
                ha="center", va="center", fontsize=14, fontweight="bold")


# ── 图 1、2：pre ──────────────────────────────────────────────────────────

def fig_pre(raw, pre, stats):
    fig = plt.figure(figsize=(16, 8.9))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.045], left=0.055, right=0.95,
                          top=0.91, bottom=0.15, wspace=0.14)
    x0, x1, y0, y1 = ZOOM
    for i, (img, title, st) in enumerate((
            (raw, "原始帧  fits/20241103S9001I.fit", stats["raw"]),
            (pre, "预处理后  fits_n/20241103S9001I_n.fit（归档产物）", stats["pre"]))):
        ax = fig.add_subplot(gs[0, i])
        im = show(ax, img)
        ax.add_patch(Rectangle((x0 - 0.5, y0 - 0.5), x1 - x0 + 1, y1 - y0 + 1,
                               fill=False, ec="#ffb000", lw=2.2, ls="--"))
        ax.text(x0 + 10, y1 + 25, "局部对照区", color="#ffb000", fontsize=13, fontweight="bold")
        ax.set_title(title, loc="left")
        ax.set_xlabel(XLAB)
        if i == 0:
            ax.set_ylabel(YLAB)
        ax.text(0.02, 0.02, f"背景中值 {st['median']:.1f} ADU\n背景 σ {st['std']:.2f} ADU",
                transform=ax.transAxes, color="white", fontsize=13, va="bottom",
                bbox=dict(fc="black", alpha=0.55, ec="none", pad=5))
    cax = fig.add_subplot(gs[0, 2])
    fig.colorbar(im, cax=cax).set_label("像素值（ADU）")
    fig.text(0.055, 0.035,
             f"两幅图使用同一线性灰度 {VMIN:.0f}–{VMAX:.0f} ADU，未做独立拉伸。"
             "背景统计为全帧 3σ 迭代裁剪（astropy sigma_clipped_stats）；"
             "σ 的下降同时来自中值超级背景扣除与 3×3 均值平滑（enhance_flag=1）。",
             fontsize=12, color="#333")
    save(fig, "nspa-pre-fullframe.png")

    # 局部对照 + 剖面
    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.04], left=0.06, right=0.95,
                          top=0.955, bottom=0.53, wspace=0.13)
    gb = fig.add_gridspec(1, 2, left=0.06, right=0.985, top=0.44, bottom=0.1, wspace=0.2)
    for i, (img, title) in enumerate(((raw, "原始帧（局部）"), (pre, "预处理后（局部，归档产物）"))):
        ax = fig.add_subplot(gs[0, i])
        sub, ext = cut(img, *ZOOM)
        im = show(ax, sub, ext)
        ax.axhline(CUT_Y, color="#ffb000", lw=1.3, ls="--")
        ax.annotate("S9", xy=(439.7, 870.9), xytext=(360, 960), color=C_TGT, fontsize=14,
                    fontweight="bold", arrowprops=dict(arrowstyle="->", color=C_TGT, lw=1.8))
        ax.set_title(title, loc="left")
        ax.set_xlabel(XLAB)
        if i == 0:
            ax.set_ylabel(YLAB)
    fig.colorbar(im, cax=fig.add_subplot(gs[0, 2])).set_label("像素值（ADU）")

    ax = fig.add_subplot(gb[0, 0])
    xs = np.arange(x0, x1 + 1)
    ax.plot(xs, raw[CUT_Y - 1, x0 - 1:x1], color=C_RAW, lw=1.0, label="原始")
    ax.plot(xs, pre[CUT_Y - 1, x0 - 1:x1], color=C_PRE, lw=1.2, label="预处理后")
    ax.set_ylim(655, 760)
    ax.set_xlim(x0, x1)
    ax.set_title(f"沿 y = {CUT_Y} 的像素剖面（虚线处，经过 S9）", loc="left")
    ax.set_xlabel(XLAB)
    ax.set_ylabel("像素值（ADU）")
    ax.legend(loc="upper right", frameon=False)
    ax.grid(alpha=0.3)

    ax = fig.add_subplot(gb[0, 1])
    n = raw.shape[1]
    cols = np.arange(1, n + 1)
    ax.plot(cols, np.median(raw, axis=0), color=C_RAW, lw=1.2, label="原始：逐列中值")
    ax.plot(cols, np.median(raw, axis=1), color=C_RAW, lw=1.2, ls=":", label="原始：逐行中值")
    ax.plot(cols, np.median(pre, axis=0), color=C_PRE, lw=1.4, label="预处理后：逐列中值")
    ax.plot(cols, np.median(pre, axis=1), color=C_PRE, lw=1.4, ls=":", label="预处理后：逐行中值")
    ax.set_ylim(670, 697)
    ax.set_xlim(1, n)
    ax.set_title("全帧逐列 / 逐行背景中值", loc="left")
    ax.set_xlabel("列号 x 或行号 y（像素）")
    ax.set_ylabel("中值（ADU）")
    ax.legend(loc="lower left", frameon=True, framealpha=0.9, ncol=2, fontsize=12)
    ax.grid(alpha=0.3)
    fig.text(0.06, 0.02, f"上排两图同一线性灰度 {VMIN:.0f}–{VMAX:.0f} ADU；"
             f"局部区域 x {ZOOM[0]}–{ZOOM[1]}，y {ZOOM[2]}–{ZOOM[3]}。"
             "原始帧 x = 2048 整列偏低（中值约 578 ADU），超出右下图纵轴范围。",
             fontsize=12, color="#333")
    save(fig, "nspa-pre-zoom.png")


# ── 图 3：detect ──────────────────────────────────────────────────────────

def fig_detect(raw, pre, det, hot, edge):
    fig = plt.figure(figsize=(14, 13.2))
    ax = fig.add_axes([0.08, 0.12, 0.84, 0.82])
    show(ax, raw)
    for k, (x, y, r) in enumerate(det[:, :3], 1):
        ax.add_patch(Circle((x, y), r, fill=False, ec=C_DET, lw=1.8))
        ax.text(x + 20, y + 16, str(k), color=C_DET, fontsize=12, fontweight="bold")
    for x, y in (hot, edge):
        ax.add_patch(Circle((x, y), 22, fill=False, ec=C_MISS, lw=1.8, ls="--"))
    ax.set_title(f"检测结果 .reg 回标到原始帧：{len(det)} 个绿圈（.reg 半径 10 px，编号按 .reg 行序 = 流量降序）",
                 loc="left")
    ax.set_xlabel(XLAB)
    ax.set_ylabel(YLAB)
    fig.text(0.08, 0.02,
             f"原始帧，线性灰度 {VMIN:.0f}–{VMAX:.0f} ADU。圈心 = .reg 中的 (x, y)，DS9 physical 1-based；"
             "按 region 坐标用 matplotlib 渲染，非 DS9 截图。\n"
             "检测在预处理图上进行（两图像素网格相同）。橙色虚线圈为复查时标出的未入表源，不来自 .reg，见下一图。",
             fontsize=12, color="#333")
    save(fig, "nspa-detect-overlay.png")

    snr = det[:, 4]
    cases = [
        (*det[0, :2], f"#1 最亮星\nSNR {snr[0]:.0f}", True),
        (*det[10, :2], f"#11 S9 目标\nSNR {snr[10]:.1f}", True),
        (*det[19, :2], f"#20 较暗星\nSNR {snr[19]:.1f}", True),
        (*det[23, :2], f"#24 表中最暗\nSNR {snr[23]:.1f}", True),
        (*hot, "未入表：单像素热点\n平滑后 9 px < 最少 10 px", False),
        (*edge, "未入表：贴边源\n位于 10 px 边框内", False),
    ]
    half = 25
    fig, axes = plt.subplots(2, 6, figsize=(16, 6.8))
    fig.subplots_adjust(left=0.05, right=0.93, top=0.87, bottom=0.12, wspace=0.32, hspace=0.12)
    for c, (x, y, title, in_reg) in enumerate(cases):
        xi, yi = int(round(x)), int(round(y))
        x0 = min(max(1, xi - half), 2048 - 2 * half)
        y0 = min(max(1, yi - half), 2048 - 2 * half)
        for r, (img, row_name) in enumerate(((raw, "原始帧"), (pre, "预处理后（检测输入）"))):
            a = axes[r, c]
            sub, ext = cut(img, x0, x0 + 2 * half, y0, y0 + 2 * half)
            im = a.imshow(sub, origin="lower", cmap="gray", vmin=ZMIN, vmax=ZMAX, extent=ext,
                          interpolation="nearest")
            if in_reg:
                a.add_patch(Circle((x, y), 10, fill=False, ec=C_DET, lw=2))
                a.plot(x, y, "+", color=C_DET, ms=9, mew=1.5)
            else:
                a.add_patch(Circle((x, y), 10, fill=False, ec=C_MISS, lw=1.8, ls="--"))
            a.tick_params(labelsize=9.5)
            if r == 0:
                a.set_title(title, fontsize=12.5, loc="left", color="#1f2328" if in_reg else "#b35c00")
                a.set_xticklabels([])
            if c == 0:
                a.set_ylabel(row_name, fontsize=13)
    cax = fig.add_axes([0.945, 0.12, 0.012, 0.72])
    fig.colorbar(im, cax=cax).set_label("像素值（ADU）")
    fig.text(0.05, 0.03,
             f"每格 51×51 px，坐标为 DS9 physical；12 格使用同一线性灰度 {ZMIN:.0f}–{ZMAX:.0f} ADU（比全帧图宽，便于同时看清亮星与单像素热点）。"
             "绿圈来自 .reg；橙色虚线圈为复查标出、未写入 .reg 的源。",
             fontsize=11.5, color="#333")
    save(fig, "nspa-detect-zoom.png")


# ── 图 4、5：match ────────────────────────────────────────────────────────

def fig_match(raw, det, ref, sol, plate):
    tgt = sol["target"]
    fig = plt.figure(figsize=(16, 9.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1], left=0.05, right=0.985,
                          top=0.92, bottom=0.1, wspace=0.16)
    ax = fig.add_subplot(gs[0, 0])
    show(ax, raw)
    for x, y in det[:, :2]:
        ax.add_patch(Circle((x, y), 10, fill=False, ec=C_DET, lw=1.3))
    for k, (x, y, r) in enumerate(ref[:, :3], 1):
        ax.add_patch(Circle((x, y), r, fill=False, ec=C_REF, lw=2.0))
        ax.text(x + 26, y - 50, f"R{k}", color=C_REF, fontsize=11.5, fontweight="bold")
    ax.add_patch(Rectangle((tgt["x"] - 20, tgt["y"] - 20), 40, 40, fill=False, ec=C_TGT, lw=2))
    ax.text(tgt["x"] + 30, tgt["y"] + 30, "S9", color=C_TGT, fontsize=14, fontweight="bold")
    draw_compass(ax, plate, 1780, 260)
    ax.set_title(f"绿：检测星 {len(det)}　红：参考星 {len(ref)}（.ref.reg）　蓝框：S9",
                 loc="left")
    ax.set_xlabel(XLAB)
    ax.set_ylabel(YLAB)

    a = fig.add_subplot(gs[0, 1])
    half = 14
    xi, yi = int(round(tgt["x"])), int(round(tgt["y"]))
    sub, ext = cut(raw, xi - half, xi + half, yi - half, yi + half)
    a.imshow(sub, origin="lower", cmap="gray", extent=ext, interpolation="nearest",
             vmin=VMIN, vmax=VMAX + 40)
    a.add_patch(Circle((tgt["x"], tgt["y"]), 10, fill=False, ec=C_DET, lw=1.8))
    a.plot(tgt["x"], tgt["y"], "o", mfc="none", mec=C_TGT, ms=13, mew=2.4,
           label=f"实测质心 ({tgt['x']:.2f}, {tgt['y']:.2f})")
    a.plot(tgt["eph_x"], tgt["eph_y"], "x", color=C_EPH, ms=15, mew=3,
           label=f"历表位置反算 ({tgt['eph_x']:.2f}, {tgt['eph_y']:.2f})")
    a.add_patch(Circle((tgt["eph_x"], tgt["eph_y"]), 3, fill=False, ec=C_EPH, lw=1.5, ls=":"))
    ps = sol["pixel_scale_arcsec"]
    xb = xi + half - 2 - 1 / ps
    a.plot([xb, xb + 1 / ps], [yi - half + 2] * 2, color="white", lw=4)
    a.text(xb + 0.5 / ps, yi - half + 2.6, "1″", color="white", ha="center",
           fontsize=13, fontweight="bold")
    a.legend(loc="upper left", fontsize=12, framealpha=0.85)
    a.set_title(f"S9 局部（29×29 px，灰度 {VMIN:.0f}–{VMAX + 40:.0f} ADU）", loc="left")
    a.set_xlabel(XLAB)
    a.set_ylabel(YLAB)
    a.text(0.02, 0.1, "黄色虚线圈：历表预报 3 px 抓取半径", transform=a.transAxes,
           color=C_EPH, fontsize=12, bbox=dict(fc="black", alpha=0.55, ec="none"))
    fig.text(0.05, 0.02,
             "红圈 = 归档 .ref.reg（半径 15 px），绿圈 = 归档 .reg（半径 10 px），均按 DS9 physical 坐标渲染。"
             "N/E 方向与历表反算像素由重建的底片常数给出（nspa-frame-solution.json）。",
             fontsize=11.5, color="#333")
    save(fig, "nspa-match-overlay.png")

    # 天区分布
    gaia = np.array([[g["ra"], g["de"], g["g"]] for g in sol["gaia_field"]])
    refs = sol["references"]
    corners = np.array([plate.sky(x, y) for x, y in
                        ((0.5, 0.5), (2048.5, 0.5), (2048.5, 2048.5), (0.5, 2048.5))])
    inside = np.array([0.5 <= px <= 2048.5 and 0.5 <= py <= 2048.5
                       for px, py in (plate.pix(r, d) for r, d, _ in gaia)])
    ref_ra = np.array([r["ra_gaia"] for r in refs])
    ref_de = np.array([r["de_gaia"] for r in refs])
    is_ref = np.array([np.min(np.hypot(ref_ra - r, ref_de - d)) < 1e-7 for r, d, _ in gaia])
    det_sky = np.array([plate.sky(x, y) for x, y in det[:, :2]])
    det_is_ref = np.array([np.min(np.hypot(ref[:, 0] - x, ref[:, 1] - y)) < 1e-3
                           for x, y in det[:, :2]])
    det_is_tgt = np.hypot(det[:, 0] - tgt["x"], det[:, 1] - tgt["y"]) < 1e-3

    fig = plt.figure(figsize=(16, 10.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.3, 1], left=0.07, right=0.985,
                          top=0.94, bottom=0.2, wspace=0.22, hspace=0.42)
    ax = fig.add_subplot(gs[:, 0])
    ax.add_patch(Polygon(corners, closed=True, fill=True, fc="#eef4fb", ec="#7a8a99", lw=1.5,
                         label="本帧视场（四角由底片常数换算）"))
    sz = lambda g: 8 + (18.5 - g) * 10  # noqa: E731
    m = inside & ~is_ref
    ax.scatter(gaia[m, 0], gaia[m, 1], s=sz(gaia[m, 2]) + 60, facecolors="none",
               edgecolors="#57606a", lw=1.8, ls="--",
               label=f"视场内 GAIA 星、未参与匹配（{m.sum()}，G {gaia[m, 2].min():.1f}–{gaia[m, 2].max():.1f}）")
    ax.scatter(gaia[~inside, 0], gaia[~inside, 1], s=sz(gaia[~inside, 2]), color="#c9d1d9",
               label=f"视场外 GAIA 星（截取框 ±15′ 内，{(~inside).sum()}）")
    ax.scatter(ref_ra, ref_de, s=sz(np.array([r["g"] for r in refs])) + 40, facecolors="none",
               edgecolors=C_REF, lw=2.2, label=f"参考星 R1–R{len(refs)}（GAIA，历元改正后）")
    for k, (r, d) in enumerate(zip(ref_ra, ref_de), 1):
        ax.text(r - 0.0035, d + 0.0022, f"R{k}", color=C_REF, fontsize=11, fontweight="bold")
    other = ~det_is_ref & ~det_is_tgt
    ax.scatter(det_sky[other, 0], det_sky[other, 1], marker="x", color="#139c3a", s=45, lw=1.8,
               label=f"检测到但无 GAIA 对应（{other.sum()}）")
    ax.plot(tgt["eph_ra"], tgt["eph_de"], "+", color="#d4a000", ms=22, mew=3, label="S9 历表位置")
    ax.plot(tgt["obs_ra"], tgt["obs_de"], "o", mfc="none", mec="#0090c0", ms=12, mew=2.2,
            label="S9 实测位置")
    pad = 0.012
    ax.set_xlim(corners[:, 0].max() + pad, corners[:, 0].min() - pad)   # 东在左
    ax.set_ylim(corners[:, 1].min() - pad, corners[:, 1].max() + pad)
    ax.set_aspect(1 / np.cos(np.deg2rad(tgt["eph_de"])))
    ax.set_xlabel("RA（度，ICRS）")
    ax.set_ylabel("Dec（度，ICRS）")
    ax.set_title("参考星在天区中的分布（历元 2024.83）", loc="left")
    ax.legend(loc="upper left", bbox_to_anchor=(-0.02, -0.08), fontsize=11.5, ncol=2, frameon=False)
    ax.grid(alpha=0.25)
    ax.ticklabel_format(useOffset=False)

    a = fig.add_subplot(gs[0, 1])
    dra = np.array([r["dra_cosd"] for r in refs])
    dde = np.array([r["dde"] for r in refs])
    used = np.array([r["used_in_fit"] for r in refs])
    a.scatter(dra[used], dde[used], color=C_REF, s=50, label=f"参与拟合（{used.sum()}）")
    a.scatter(dra[~used], dde[~used], facecolors="none", edgecolors=C_REF, s=60, lw=1.8,
              label=f"2.6σ 剔除（{(~used).sum()}）")
    sig = sol["plate_sigma_arcsec"]
    for k, (u, v) in enumerate(zip(dra, dde), 1):
        if np.hypot(u, v) > sig:      # 只标 σ 圆外的星，避免圆内重叠
            a.text(u + 0.01, v + 0.01, f"R{k}", fontsize=10.5, color="#8a1f18")
    a.add_patch(Circle((0, 0), sig, fill=False, ec="#555", ls="--", lw=1.2))
    a.text(sig * 0.72, -sig * 0.9, f"σ = {sig:.3f}″", fontsize=11, color="#555")
    a.axhline(0, color="#aaa", lw=0.8)
    a.axvline(0, color="#aaa", lw=0.8)
    a.set_xlim(-0.42, 0.42)
    a.set_ylim(-0.25, 0.25)
    a.set_aspect("equal")
    a.set_xlabel("Δα·cosδ（″）")
    a.set_ylabel("Δδ（″）")
    a.set_title(f"参考星底片拟合残差（{sol['model_type']} 参数模型）", loc="left", fontsize=14)
    a.legend(fontsize=10.5, loc="upper left")
    a.grid(alpha=0.25)

    a = fig.add_subplot(gs[1, 1])
    oc_ra, oc_de = tgt["oc_ra_cosd_arcsec"], tgt["oc_de_arcsec"]
    a.add_patch(Rectangle((-ps / 2, -ps / 2), ps, ps, fill=False, ec="#999", ls=":"))
    a.text(ps / 2 - 0.004, ps / 2 + 0.006, f"虚线框：1 像素 = {ps:.3f}″", fontsize=10.5, color="#777")
    a.plot(0, 0, "+", color="#d4a000", ms=22, mew=3, label="历表位置 C")
    a.plot(oc_ra, oc_de, "o", mfc="none", mec="#0090c0", ms=13, mew=2.4, label="实测位置 O")
    a.annotate("", xy=(oc_ra, oc_de), xytext=(0, 0),
               arrowprops=dict(arrowstyle="-|>", color="#0090c0", lw=1.8))
    a.text(oc_ra + 0.012, oc_de + 0.006,
           f"O−C = ({oc_ra:+.4f}″, {oc_de:+.4f}″)", fontsize=12, color="#006c90")
    a.set_xlim(0.2, -0.2)
    a.set_ylim(-0.14, 0.14)
    a.set_aspect("equal")
    a.set_xlabel("Δα·cosδ（″，东为正，向左）")
    a.set_ylabel("Δδ（″）")
    a.set_title("本帧 S9：实测 − 历表", loc="left", fontsize=14)
    a.legend(fontsize=10.5, loc="lower right", framealpha=1)
    a.grid(alpha=0.25)
    save(fig, "nspa-match-sky.png")
    return dict(gaia_in_frame=int(inside.sum()), gaia_in_frame_not_ref=int(m.sum()),
                detections_without_gaia=int(other.sum()))


# ── 图 6：O-C ─────────────────────────────────────────────────────────────

def load_unique(path):
    lines = [ln for ln in Path(path).read_text().splitlines() if ln.strip()]
    uniq = list(dict.fromkeys(ln.rstrip() for ln in lines))
    a = np.array([[float(v) for v in ln.split()[:16]] for ln in uniq])
    return a, len(lines)


def fig_oc():
    a, n_rows = load_unique(REPO / "outputs/results/S9/2024/fits1.dat")
    t = (a[:, 2] - 3.0) * 24.0   # 2024-11-03 当日 UTC 小时
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.4), sharex=True)
    fig.subplots_adjust(left=0.065, right=0.985, top=0.86, bottom=0.16, wspace=0.2)
    for ax, col, lab, color in ((axes[0], 13, "Δα·cosδ（″）", "#2a78d6"),
                                (axes[1], 14, "Δδ（″）", "#eb6834")):
        y = a[:, col]
        ax.axhline(0, color="#999", lw=0.9)
        ax.axhspan(y.mean() - y.std(ddof=1), y.mean() + y.std(ddof=1), color=color, alpha=0.1)
        ax.axhline(y.mean(), color=color, lw=1.2, ls="--")
        ax.plot(t, y, "o", color=color, ms=8)
        ax.plot(t[0], y[0], "o", mfc="none", mec="black", ms=16, mew=2)
        ax.annotate("本页示例帧 001", xy=(t[0], y[0]), xytext=(t[0] + 0.05, y[0] + 0.07),
                    fontsize=12, arrowprops=dict(arrowstyle="->", lw=1.2))
        ax.set_ylim(-0.12, 0.2)
        ax.set_ylabel(lab)
        ax.set_xlabel("2024-11-03 UTC（小时）")
        ax.grid(alpha=0.3)
        ax.set_title(f"{lab[:-3]}　均值 {y.mean():+.3f}″　σ {y.std(ddof=1):.3f}″　N = {len(y)}",
                     loc="left", fontsize=14)
    fig.suptitle("S9（Phoebe）2024-11-03：comoc 保留的单帧 O-C", x=0.065, ha="left",
                 fontsize=16, fontweight="bold")
    fig.text(0.985, 0.955, "虚线：均值　色带：±1σ　数据：outputs/results/S9/2024/fits1.dat（去重后）",
             ha="right", fontsize=12, color="#555")
    save(fig, "nspa-oc-s9-2024.png")
    out = dict(S9_2024=dict(rows_in_file=n_rows, unique_frames=len(a),
                            mean_ra=round(a[:, 13].mean(), 4), std_ra=round(a[:, 13].std(ddof=1), 4),
                            mean_de=round(a[:, 14].mean(), 4), std_de=round(a[:, 14].std(ddof=1), 4)))
    for i in range(1, 6):
        b, n = load_unique(REPO / f"outputs/results/U/2020/fits{i}.dat")
        out[f"U{i}_2020"] = dict(rows_in_file=n, unique=len(b),
                                 nights=len(set(np.floor(b[:, 2]).astype(int))),
                                 std_ra=round(b[:, 13].std(ddof=1), 4),
                                 std_de=round(b[:, 14].std(ddof=1), 4))
    return out


# ── 主程序 ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", required=True, type=Path)
    args = ap.parse_args()
    day = args.materials.resolve() / DAY

    raw_path = day / "fits" / f"{FRAME}.fit"
    pre_path = day / "fits_n" / f"{FRAME}_n.fit"
    raw = fits.getdata(raw_path).astype(np.float64)
    pre = fits.getdata(pre_path).astype(np.float64)
    assert raw.shape == pre.shape == (2048, 2048)
    det = read_reg(day / "fits_reg" / f"{FRAME}.fit.reg")
    ref = read_reg(day / "fits_ref" / f"{FRAME}.fit1.ref.reg")
    sol = json.loads((ASSETS / "nspa-frame-solution.json").read_text())
    plate = Plate(sol)

    # 像素 ↔ region 对齐检查：每个 .reg 圈心与预处理图局部光心之差
    offs = []
    for x, y in det[:, :2]:
        i, j = int(round(x)) - 1, int(round(y)) - 1
        s = pre[j - 5:j + 6, i - 5:i + 6] - sol_bkgd(det)
        s[s < 0] = 0
        yy, xx = np.mgrid[-5:6, -5:6]
        offs.append(((xx * s).sum() / s.sum() + i + 1 - x, (yy * s).sum() / s.sum() + j + 1 - y))
    offs = np.array(offs)

    stats = {}
    for k, img in (("raw", raw), ("pre", pre)):
        mean, med, std = sigma_clipped_stats(img, sigma=3.0, maxiters=10)
        stats[k] = dict(median=float(med), std=float(std))

    hot = (1549.0, 190.0)     # 预处理图 5σ 连通域仅 9 px（3×3 平滑后的单像素）
    edge = (2.7, 1627.1)      # 预处理图 5σ 连通域贴左边缘（x < 10）
    fig_pre(raw, pre, stats)
    fig_detect(raw, pre, det, hot, edge)
    counts = fig_match(raw, det, ref, sol, plate)
    oc = fig_oc()

    prov = dict(
        sample=dict(target="S9 (Phoebe)", frame=FRAME, night="2024-11-03",
                    exposure_mid_utc=sol["exposure_mid_utc"], exptime_s=45.0,
                    note="全部为用户归档产物；本页未重跑 pre/detect；fits_n 为归档 float32 文件，"
                         "当前 HEAD 的中值分支写出 uint16，故不声称由当前 HEAD 生成。"),
        files=dict(raw=str(DAY / "fits" / f"{FRAME}.fit"), preprocessed=str(DAY / "fits_n" / f"{FRAME}_n.fit"),
                   detection_reg=str(DAY / "fits_reg" / f"{FRAME}.fit.reg"),
                   reference_reg=str(DAY / "fits_ref" / f"{FRAME}.fit1.ref.reg"),
                   object_out=str(DAY / "fits_out" / "object_1.out"),
                   config="inputs/configs/nspa2024.cfg (与归档运行是否完全一致未经证实)",
                   gaia="inputs/catalogs/S9/2024/GAIA3_S9_202410.DAT",
                   ephemeris="inputs/catalogs/S9/2024/EPH_S9_202411.DAT"),
        image=dict(shape=[2048, 2048], raw_dtype="uint16 (BITPIX=16, BZERO=32768)",
                   preprocessed_dtype="float32 (BITPIX=-32)", ltv="LTV1/LTV2 absent (0)",
                   coords="DS9 physical, 1-based; data[j,i] -> (x,y)=(i+1,j+1)",
                   display_stretch_adu=[VMIN, VMAX],
                   display_note="全帧与预处理局部对照：原始/预处理同一线性灰度 670–715 ADU；"
                                "检测局部放大 12 格共用 675–760 ADU；match 图中 S9 局部 670–755 ADU。均未对单图独立拉伸",
                   background_sigma_clipped=stats),
        counts=dict(detections=int(len(det)), references=int(len(ref)),
                    references_used_in_fit=sol["n_reference_used_in_fit"],
                    gaia_in_extraction_box=sol["n_gaia_in_field"], **counts),
        alignment=dict(reg_vs_local_centroid_median_abs_px=[round(float(np.median(np.abs(offs[:, 0]))), 3),
                                                            round(float(np.median(np.abs(offs[:, 1]))), 3)],
                       ref_xy_equal_to_detection_xy=bool(all(
                           np.min(np.hypot(det[:, 0] - x, det[:, 1] - y)) < 1e-3 for x, y in ref[:, :2]))),
        solution=dict(file="docs/assets/nspa-frame-solution.json",
                      method="reconstruct_frame.py 调用 nspa.domain.matching.find_obj_base_angle，"
                             "输入为归档 .reg + cfg + GAIA + 历表；与归档 object_1.out 比对",
                      plate_sigma_arcsec=sol["plate_sigma_arcsec"],
                      target_oc_arcsec=[sol["target"]["oc_ra_cosd_arcsec"], sol["target"]["oc_de_arcsec"]],
                      diff_vs_archive_arcsec=[sol["check_vs_archive"]["d_obs_ra_arcsec"],
                                              sol["check_vs_archive"]["d_obs_de_arcsec"]],
                      ref_reg_dec_precision="ref.reg Dec 仅 3 位小数；天区图使用 RA(8 位)+粗 Dec 在历元改正后的 GAIA 中唯一对应得到的完整坐标（15/15 唯一）"),
        oc=oc,
    )
    (ASSETS / "provenance.json").write_text(json.dumps(prov, indent=1, ensure_ascii=False))
    print("alignment offsets median |dx|,|dy| px:", prov["alignment"]["reg_vs_local_centroid_median_abs_px"])
    print(json.dumps(counts), json.dumps(stats))


def sol_bkgd(det):
    """detect 写入 .reg 的背景值（每行相同）。"""
    return float(det[0, 8])


if __name__ == "__main__":
    main()
