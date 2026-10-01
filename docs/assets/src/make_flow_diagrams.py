"""Generate the five editable, self-contained SVG diagrams used in README.md.

Run from any directory with Python's standard library only::

    python docs/assets/src/make_flow_diagrams.py

The 1040 px canvas is designed for GitHub's README column. Main arrows show
execution order; dashed arrows show external inputs or auxiliary plotting.
Module parameters describe the example in inputs/configs/nspa2024.cfg.
"""

from pathlib import Path
from xml.sax.saxutils import escape

ASSETS = Path(__file__).resolve().parents[1]
FONT = ("'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',"
        "'Hiragino Sans GB','Source Han Sans SC',sans-serif")
INK, MUTED, LINE = "#162638", "#526579", "#dce4ec"
PAPER, SOFT, NAVY = "#ffffff", "#f5f8fb", "#162638"
ACCENT = {"pre": "#0b7b72", "detect": "#a66212",
          "match": "#3269b0", "comoc": "#7955a3"}
TINT = {"pre": "#edf7f5", "detect": "#fdf5e9",
        "match": "#eef4fc", "comoc": "#f5f0fa"}


def text_width(value, size):
    """Conservative width estimate; rendering is checked in a browser too."""
    return sum(size if ord(char) > 0x2E80 else size * 0.60 for char in value)


class Svg:
    def __init__(self, height, title, description):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="{height}" '
            f'viewBox="0 0 1040 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(description)}</desc>',
            '<defs>',
            *(f'<marker id="arrow-{key}" viewBox="0 0 10 10" refX="9" refY="5" '
              f'markerWidth="6" markerHeight="6" orient="auto">'
              f'<path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="{color}" '
              f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></marker>'
              for key, color in {**ACCENT, "main": MUTED}.items()),
            '</defs>',
            # A CSS "text { fill: ... }" rule would override text fill attributes.
            f'<g font-family="{FONT}">',
            f'<rect width="1040" height="{height}" rx="20" fill="{PAPER}"/>',
            f'<rect x="1" y="1" width="1038" height="{height - 2}" rx="20" '
            f'fill="none" stroke="{LINE}"/>',
        ]

    def rect(self, x, y, width, height, fill=PAPER, stroke=LINE, radius=14, dash=None):
        dashed = f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"{dashed}/>')

    def text(self, x, y, value, size=21, color=INK, weight=400, max_width=None,
             anchor="start"):
        if max_width is not None:
            assert text_width(value, size) <= max_width, f'Text too wide: {value}'
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}">{escape(value)}</text>')

    def line(self, x1, y1, x2, y2, color=LINE, dash=None):
        dashed = f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(
            f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" stroke="{color}" '
            f'stroke-width="1.5"{dashed}/>')

    def arrow(self, points, key="main", dashed=False):
        path = 'M ' + ' L '.join(f'{x} {y}' for x, y in points)
        dash = ' stroke-dasharray="5 5"' if dashed else ''
        color = ACCENT.get(key, MUTED)
        self.parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash} '
            f'marker-end="url(#arrow-{key})"/>')

    def icon(self, x, y, key, color=None):
        """Small line illustrations, using only portable SVG primitives."""
        color = color or ACCENT[key]
        shapes = {
            "pre": '<rect x="2" y="2" width="28" height="28" rx="5"/>'
                   '<path d="M 7 22 Q 12 12 17 19 T 27 12 M 7 10 H 15"/>',
            "detect": '<circle cx="16" cy="16" r="10"/>'
                      '<path d="M 16 0 V 8 M 16 24 V 32 M 0 16 H 8 M 24 16 H 32"/>'
                      '<circle cx="16" cy="16" r="2"/>',
            "match": '<path d="M 3 27 V 5 M 3 27 H 28 M 7 22 L 15 15 L 25 6"/>'
                     '<circle cx="7" cy="22" r="2"/><circle cx="15" cy="15" r="2"/>'
                     '<circle cx="25" cy="6" r="2"/>',
            "comoc": '<path d="M 3 4 V 28 H 30 M 4 17 H 29"/>'
                     '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="21" r="2"/>'
                     '<circle cx="26" cy="14" r="2"/>',
        }
        self.parts.append(f'<g transform="translate({x} {y})" fill="none" '
                          f'stroke="{color}" stroke-width="1.8" '
                          f'stroke-linecap="round" stroke-linejoin="round">{shapes[key]}</g>')

    def header(self, title, subtitle, key=None, number=None):
        if key:
            self.rect(32, 30, 56, 56, TINT[key], "none", 16)
            self.icon(44, 42, key)
            self.text(104, 66, title, 32, weight=700, max_width=760)
            self.text(104, 103, subtitle, 21, MUTED, max_width=890)
            self.text(1008, 65, number, 23, ACCENT[key], 600, anchor="end")
        else:
            self.text(32, 60, title, 34, weight=700)
            self.text(32, 98, subtitle, 21, MUTED, max_width=970)
            self.parts.append('<g transform="translate(957 57)" fill="none" '
                              'stroke="#3269b0" stroke-width="1.5">'
                              '<circle r="12"/><ellipse rx="32" ry="14" '
                              'transform="rotate(-32)"/><circle cx="25" cy="-13" '
                              'r="4" fill="#3269b0"/></g>')

    def save(self, name):
        (ASSETS / name).write_text('\n'.join(self.parts + ['</g>', '</svg>']) + '\n',
                                   encoding="utf-8")
        print('wrote', name)


def overview():
    s = Svg(800, 'NSPA 总体数据流',
            '原始 CCD FITS 按顺序经过 pre、detect、match、comoc。'
            'GAIA DR3 星表与 IMCCE 卫星历表进入 match；comoc 汇总数据由 report 辅助绘图。')
    s.header('从 CCD 图像到天体测量结果', '四个核心模块 · 按观测夜组织 · 支持整条运行与单步重跑')

    s.rect(128, 128, 624, 52, SOFT)
    s.text(152, 162, '输入', 18, MUTED, 600)
    s.text(216, 162, '原始 CCD 图像', 23, weight=600)
    s.text(728, 162, 'FITS · 逐帧', 20, MUTED, anchor="end")
    s.arrow([(440, 180), (440, 200)])

    stages = [
        ('pre', '图像预处理', '背景估计与扣除', '平坦背景 FITS'),
        ('detect', '星象检测与定心', '阈值分割 · 修正矩定心', '星象表 / DS9 region'),
        ('match', '参考星匹配与归算', 'GAIA 配对 · 底片常数求解', '目标 RA / Dec 与 O−C'),
        ('comoc', 'O−C 统计', '野值剔除 · 按日、按目标统计', '残差数据与统计表'),
    ]
    for i, (key, title, method, output) in enumerate(stages):
        y = 206 + 104 * i
        color = ACCENT[key]
        s.rect(48, y + 20, 56, 44, TINT[key], "none", 12)
        s.text(76, y + 49, f'{i + 1:02}', 23, color, 600, anchor="middle")
        s.rect(128, y, 624, 84, TINT[key], "none")
        s.icon(152, y + 25, key)
        s.text(204, y + 34, title, 24, weight=700, max_width=390)
        s.text(728, y + 33, key, 19, color, 600, anchor="end")
        s.text(204, y + 64, method, 20, MUTED, max_width=305)
        s.text(728, y + 64, output, 19, color, 500, anchor="end")
        if i < 3:
            s.arrow([(440, y + 84), (440, y + 98)])

    s.rect(790, 376, 218, 120, SOFT, LINE, 14, '5 5')
    s.text(810, 407, '外部参考数据', 18, MUTED, 600)
    s.text(810, 443, 'GAIA DR3 星表', 22, ACCENT['match'], 600)
    s.text(810, 475, 'IMCCE 卫星历表', 21, ACCENT['match'])
    s.arrow([(790, 458), (760, 458)], 'match', True)

    s.arrow([(440, 602), (440, 642)])
    s.rect(128, 650, 624, 88, NAVY, "none")
    s.text(152, 683, '归算产物', 18, '#c6d5e6', 600)
    s.text(152, 717, '目标天球位置 · O−C 数据 · 单日与全时段统计', 22, '#ffffff', 600,
           max_width=576)
    s.rect(790, 650, 218, 88, SOFT, LINE, 14, '5 5')
    s.text(810, 682, 'report · 辅助', 21, ACCENT['comoc'], 600)
    s.text(810, 716, 'O−C 残差图', 22, weight=600)
    s.arrow([(752, 560), (899, 560), (899, 644)], 'comoc', True)
    s.text(804, 597, '读取汇总结果', 18, MUTED)

    s.line(128, 771, 161, 771, MUTED)
    s.text(173, 777, '主处理流程', 18, MUTED)
    s.line(328, 771, 361, 771, MUTED, '5 5')
    s.text(373, 777, '外部输入 / 辅助出图', 18, MUTED)
    s.save('nspa-flow-overview.svg')


def module(key, number, title, subtitle, inputs, steps, outputs, notes,
           report=False):
    """Left-to-right method cards with input above and output below.

    Multiple inputs join a bus before the first method, rather than implying
    that all inputs feed an arbitrary midpoint of the algorithm.
    """
    s = Svg(758 if report else 720, f'NSPA {title}',
            f'{title}。输入：' + '；'.join(item[0] for item in inputs) +
            '。处理顺序：' + ' → '.join(item[0] for item in steps) +
            '。输出：' + '；'.join(item[0] for item in outputs) + '。' + ' '.join(notes))
    s.header(title, subtitle, key, number)
    color = ACCENT[key]

    s.rect(32, 140, 976, 96, SOFT)
    s.text(52, 170, '输入', 18, MUTED, 600)
    column_width = 856 / len(inputs)
    centers = []
    for i, (head, detail) in enumerate(inputs):
        x = 132 + i * column_width
        s.text(x, 178, head, 23, weight=600, max_width=column_width - 28)
        s.text(x, 211, detail, 20, MUTED, max_width=column_width - 28)
        if i:
            s.line(x - 20, 161, x - 20, 218)
        centers.append(x + (column_width - 28) / 2)

    if len(inputs) == 1:
        s.arrow([(145, 236), (145, 270)], key)
    else:
        for cx in centers:
            s.line(cx, 236, cx, 254, color)
        s.line(145, 254, centers[-1], 254, color)
        s.arrow([(145, 254), (145, 270)], key)

    for i, (head, lines) in enumerate(steps):
        x = 32 + i * 250
        s.rect(x, 278, 226, 226)
        s.rect(x + 20, 298, 46, 30, TINT[key], "none", 8)
        s.text(x + 43, 320, f'{i + 1:02}', 18, color, 600, anchor="middle")
        s.text(x + 20, 365, head, 23, weight=700, max_width=186)
        s.line(x + 20, 384, x + 206, 384)
        for j, value in enumerate(lines):
            s.text(x + 20, 418 + 29 * j, value, 21, MUTED, max_width=186)
        if i < 3:
            s.arrow([(x + 229, 391), (x + 245, 391)], key)

    s.arrow([(895, 504), (895, 538)], key)
    s.rect(32, 546, 976, 90, NAVY, "none")
    s.text(52, 578, '输出', 18, '#c6d5e6', 600)
    column_width = 856 / len(outputs)
    for i, (head, detail) in enumerate(outputs):
        x = 132 + i * column_width
        if i:
            s.line(x - 20, 564, x - 20, 618, '#435365')
        s.text(x, 579, head, 23, '#ffffff', 600, max_width=column_width - 28)
        s.text(x, 611, detail, 20, '#c6d5e6', max_width=column_width - 28)

    note_y = 672
    if report:
        s.arrow([(895, 636), (895, 657)], key, True)
        s.rect(532, 663, 476, 48, TINT[key], "none", 12, '5 5')
        s.text(552, 694, 'report · 读取汇总结果，绘制 O−C 残差图', 21, color, 600,
               max_width=436)
        note_y = 739
    for i, note in enumerate(notes):
        s.text(32, note_y + 29 * i, note, 20, MUTED, max_width=976)
    s.save(f'nspa-flow-{key}.svg')


def modules():
    module('pre', '01', '图像预处理', '压平天空背景与大尺度结构，为星象检测准备图像',
           inputs=[('原始 CCD 图像', '逐帧读取 FITS · 背景可能包含渐变、光晕与条纹')],
           steps=[
               ('估计背景', ['迭代 σ 裁剪', '估计背景均值', '与噪声 σ']),
               ('沿行处理', ['65 px 中值窗口', '估计并扣除背景', '加回背景均值']),
               ('沿列处理', ['交换窗口方向', '再次扣除背景', '压低残留结构']),
               ('轻度平滑', ['可选 3×3 均值', '降低像素噪声', '保持像素网格']),
           ],
           outputs=[('平坦背景 FITS', '与原图同尺寸 · 像素坐标保持不变')],
           notes=['示例采用行、列串联中值与减法扣背景；每次扣背景均加回原始背景均值。',
                  '以上为中值背景分支；也支持同态滤波、双边 Retinex。参数来自 nspa2024.cfg。'])

    module('detect', '02', '星象检测与定心', '从图像中的连通亮区得到星象中心、流量与信噪比',
           inputs=[('预处理图像', '读取平坦背景 FITS · 跳过预处理时也可读取原图')],
           steps=[
               ('阈值分割', ['背景 + k·σ', '保留阈值以上', '像素；示例 k = 5']),
               ('连通区域', ['按 8 邻域连通', '将相连亮像素', '归为同一星象']),
               ('修正矩定心', ['测定中心 (x, y)', '计算星象流量', '与信噪比 SNR']),
               ('筛选星象', ['像素数与边缘', '饱和与 SNR', '逐项筛选']),
           ],
           outputs=[('星象表 · DS9 region', '中心 (x, y)、流量与 SNR · 按流量从亮到暗排列')],
           notes=['筛选条件：像素数 10–5026，排除 10 px 边框内与饱和星象，并应用 SNR 门限。',
                  '坐标采用 DS9 physical（1-based），可直接叠加到相同像素网格的图像上。'])

    module('match', '03', '参考星匹配与底片归算', '用 GAIA 恒星建立像素与天球坐标的对应，定位天然卫星',
           inputs=[('检测星象表', '(x, y)、流量、SNR'),
                   ('GAIA DR3 星表', '位置、自行、G 星等'),
                   ('IMCCE 卫星历表', '曝光中点位置插值')],
           steps=[
               ('预报与取星', ['插值历表位置', '截取视场恒星', '自行改正到历元']),
               ('自动配对', ['逐颗假设目标', '按尺度与旋转', '取最多匹配者']),
               ('底片常数', ['最小二乘求解', '2.6σ 迭代剔除', '全图重配再拟合']),
               ('定位与归算', ['历表反算像素', '≤ 3 px 最近源', '换算 RA / Dec']),
           ],
           outputs=[('目标 RA / Dec', 'O−C = 实测 − 历表'),
                    ('参考星表', 'DS9 region · 红圈'),
                    ('底片拟合 σ', '逐帧输出')],
           notes=['底片模型可选 6 / 12 / 20 项；同一帧的后续目标复用已求得的底片常数。',
                  '底片常数只在内部使用，不写回 FITS 头，不生成 WCS。'])

    module('comoc', '04', 'O−C 统计', '剔除野值，汇总每个观测夜与每个目标的残差',
           inputs=[('逐帧 O−C', '来自 match 的归算结果 · 多帧、多目标')],
           steps=[
               ('按日分组', ['按观测日期', '与目标分别', '整理残差序列']),
               ('迭代剔除', ['偏离均值 < k·σ', '且 |O−C| < 上限', '迭代至收敛']),
               ('质量门限', ['两个方向的 σ', '均须 < 0.3″', '且保留 ≥ 2 帧']),
               ('汇总输出', ['保留合格夜数据', '统计均值与 σ', '合并跨日结果']),
           ],
           outputs=[('O−C 数据', '单日 / 全时段'), ('统计表', '均值、σ、保留点数')],
           notes=['示例 k = 2.6、绝对值上限 0.2″；report 只读取汇总数据绘图，不参与归算。'],
           report=True)


if __name__ == '__main__':
    overview()
    modules()
