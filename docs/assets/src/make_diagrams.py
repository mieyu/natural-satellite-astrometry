"""生成 README 用的两张 SVG 示意图（纯标准库，无第三方依赖）。

    python docs/assets/src/make_diagrams.py

输出：
    docs/assets/nspa-pipeline.svg      四个核心模块（pre / detect / match / comoc+report）四面板大图
    docs/assets/nspa-architecture.svg  整体分层架构图

图中文字均对应 nspa/ 下的实际实现；修改流程后请同步更新本脚本中的文字再重新生成。
SVG 自带不透明背景，并通过 prefers-color-scheme 提供深色配色，GitHub 深/浅主题均可读。
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1]

FONT = ("'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',"
        "'Source Han Sans SC','Noto Sans SC',sans-serif")
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

# 模块强调色：(浅色, 深色)
ACCENTS = {
    "pre": ("#0e8f7e", "#2cc3ad"),
    "det": ("#c26a00", "#f0a33a"),
    "mat": ("#2f6fd6", "#6aa5f5"),
    "com": ("#a63d8c", "#e27cc6"),
    "app": ("#57606a", "#9da7b3"),
}


def style_block():
    light = {
        "bg": "#ffffff", "panel": "#f6f8fa", "border": "#d0d7de", "box": "#ffffff",
        "t": "#1f2328", "m": "#59636e", "arrow": "#8c959f", "chip": "#eef1f4",
    }
    dark = {
        "bg": "#0d1117", "panel": "#161b22", "border": "#30363d", "box": "#0d1117",
        "t": "#e6edf3", "m": "#9da7b3", "arrow": "#6e7681", "chip": "#21262d",
    }

    def rules(c, idx):
        r = [
            f".bg{{fill:{c['bg']}}}",
            f".panel{{fill:{c['panel']};stroke:{c['border']}}}",
            f".box{{fill:{c['box']};stroke:{c['border']}}}",
            f".chip{{fill:{c['chip']};stroke:{c['border']}}}",
            f".t{{fill:{c['t']}}}",
            f".m{{fill:{c['m']}}}",
            f".ar{{stroke:{c['arrow']};fill:none}}",
            f".arf{{fill:{c['arrow']}}}",
            f".bgs{{stroke:{c['bg']}}}",
        ]
        for k, v in ACCENTS.items():
            col = v[idx]
            r += [
                f".{k}-f{{fill:{col}}}",
                f".{k}-s{{stroke:{col};fill:none}}",
                f".{k}-t{{fill:{col};fill-opacity:{0.10 if idx == 0 else 0.16}}}",
                f".{k}-x{{fill:{col}}}",
            ]
        return "\n    ".join(r)

    return f"""<style>
    text{{font-family:{FONT}}}
    .mono{{font-family:{MONO}}}
    .b{{font-weight:700}}
    {rules(light, 0)}
    @media (prefers-color-scheme: dark) {{
    {rules(dark, 1)}
    }}
  </style>"""


def T(x, y, s, size=15, cls="t", anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" '
            f'text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def rect(x, y, w, h, cls, r=10, sw=1, extra=""):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
            f'class="{cls}" stroke-width="{sw}"{extra}/>')


def arrow_v(x, y1, y2, cls="ar", head="arf", sw=1.6):
    return (f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - 6}" class="{cls}" stroke-width="{sw}"/>'
            f'<path d="M{x - 5},{y2 - 7} L{x + 5},{y2 - 7} L{x},{y2} Z" class="{head}"/>')


def defs():
    return ""


# ────────────────────────── 四面板流程图 ──────────────────────────

PANELS = [
    dict(
        key="pre", no="1", name="pre", title="图像预处理",
        src="nspa/core/preprocessor.py · utils/image_utils.py",
        inp="fits/*.fit　原始 CCD 观测图像（每个观测日一个目录）",
        steps=[
            ("迭代 σ-clipping 背景估计", "2.6σ 截断迭代收敛，得到背景均值 bkgd 与噪声 σ"),
            ("按 superflag 选择背景处理算法", None),
            ("超级背景中值滤波（superflag=1）", "带状核 L×1 → 1×L 串联去条纹，或二维矩形核；bkgdmode 1 除法 / 2 减法"),
            ("可选 3×3 均值平滑（enhance_flag=1）", "仅作用于中值模式；各模式结果均写为 fits_n/<原名>_n.fit"),
            ("文件级多进程并行", "ProcessPoolExecutor，中值实现 auto：bottleneck / scipy 多线程"),
        ],
        pills=["0 跳过", "1 中值超级背景", "2 同态滤波", "3 双边 Retinex"],
        out="fits_n/*_n.fit　背景扣除后的图像",
        params="1superflag · 1med_length · 1med_width · 1bkgdmode · 1enhance_flag",
    ),
    dict(
        key="det", no="2", name="detect", title="星象检测与定心",
        src="nspa/core/detector.py · utils/image_utils.py",
        inp="fits_n/*_n.fit（superflag=0 时直接读取原图）",
        steps=[
            ("阈值分割", "保留像素 > bkgd + k·σ（k = 2bkgd_threshold），最外一圈清零"),
            ("连通域标号", "fortran 三段式（numba 加速，含子区域合并）或 scipy 8 连通"),
            ("星象筛选", "10 ≤ 像素数 ≤ π·40²，排除 10 px 边缘，标记饱和星象"),
            ("修正矩定心", "以 I^p 加权求形心，p = 2pos_method（1 / 2 / 3 阶）"),
            ("信噪比与排序", "SNR = ΣI / √(ΣI + N·σ²)，按流量降序，SNR 阈值后输出"),
        ],
        out="fits_reg/*.fit.reg　DS9 区域文件（x, y, 流量, SNR）",
        params="2bkgd_threshold · 2snr_threshold · 2pos_method · 2connectivity",
    ),
    dict(
        key="mat", no="3", name="match", title="参考星匹配与底片归算",
        src="nspa/core/matcher.py · domain/matching.py · astrometry.py",
        inp="*.fit.reg　+ GAIA 星表　+ IMCCE 格式历表　+ FITS 头观测时刻",
        steps=[
            ("历表插值与视场取星", "拉格朗日插值得到目标预报位置；截取视场内 GAIA 星并做自行改正"),
            ("盲搜粗匹配", "逐颗检测星假设为目标，KD-tree 与 GAIA 交叉匹配，匹配数最多者胜出"),
            ("底片常数解算", "6 / 12 / 20 项多项式底片模型，迭代最小二乘，2.6σ 剔除参考星"),
            ("全图再匹配与目标定位", "历表位置反演到像素，3 px 内取检测星 → 观测 (α, δ)"),
            ("同图多目标复用（prepar）", "底片常数残差与匹配星数达标时，后续目标直接复用"),
        ],
        out="fits_ref/*.ref.reg　+　fits_out/object_N.out（O、C、σ₀）",
        params="3tele_label · 3modeltype · 3plate_angle · 3match_limit · 3gaia_*mag",
    ),
    dict(
        key="com", no="4", name="comoc + report", title="O-C 统计与报告",
        src="nspa/core/analyzer.py · core/reporter.py",
        inp="fits_out/object_N.out　逐图观测位置与历表位置",
        steps=[
            ("逐日逐目标读取 O-C", "Δα·cosδ 与 Δδ（角秒）"),
            ("迭代野值剔除", "|x − x̄| < k·σ 且 |O-C| < eps，直到样本数不再减少"),
            ("单日质量门限", "剔除后 σ < 0.3″ 且样本数 > 1 才保留该日数据"),
            ("汇总输出", "final_oc / final_object、00oc_N.out、跨日 <目录名>N.dat"),
            ("report：O-C 散点图（第 5 步辅助模块）", "扫描 *N.dat → OC_summary.png + 每目标 OC_U{N}.png"),
        ],
        out="4specified-output/　.dat · .out · OC_*.png",
        params="4eps · 4std_limit · 4mean_limit · 4specified-output · 4del_flag",
    ),
]


def panel(p, x0, y0, w, h):
    k = p["key"]
    o = [f'<g id="panel-{p["name"].split()[0]}">']
    o.append(rect(x0, y0, w, h, "panel", r=16))
    # 标题区
    o.append(f'<path d="M{x0},{y0 + 16} a16,16 0 0 1 16,-16 h{w - 32} a16,16 0 0 1 16,16 '
             f'v52 h{-w} Z" class="{k}-t"/>')
    o.append(f'<rect x="{x0}" y="{y0 + 16}" width="5" height="{h - 32}" class="{k}-f"/>')
    o.append(f'<circle cx="{x0 + 40}" cy="{y0 + 34}" r="17" class="{k}-f"/>')
    o.append(T(x0 + 40, y0 + 40, p["no"], 18, "b", "middle", ' fill="#ffffff"'))
    o.append(T(x0 + 68, y0 + 42, p["name"], 22, f"b mono {k}-x"))
    name_w = 13.5 * len(p["name"]) + 14
    o.append(T(x0 + 68 + name_w, y0 + 42, p["title"], 21, "b t"))
    o.append(T(x0 + w - 22, y0 + 88, p["src"], 12.5, "m mono", "end"))

    # 输入
    cx = x0 + 24
    cw = w - 48
    y = y0 + 102
    o.append(rect(cx, y, cw, 34, "chip", r=8))
    o.append(rect(cx, y, 52, 34, f"{k}-f", r=8))
    o.append(T(cx + 26, y + 22, "输入", 13.5, "b", "middle", ' fill="#ffffff"'))
    o.append(T(cx + 66, y + 22, p["inp"], 14, "t"))
    y += 34

    # 步骤
    bh, gap = 54, 16
    for i, (title, detail) in enumerate(p["steps"]):
        o.append(arrow_v(x0 + w / 2, y, y + gap))
        y += gap
        o.append(rect(cx, y, cw, bh, "box", r=9))
        o.append(f'<circle cx="{cx + 22}" cy="{y + bh / 2}" r="11" class="{k}-t"/>')
        o.append(T(cx + 22, y + bh / 2 + 5, str(i + 1), 13, f"b {k}-x", "middle"))
        if detail is None:  # 分支选择：药丸
            o.append(T(cx + 44, y + 22, title, 15, "b t"))
            px = cx + 44
            for j, pill in enumerate(p["pills"]):
                pw = sum(12.2 if ord(ch) > 0x2E80 else 7.2 for ch in pill) + 22
                on = j == 1
                o.append(rect(px, y + 30, pw, 19, f"{k}-f" if on else f"{k}-t", r=9.5))
                o.append(T(px + pw / 2, y + 44, pill, 12, "b" if on else f"{k}-x",
                           "middle", ' fill="#ffffff"' if on else ""))
                px += pw + 8
        else:
            o.append(T(cx + 44, y + 23, title, 15, "b t"))
            o.append(T(cx + 44, y + 43, detail, 13, "m"))
        y += bh

    # 输出
    o.append(arrow_v(x0 + w / 2, y, y + gap))
    y += gap
    o.append(rect(cx, y, cw, 34, "chip", r=8, sw=1.5, extra=f' style="stroke-dasharray:0"'))
    o.append(rect(cx, y, 52, 34, f"{k}-f", r=8))
    o.append(T(cx + 26, y + 22, "输出", 13.5, "b", "middle", ' fill="#ffffff"'))
    o.append(T(cx + 66, y + 22, p["out"], 14, "b t"))
    y += 34
    o.append(T(cx, y + 30, "关键参数  " + p["params"], 12.5, "m mono"))
    o.append("</g>")
    return "\n  ".join(o)


def big_arrow(x1, y1, x2, y2, label):
    """面板之间的衔接箭头（带数据标签）。"""
    o = []
    o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="ar" stroke-width="3" '
             f'stroke-linecap="round"/>')
    if x2 > x1:
        o.append(f'<path d="M{x2 + 2},{y2} l-12,-8 v16 Z" class="arf"/>')
    elif x2 < x1:
        o.append(f'<path d="M{x2 - 2},{y2} l12,-8 v16 Z" class="arf"/>')
    else:
        o.append(f'<path d="M{x2},{y2 + 2} l-8,-12 h16 Z" class="arf"/>')
    return "\n  ".join(o)


def pipeline_svg():
    W, H = 1600, 1440
    pw, ph = 730, 590
    xl, xr = 40, W - 40 - pw
    yt, yb = 150, 150 + ph + 56
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'role="img" aria-labelledby="ttl desc">',
         '<title id="ttl">NSPA 主处理流程：四个核心模块</title>',
         '<desc id="desc">pre 图像预处理、detect 星象检测与定心、match 参考星匹配与底片归算、'
         'comoc O-C 统计（含 report 绘图输出）四个模块的内部逻辑与数据衔接。</desc>',
         style_block(),
         rect(0, 0, W, H, "bg", r=20)]
    o.append(T(40, 62, "NSPA 主处理流程 · 四个核心模块", 30, "b t"))
    o.append(T(40, 96, "每个观测日目录 YYYYMMDD/fits 依次流经 pre → detect → match → comoc；"
                        "report 作为第 5 步读取汇总结果绘制 O-C 图。", 16, "m"))
    # 顶部流程条
    chips = [("pre", "pre"), ("det", "detect"), ("mat", "match"), ("com", "comoc"), ("com", "report")]
    x = 40
    for i, (k, nm) in enumerate(chips):
        w = 20 + 11 * len(nm)
        dashed = ' style="stroke-dasharray:4 3"' if nm == "report" else ""
        o.append(f'<rect x="{x}" y="112" width="{w}" height="24" rx="12" class="{k}-t {k}-s" '
                 f'stroke-width="1.2"{dashed}/>')
        o.append(T(x + w / 2, 129, nm, 13, f"b mono {k}-x", "middle"))
        x += w
        if i < len(chips) - 1:
            o.append(f'<path d="M{x + 6},124 h14" class="ar" stroke-width="1.6"/>'
                     f'<path d="M{x + 26},124 l-7,-4.5 v9 Z" class="arf"/>')
            x += 32
    o.append(T(x + 14, 129, "python -m nspa.main --step all | pre | detect | match | comoc | report",
               13, "m mono"))

    pos = [(xl, yt), (xr, yt), (xr, yb), (xl, yb)]
    for p, (x0, y0) in zip(PANELS, pos):
        o.append(panel(p, x0, y0, pw, ph))
    # 衔接：1→2 右，2→3 下，3→4 左
    midy = yt + 125
    o.append(big_arrow(xl + pw + 8, midy, xr - 10, midy, ""))
    o.append(big_arrow(xr + pw / 2, yt + ph + 8, xr + pw / 2, yb - 10, ""))
    o.append(big_arrow(xr - 8, yb + 125, xl + pw + 10, yb + 125, ""))

    o.append(T(40, H - 24, "应用层 nspa/application：PipelineRunner 依次执行所选步骤，"
                           "逐步记录耗时、告警与失败项，写入 outputs/runs/<run_id>/manifest.json。",
               13.5, "m"))
    o.append("</svg>")
    return "\n  ".join(o) + "\n"


# ────────────────────────── 架构图 ──────────────────────────

def layer_label(x, y, h, text, sub):
    return (T(x, y + h / 2 - 2, text, 16, "b t") + "\n  " +
            T(x, y + h / 2 + 18, sub, 12.5, "m mono"))


def mod_box(x, y, w, h, title, sub, k=None, dashed=False):
    cls = f"{k}-t" if k else "box"
    o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="{cls}" '
         f'stroke-width="1.2"{" style=" + chr(34) + "stroke-dasharray:5 4" + chr(34) if dashed else ""}/>']
    if k:
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="{k}-s" '
                 f'stroke-width="1.4"{" style=" + chr(34) + "stroke-dasharray:5 4" + chr(34) if dashed else ""}/>')
    o.append(T(x + w / 2, y + h / 2 - 3, title, 15.5, f"b mono {k + '-x' if k else 't'}", "middle"))
    o.append(T(x + w / 2, y + h / 2 + 17, sub, 12.5, "m", "middle"))
    return "\n  ".join(o)


def arch_svg():
    W, H = 1600, 960
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'role="img" aria-labelledby="ttl desc">',
         '<title id="ttl">NSPA 整体架构</title>',
         '<desc id="desc">入口层、配置与应用层、流程编排层、领域算法与工具层、文件 I/O 层，'
         '以及 inputs 与 outputs 数据目录。</desc>',
         style_block(),
         rect(0, 0, W, H, "bg", r=20)]
    o.append(T(40, 62, "NSPA 整体架构", 30, "b t"))
    o.append(T(40, 96, "分层组织：入口只负责参数与调度，算法集中在 domain / utils，文件格式集中在 io。", 16, "m"))

    L = 290  # 左侧数据栏右边界
    R = W - 290  # 右侧数据栏左边界
    cx0, cx1 = L + 40, R - 40
    cw = cx1 - cx0

    # 左侧 inputs
    o.append(rect(40, 130, 230, 790, "panel", r=14))
    o.append(T(60, 166, "inputs/", 20, "b mono t"))
    o.append(T(60, 190, "运行输入（用户自备）", 13.5, "m"))
    items_in = [
        ("images/", "原始 FITS 观测图", "不入库 · YYYYMMDD/fits"),
        ("catalogs/", "GAIA 参考星表", "GAIA3_*.DAT"),
        ("catalogs/", "目标历表（IMCCE 格式）", "EPH_*.DAT"),
        ("configs/", "cfg 参数文件", "nspa2024.cfg 等"),
    ]
    y = 214
    for a, b, c in items_in:
        o.append(rect(56, y, 198, 76, "box", r=9))
        o.append(T(70, y + 25, a, 14, "b mono t"))
        o.append(T(70, y + 46, b, 13.5, "t"))
        o.append(T(70, y + 65, c, 12, "m mono"))
        y += 92

    # 右侧 outputs
    o.append(rect(R + 20, 130, 230, 790, "panel", r=14))
    o.append(T(R + 40, 166, "输出", 20, "b t"))
    o.append(T(R + 40, 190, "观测日目录与 outputs/", 13.5, "m"))
    items_out = [
        ("<观测日>/fits_n/", "预处理图 *_n.fit", "pre"),
        ("<观测日>/fits_reg/", "检测星 *.fit.reg", "detect"),
        ("<观测日>/fits_ref/", "参考星 *.ref.reg", "match"),
        ("<观测日>/fits_out/", "object_N.out / final_*", "match · comoc"),
        ("outputs/results/", ".dat · 00oc · OC_*.png", "comoc · report"),
        ("outputs/runs/", "manifest.json 运行记录", "application"),
    ]
    y = 214
    for a, b, c in items_out:
        o.append(rect(R + 36, y, 198, 72, "box", r=9))
        o.append(T(R + 50, y + 24, a, 13, "b mono t"))
        o.append(T(R + 50, y + 44, b, 13, "t"))
        o.append(T(R + 50, y + 62, c, 12, "m mono"))
        y += 84

    # 中央分层
    def band(y, h, title, sub):
        o.append(rect(cx0, y, cw, h, "panel", r=14))
        o.append(layer_label(cx0 + 20, y, h, title, sub))

    inner0 = cx0 + 200
    iw = cx1 - 20 - inner0

    # 入口层
    band(130, 104, "入口层", "main.py · ui/")
    bw = (iw - 20) / 2
    o.append(mod_box(inner0, 146, bw, 72, "python -m nspa.main", "命令行：--step  --config", "app"))
    o.append(mod_box(inner0 + bw + 20, 146, bw, 72, "python ui/app.py",
                     "Tkinter 界面：生成 _ui_run.cfg → 子进程调用 CLI", "app", dashed=True))
    # 配置与应用层
    band(262, 104, "配置 / 应用层", "config · application")
    bw3 = (iw - 40) / 3
    names = [("config.py", "表驱动解析 + 按步骤校验"),
             ("paths.py", "观测日展开与产物目录"),
             ("application/", "PipelineRunner · manifest")]
    for i, (a, b) in enumerate(names):
        o.append(mod_box(inner0 + i * (bw3 + 20), 278, bw3, 72, a, b, "app"))
    # core 层
    band(394, 124, "流程编排层", "nspa/core/")
    steps = [("pre", "preprocessor", "pre"), ("detect", "detector", "det"),
             ("match", "matcher", "mat"), ("comoc", "analyzer", "com"),
             ("report", "reporter", "com")]
    bw5 = (iw - 4 * 14) / 5
    for i, (a, b, k) in enumerate(steps):
        x = inner0 + i * (bw5 + 14)
        o.append(mod_box(x, 416, bw5, 80, a, b + ".py", k, dashed=(a == "report")))
        if i < 4:
            o.append(f'<path d="M{x + bw5 + 1},456 h8" class="ar" stroke-width="1.6"/>'
                     f'<path d="M{x + bw5 + 13},456 l-5,-4 v8 Z" class="arf"/>')
    # domain / utils
    band(546, 150, "算法层", "domain · utils")
    algos = [
        ("domain/astrometry.py", "坐标变换 · 视场取星与自行改正", "底片常数解算"),
        ("domain/matching.py", "盲搜粗匹配（KD-tree）", "精化 · 再匹配 · prepar"),
        ("utils/image_utils.py", "背景估计 · 中值/同态/Retinex", "连通域 · 修正矩"),
        ("utils/math_utils.py", "拉格朗日插值", "O-C 迭代野值剔除"),
    ]
    bw2 = (iw - 14) / 2
    for i, (a, b, c) in enumerate(algos):
        x = inner0 + (i % 2) * (bw2 + 14)
        y = 560 + (i // 2) * 66
        o.append(rect(x, y, bw2, 58, "box", r=10, sw=1.2))
        o.append(T(x + 14, y + 24, a, 13.5, "b mono t"))
        o.append(T(x + 14, y + 45, b + " · " + c, 12.5, "m"))
    # io
    band(724, 104, "文件 I/O 层", "nspa/io/")
    ios = [("fits_io.py", "FITS 读写 · 多望远镜头时间解析"),
           ("catalog_io.py", "GAIA 星表 · IMCCE 历表"),
           ("text_io.py", ".reg · object_N.out · 统计文件")]
    for i, (a, b) in enumerate(ios):
        o.append(mod_box(inner0 + i * (bw3 + 20), 740, bw3, 72, a, b))
    # 模型
    band(856, 64, "数据模型", "domain/models.py")
    o.append(T(inner0, 894, "DetectedStar · GaiaCatalog · Ephemeris · PlateConstants · MatchResult · "
                            "ObjectObservation · OCStats", 13, "t"))

    # 层间箭头
    xm = inner0 + iw / 2
    for y1, y2 in [(234, 262), (366, 394), (518, 546), (696, 724)]:
        o.append(arrow_v(xm, y1, y2, sw=2))
    # inputs → core，core → outputs
    o.append(f'<path d="M270,456 H{cx0 - 6}" class="ar" stroke-width="2.4"/>'
             f'<path d="M{cx0},456 l-11,-7 v14 Z" class="arf"/>')
    o.append(f'<path d="M{cx1},456 H{R + 14}" class="ar" stroke-width="2.4"/>'
             f'<path d="M{R + 20},456 l-11,-7 v14 Z" class="arf"/>')
    o.append("</svg>")
    return "\n  ".join(o) + "\n"


if __name__ == "__main__":
    (OUT / "nspa-pipeline.svg").write_text(pipeline_svg(), encoding="utf-8")
    (OUT / "nspa-architecture.svg").write_text(arch_svg(), encoding="utf-8")
    print("written:", OUT / "nspa-pipeline.svg", OUT / "nspa-architecture.svg")
