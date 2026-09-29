"""README 流程图：1 张总体数据流 + 4 张模块流程图（可编辑 SVG）。

    python docs/assets/src/make_flow_diagrams.py

输出 docs/assets/nspa-flow-{overview,pre,detect,match,comoc}.svg。
图中只写科学用户需要的输入 → 关键方法 → 输出，不含函数名与源码路径；
示例参数取自 inputs/configs/nspa2024.cfg。
"""

from pathlib import Path
from xml.sax.saxutils import escape

ASSETS = Path(__file__).resolve().parents[1]

FONT = ("'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',"
        "'Source Han Sans SC','Noto Sans SC',sans-serif")
INK, MUTED, LINE, PAPER, CARD = "#1f2328", "#57606a", "#8c959f", "#ffffff", "#f6f8fa"
ACCENT = {"pre": "#0e8f7e", "detect": "#c26a00", "match": "#2f6fd6", "comoc": "#a63d8c"}
TINT = {"pre": "#e7f4f2", "detect": "#fbf0e3", "match": "#e9f0fb", "comoc": "#f6eaf3"}


def text_width(s, size):
    """粗略估计文本宽度：CJK 字符按 1 em，其余按 0.56 em。"""
    return sum(size if ord(c) > 0x2E80 else 0.56 * size for c in s)


class Svg:
    def __init__(self, w, h, title, desc):
        self.w, self.h = w, h
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-labelledby="t d">',
            f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>',
            "<defs>",
            *(f'<marker id="ah-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
              f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
              for k, c in {**ACCENT, "grey": LINE}.items()),
            "</defs>",
            f'<style>text{{font-family:{FONT};fill:{INK}}}</style>',
            f'<rect width="{w}" height="{h}" fill="{PAPER}"/>',
        ]

    def rect(self, x, y, w, h, fill, stroke="none", sw=1.5, r=14, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=20, color=INK, weight=400, anchor="start", max_w=None):
        if max_w is not None:
            assert text_width(s, size) <= max_w, f"text too wide ({text_width(s, size):.0f}>{max_w}): {s}"
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
                          f'fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

    def arrow(self, x1, y1, x2, y2, key="grey", sw=3, dash=None):
        c = ACCENT.get(key, LINE)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" '
                          f'stroke-width="{sw}"{d} marker-end="url(#ah-{key})"/>')

    def circle(self, cx, cy, r, fill):
        self.parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')

    def save(self, name):
        (ASSETS / name).write_text("\n".join(self.parts + ["</svg>"]) + "\n", encoding="utf-8")
        print("wrote", name)


# ── 总体数据流 ────────────────────────────────────────────────────────────

def overview():
    W, H = 1600, 560
    s = Svg(W, H, "NSPA 总体数据流",
            "原始 FITS 经图像预处理、星象检测、参考星匹配与底片归算、O-C 统计四个模块，"
            "得到目标天球位置与 O-C 残差；report 为辅助出图。")
    s.text(40, 56, "NSPA 总体数据流", 32, weight=700)
    s.text(40, 92, "一个观测夜目录为一个处理单元；四个核心模块依次运行，也可单独运行任一模块。", 20, MUTED)

    y, h = 210, 190
    bw, gap, x0 = 206, 60, 40
    xs = [x0 + i * (bw + gap) for i in range(6)]
    # 输入数据
    s.rect(xs[0], y, bw, h, CARD, LINE, 2)
    s.text(xs[0] + bw / 2, y + 62, "原始 CCD 图像", 24, weight=700, anchor="middle", max_w=bw - 20)
    s.text(xs[0] + bw / 2, y + 100, "FITS，逐帧", 19, MUTED, anchor="middle")
    s.text(xs[0] + bw / 2, y + 130, "一个观测夜一个目录", 17, MUTED, anchor="middle", max_w=bw - 16)

    mods = [
        ("pre", "① 图像预处理", ("扣除天空背景",), "→ 平坦背景图像"),
        ("detect", "② 星象检测", ("阈值分割", "修正矩定心"), "→ 星象表 (x, y, SNR)"),
        ("match", "③ 匹配与归算", ("GAIA 参考星", "底片常数"), "→ 目标 RA/Dec、O−C"),
        ("comoc", "④ O−C 统计", ("剔除野值", "逐晚统计"), "→ O−C 数据与统计"),
    ]
    for i, (k, name, how, out) in enumerate(mods, 1):
        x = xs[i]
        s.rect(x, y, bw, h, TINT[k], ACCENT[k], 2.5)
        s.rect(x, y, bw, 58, ACCENT[k], r=14)
        s.rect(x, y + 40, bw, 18, ACCENT[k], r=0)
        s.text(x + bw / 2, y + 39, name, 23, "#ffffff", 700, "middle", max_w=bw - 16)
        for j, line in enumerate(how):
            s.text(x + bw / 2, y + 96 + j * 26 - (len(how) - 1) * 6, line, 19, INK, 500, "middle",
                   max_w=bw - 14)
        s.text(x + bw / 2, y + 150, out, 17, ACCENT[k], 700, "middle", max_w=bw - 12)
        s.arrow(xs[i - 1] + bw + 6, y + h / 2, x - 6, y + h / 2, k)

    # 结果
    x = xs[5]
    s.rect(x, y, bw, h, CARD, INK, 2)
    s.text(x + bw / 2, y + 62, "天体测量结果", 24, weight=700, anchor="middle", max_w=bw - 20)
    s.text(x + bw / 2, y + 100, "目标位置 + O−C", 19, MUTED, anchor="middle")
    s.text(x + bw / 2, y + 130, "单日与全时段汇总", 17, MUTED, anchor="middle")
    s.arrow(xs[4] + bw + 6, y + h / 2, x - 6, y + h / 2, "comoc")

    # 外部数据进入 ③
    xm = xs[3]
    s.rect(xm - 90, 120, bw + 180, 58, "#ffffff", ACCENT["match"], 1.8, dash="6 5")
    s.text(xm + bw / 2, 157, "GAIA DR3 星表 · 卫星历表 (IMCCE)", 19, ACCENT["match"], 600, "middle",
           max_w=bw + 170)
    s.arrow(xm + bw / 2, 180, xm + bw / 2, y - 6, "match", 2.5)

    # report 辅助
    xr = xs[4]
    s.rect(xr, 450, bw * 2 + gap, 70, "#ffffff", ACCENT["comoc"], 1.8, dash="6 5")
    s.text(xr + 20, 493, "report（辅助）：由汇总数据绘制 O−C 残差图", 19, ACCENT["comoc"], 600,
           max_w=bw * 2 + gap - 30)
    s.arrow(xr + bw / 2, y + h + 4, xr + bw / 2, 446, "comoc", 2.5, dash="6 5")
    s.save("nspa-flow-overview.svg")


# ── 模块流程图 ────────────────────────────────────────────────────────────

def module(key, fname, title, subtitle, inputs, steps, outputs, footer, extra_out=None):
    W = 1600
    step_h, step_gap, top = 88, 18, 112
    mid_h = len(steps) * step_h + (len(steps) - 1) * step_gap
    H = top + mid_h + (150 if extra_out else 96)
    a, t = ACCENT[key], TINT[key]
    s = Svg(W, H, f"NSPA {title}", f"{title}：{subtitle}。输入：{'，'.join(i[0] for i in inputs)}；"
            f"输出：{'，'.join(o[0] for o in outputs)}。")
    s.rect(0, 0, 12, H, a, r=0)
    s.text(44, 62, title, 34, a, 700)
    s.text(44 + text_width(title, 34) + 26, 62, subtitle, 21, MUTED, max_w=1500 - text_width(title, 34))

    # 输入卡片
    cx, cw = 44, 300
    s.rect(cx, top, cw, mid_h, CARD, LINE, 2)
    s.text(cx + 24, top + 44, "输入", 20, MUTED, 700)
    yy = top + 92
    for head, *rest in inputs:
        s.text(cx + 24, yy, head, 23, INK, 700, max_w=cw - 40)
        for r in rest:
            yy += 30
            s.text(cx + 24, yy, r, 17.5, MUTED, max_w=cw - 40)
        yy += 50

    # 方法步骤
    mx, mw = 420, 780
    for i, (head, body) in enumerate(steps):
        y = top + i * (step_h + step_gap)
        s.rect(mx, y, mw, step_h, t, a, 2)
        s.circle(mx + 46, y + step_h / 2, 24, a)
        s.text(mx + 46, y + step_h / 2 + 9, str(i + 1), 26, "#ffffff", 700, "middle")
        s.text(mx + 90, y + 36, head, 23, INK, 700, max_w=mw - 110)
        s.text(mx + 90, y + 69, body, 18.5, INK, max_w=mw - 110)
        if i:
            s.arrow(mx + 46, y - step_gap - 1, mx + 46, y - 2, key, 2.5)
    s.arrow(cx + cw + 8, top + mid_h / 2, mx - 8, top + mid_h / 2, key, 3.5)

    # 输出卡片
    ox, ow = 1280, 276
    s.rect(ox, top, ow, mid_h, "#ffffff", a, 3)
    s.text(ox + 24, top + 44, "输出", 20, a, 700)
    yy = top + 92
    for head, *rest in outputs:
        s.text(ox + 24, yy, head, 23, INK, 700, max_w=ow - 40)
        for r in rest:
            yy += 30
            s.text(ox + 24, yy, r, 17.5, MUTED, max_w=ow - 40)
        yy += 50
    s.arrow(mx + mw + 8, top + mid_h / 2, ox - 8, top + mid_h / 2, key, 3.5)

    fy = top + mid_h + 56
    if extra_out:
        s.rect(ox - 240, fy - 30, ow + 240, 64, "#ffffff", a, 1.8, dash="6 5")
        s.text(ox - 220, fy + 9, extra_out, 19, a, 600, max_w=ow + 200)
        s.arrow(ox + ow / 2, top + mid_h + 4, ox + ow / 2, fy - 34, key, 2.5, dash="6 5")
        fy += 70
    s.text(44, fy, footer, 18, MUTED, max_w=1500 if not extra_out else 1500)
    s.save(fname)


def modules():
    module(
        "pre", "nspa-flow-pre.svg", "① 图像预处理", "压平天空背景与大尺度结构，保留星象",
        inputs=[("原始 CCD 图像", "FITS，逐帧读取", "背景含渐变、光晕、条纹")],
        steps=[
            ("估计背景水平", "迭代 σ 裁剪，得到背景均值与噪声 σ"),
            ("构建“超级背景”", "先沿行、再沿列做长窗口中值滤波，星象被滤掉，只剩背景"),
            ("扣除背景", "原图减去超级背景，再加回背景均值，整体灰度水平不变"),
            ("轻度平滑（可选）", "3×3 均值平滑，降低逐像素噪声"),
        ],
        outputs=[("平坦背景图像", "FITS，与原图同尺寸", "像素坐标不变")],
        footer="本页示例：中值窗口 65 px、行→列串联、减法扣背景、开启 3×3 平滑。"
               "另可选同态滤波、双边 Retinex 两种背景处理方式。",
    )
    module(
        "detect", "nspa-flow-detect.svg", "② 星象检测与定心", "在平坦图像上找出星象并测定中心",
        inputs=[("预处理图像", "背景已压平", "（也可直接用原图）")],
        steps=[
            ("阈值分割", "保留高于 “背景 + k·σ” 的像素（示例 k = 5）"),
            ("连通区域", "8 邻域相连的像素归为同一个星象"),
            ("修正矩定心", "强度加权质心 (x, y)，同时给出流量与信噪比 SNR"),
            ("筛选", "像素数 10 – 5026；去掉贴边（10 px 边框）与饱和星象；SNR 门限"),
        ],
        outputs=[("星象表", "每颗星 x, y, 流量, SNR", "DS9 region，可直接叠加")],
        footer="坐标为 DS9 physical 像素（1-based）；星象表按流量从亮到暗排列。",
    )
    module(
        "match", "nspa-flow-match.svg", "③ 参考星匹配与底片归算", "用 GAIA 恒星建立像素→天球的对应，定位卫星",
        inputs=[("星象表", "来自 ②"), ("GAIA DR3 星表", "位置、自行、G 星等"),
                ("卫星历表", "IMCCE，按曝光中点插值")],
        steps=[
            ("预报与取星", "历表插值得到目标预报位置；截取视场内 GAIA 星并按自行改到观测历元"),
            ("自动匹配", "依次假设每颗检测星是目标，按标称比例尺与旋转角与 GAIA 配对，取最多者"),
            ("底片常数", "6 / 12 / 20 项多项式最小二乘，2.6σ 迭代剔除；再用新常数全图重匹配"),
            ("定位目标", "历表位置反算到像素，3 px 内最近的星即目标，换算为 RA / Dec"),
        ],
        outputs=[("目标 RA / Dec", "及 O−C = 实测 − 历表"), ("参考星表", "DS9 region，红圈"),
                 ("底片拟合 σ", "逐帧写出")],
        footer="同一帧有多个目标时，后续目标复用该帧底片常数。底片常数只在内部使用，不写回 FITS 头（不生成 WCS）。",
    )
    module(
        "comoc", "nspa-flow-comoc.svg", "④ O−C 统计", "剔除野值，给出每晚、每个目标的残差统计",
        inputs=[("逐帧 O−C", "来自 ③，多帧、多目标")],
        steps=[
            ("分组", "按观测日、按目标分别统计"),
            ("迭代剔除野值", "|O−C − 均值| < k·σ（示例 k = 2.6），且 |O−C| < 上限（示例 0.2″）"),
            ("质量门限", "剔除后 Δα·cosδ 与 Δδ 的标准差都 < 0.3″ 的当晚数据才保留"),
            ("汇总", "输出单日与全时段的观测数据、均值与标准差"),
        ],
        outputs=[("O−C 数据", "单日 / 全时段"), ("统计表", "均值、σ、保留点数")],
        footer="report 不参与计算，只读取 ④ 的汇总结果绘图。",
        extra_out="report（辅助）：绘制 O−C 残差图",
    )


if __name__ == "__main__":
    overview()
    modules()
