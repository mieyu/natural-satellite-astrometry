"""参数表单：把 nspa.config._SCALAR_FIELDS 按 section 分组渲染为可编辑表单。

字段定义、默认值、类型全部来自 nspa.config，UI 不重复维护字段表。
路径/列表类输入（fitspath、历表、星表）由 inputs_panel 负责，不在此面板。
"""

from pathlib import Path

from nspa.config import _SCALAR_FIELDS, parse_config

_GENERATED_CFG_NAMES = {"_ui_run.cfg"}
_INPUT_OWNED_SCALAR_KEYS = {
    "run_manifest_dir",
    "3obj_total",
    "4specified-output",
}

_SECTION_TITLES = {
    "pre": "① 图像预处理",
    "detect": "② 星点检测与定位",
    "match": "③ 星表匹配与坐标计算",
    "comoc": "④ 位置偏差统计（O−C）",
}
_SECTION_ORDER = ["pre", "detect", "match", "comoc"]
_SECTION_DESCRIPTIONS = {
    "pre": "处理图像背景，使星点更容易识别。",
    "detect": "寻找星点，测量它们在图像中的位置。",
    "match": "利用参考星，把图像位置换算为天球坐标。",
    "comoc": "比较测量位置与历表位置，检查测量偏差。",
}

# 显示文字与 cfg 原值分离，生成配置时仍使用程序原有的值。
_CHOICES = {
    "1superflag": {"0": "跳过背景处理", "1": "中值滤波", "2": "同态滤波", "3": "双边 Retinex"},
    "1bkgdmode": {"1": "除法归一化", "2": "减去背景"},
    "1enhance_flag": {"0": "关闭", "1": "开启 3×3 平滑"},
    "1median_impl": {"auto": "自动选择", "scipy": "SciPy", "scipy_threaded": "SciPy 多线程", "bottleneck": "Bottleneck"},
    "2connectivity": {"fortran": "兼容旧版", "scipy": "标准八邻域"},
    "3tele_label": {v: v for v in ("ss156", "ss156_2014", "km100", "lj240", "km100B", "km100c")},
    "3modeltype": {"6": "六参数线性", "12": "十二参数", "20": "二十参数", "30": "三十参数"},
    "4del_flag": {"0": "保留中间文件", "1": "清理中间文件"},
}
_SUGGESTIONS = {
    "1pre_workers": {"0": "自动", "1": "单进程", "2": "2 个进程", "4": "4 个进程"},
    "2detect_workers": {"0": "自动", "1": "单进程", "2": "2 个进程", "4": "4 个进程"},
    "2pos_method": {"1": "一阶权重", "2": "二阶权重", "3": "三阶权重"},
}
_LEGACY_KEYS = {"1biasflag", "1darkflag", "1flatflag"}
_LABELS = {
    "1biasflag": "偏置校正（未启用）", "1darkflag": "暗场校正（未启用）",
    "1flatflag": "平场校正（未启用）", "1superflag": "背景处理方法",
    "1med_length": "窗口长度（像素）", "1med_width": "窗口宽度（像素）",
    "1bkgdmode": "背景处理方式", "1enhance_flag": "平滑处理",
    "1median_impl": "中值计算方式", "1pre_workers": "预处理进程数",
    "1homo_gauss_cutoff": "同态截止频率", "1bssr_gauss_size": "高斯窗口（像素）",
    "2bkgd_threshold": "背景阈值（σ 倍数）", "2snr_threshold": "信噪比下限",
    "2pos_method": "中心定位权重", "2connectivity": "星点分组方法",
    "2detect_workers": "检测进程数", "3tele_label": "设备读取规则",
    "3tele_focal": "焦距（毫米）", "3ccd_scale": "像素尺寸（毫米）",
    "3ccd_fieldsize": "参考星半宽（角分）", "3modeltype": "归算模型",
    "3plate_angle": "初始方向角（度）", "3obj_ephsource": "历表来源标识",
    "3gaia_minmag": "参考星亮端（等）", "3gaia_maxmag": "参考星暗端（等）",
    "3match_limit": "匹配距离（角秒）", "3delta_T": "时间改正（秒）",
    "3obj_total": "目标数量（自动）", "4specified-output": "汇总目录（自动）",
    "4eps": "残差上限（角秒）", "4std_limit": "标准差剔除倍数",
    "4mean_limit": "均值偏差限（角秒）", "4del_flag": "统计后文件处理",
}
_HELP = {
    "1superflag": "选择背景处理方法。不同方法使用不同参数，灰色参数在当前模式下不参与处理。",
    "1med_length": "中值滤波窗口的长度，单位为像素。与窗口宽度共同决定背景估计的范围。",
    "1med_width": "中值滤波窗口的宽度。55×1 的设置会依次进行横向和纵向滤波。",
    "1bkgdmode": "减去背景用于扣除估计背景；除法归一化用于调整图像相对背景的亮度。",
    "1enhance_flag": "开启后，在中值背景处理后进行 3×3 均值平滑，减弱细小波动。",
    "1median_impl": "选择中值滤波的计算方式。自动选择会根据滤波窗口安排实现方式。",
    "1homo_gauss_cutoff": "仅在同态滤波时使用，控制频域滤波的截止位置。",
    "1bssr_gauss_size": "仅在双边 Retinex 时使用，高斯窗口尺寸应为正奇数。",
    "2bkgd_threshold": "像素检测门槛为背景值加上此倍数的背景噪声标准差。调高后可能漏掉较暗星点。",
    "2snr_threshold": "只保留信噪比高于此值、且满足其他检测条件的候选星点。",
    "2connectivity": "把相邻的候选像素归为同一个星点。两种方法的分组结果可能不同。",
    "3tele_label": "按实际设备选择 FITS 文件头读取规则；不会自动更改焦距或像素尺寸。",
    "3tele_focal": "望远镜实际焦距，单位为毫米。例如 13.3 米应填 13300。",
    "3ccd_scale": "填写物理像素尺寸。例如 13.5 微米应填 0.0135 毫米。",
    "3ccd_fieldsize": "筛选参考星范围的半宽，单位为角分。18 表示中心两侧各 18 角分。",
    "3modeltype": "用于建立图像位置与天球投影坐标的关系。参数数量越多不代表结果一定更好。",
    "3plate_angle": "0 表示自动寻找方向，其他值为初始方向估计。",
    "3obj_ephsource": "仅为来源标识，不会下载历表或切换文件格式。",
    "3gaia_minmag": "星等越小越亮；亮端数值应小于暗端数值。",
    "3gaia_maxmag": "参考星的暗端界限。例如亮端为 7、暗端为 18.5 时，选择 7～18.5 等参考星。",
    "3match_limit": "星点与参考星匹配时允许的位置差，单位为角秒。",
    "3delta_T": "对 FITS 记录的观测时间增加的改正量，单位为秒。没有已知时间偏差时通常保持 0。",
    "3obj_total": "由输入区选择的目标历表自动确定。",
    "4specified-output": "由输入区选择的数据和输出位置自动确定，保存跨日期汇总结果。",
    "4eps": "标准差剔除模式下，赤经或赤纬方向的残差绝对值达到此上限时，测量点会被剔除。",
    "4std_limit": "大于 0 使用标准差剔除，并同时检查残差上限；0 改用均值偏差限。",
    "4mean_limit": "只在标准差剔除倍数为 0 时生效，限制测量残差与平均残差的差值。",
    "4del_flag": "清理选项会在统计结束后删除指定中间文件。培训时建议保留。",
    "2pos_method": "可选择常用阶数，也可输入其他正整数。",
    "1pre_workers": "0 自动，1 单进程；也可输入其他非负整数。",
    "2detect_workers": "0 自动，1 单进程；也可输入其他非负整数。",
}


def _options(cfg_key):
    return _CHOICES.get(cfg_key, _SUGGESTIONS.get(cfg_key, {}))


def _display_value(cfg_key, value):
    raw = "" if value is None else str(value)
    options = _options(cfg_key)
    if cfg_key == "3tele_label":
        raw = next((key for key in options if key.lower() == raw.lower()), raw)
    return options.get(raw, raw)


def _raw_value(cfg_key, value):
    value = value.strip()
    return next((raw for raw, label in _options(cfg_key).items() if label == value), value)


def fields_by_section():
    """{section: [(cfg_key, attr, type, default), ...]}，按表顺序。"""
    grouped = {s: [] for s in _SECTION_ORDER}
    for cfg_key, section, attr, typ, default in _SCALAR_FIELDS:
        if section in grouped:
            grouped[section].append((cfg_key, attr, typ, default))
    return grouped


def list_config_files(repo_root, input_root=None):
    """列出可作为 UI 模板载入的手工 cfg 文件名。"""
    root = Path(input_root) if input_root is not None else Path(repo_root) / "inputs"
    cfg_dir = root / "configs"
    if not cfg_dir.is_dir():
        return []
    return sorted(
        p.name for p in cfg_dir.glob("*.cfg")
        if p.name not in _GENERATED_CFG_NAMES
    )


def load_cfg_form_values(path):
    """读取 cfg 中可回填到参数表单的值，跳过由输入面板控制的字段。"""
    config = parse_config(str(path))
    values = {}
    for cfg_key, section, attr, _typ, _default in _SCALAR_FIELDS:
        if cfg_key in _INPUT_OWNED_SCALAR_KEYS:
            continue
        try:
            value = getattr(getattr(config, section), attr)
        except AttributeError:
            continue
        values[cfg_key] = "" if value is None else str(value)
    return values


def build_widget(parent):
    import tkinter as tk
    from tkinter import ttk

    def add_help(widget, text):
        popup = None

        def hide(_event=None):
            nonlocal popup
            if popup is not None:
                popup.destroy()
                popup = None

        def show(_event):
            nonlocal popup
            hide()
            popup = tk.Toplevel(widget)
            popup.wm_overrideredirect(True)
            popup.wm_geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height()}")
            ttk.Label(popup, text=text, padding=6, wraplength=340, relief="solid").pack()

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")
        widget.bind("<Destroy>", hide, add="+")

    class ParamsPanel(ttk.Frame):
        def __init__(self, master):
            super().__init__(master)
            self.entries = {}  # cfg_key -> tk.StringVar
            self.types = {}    # cfg_key -> python type
            self.widgets = {}
            self.base_states = {}

            grouped = fields_by_section()
            for col, section in enumerate(_SECTION_ORDER):
                box = ttk.LabelFrame(self, text=_SECTION_TITLES[section])
                box.grid(row=0, column=col, sticky="nw", padx=5, pady=4)
                ttk.Label(box, text=_SECTION_DESCRIPTIONS[section], wraplength=290).grid(
                    row=0, column=0, columnspan=2, sticky="w", padx=3, pady=(4, 8)
                )
                for r, (cfg_key, attr, typ, default) in enumerate(grouped[section], start=1):
                    label = ttk.Label(box, text=_LABELS.get(cfg_key, cfg_key))
                    label.grid(row=r, column=0, sticky="w", padx=3, pady=1)
                    help_text = _HELP.get(cfg_key, _LABELS.get(cfg_key, cfg_key))
                    if cfg_key in _LEGACY_KEYS:
                        help_text += "\n当前版本不执行此项校正；保留模板值，不可在此启用。"
                    help_text += "\n参数名：" + cfg_key
                    add_help(label, help_text)
                    var = tk.StringVar(value=_display_value(cfg_key, default))
                    state = "readonly" if cfg_key in _INPUT_OWNED_SCALAR_KEYS | _LEGACY_KEYS else "normal"
                    if _options(cfg_key):
                        state = "readonly" if cfg_key in _CHOICES else "normal"
                        widget = ttk.Combobox(box, textvariable=var, width=16,
                                              values=list(_options(cfg_key).values()), state=state)
                    else:
                        widget = ttk.Entry(box, textvariable=var, width=18, state=state)
                    widget.grid(
                        row=r, column=1, sticky="w", padx=3, pady=1
                    )
                    add_help(widget, help_text)
                    self.entries[cfg_key] = var
                    self.types[cfg_key] = typ
                    self.widgets[cfg_key] = widget
                    self.base_states[cfg_key] = state
            for key in ("1superflag", "4std_limit"):
                self.entries[key].trace_add("write", self._update_states)
            self._update_states()

        def _update_states(self, *_args):
            values = self.get_scalars()
            mode = values["1superflag"]
            active = {key: mode == "1" for key in (
                "1med_length", "1med_width", "1bkgdmode", "1enhance_flag", "1median_impl")}
            active["1homo_gauss_cutoff"] = mode == "2"
            active["1bssr_gauss_size"] = mode == "3"
            try:
                sigma = float(values["4std_limit"])
            except ValueError:
                sigma = None
            active["4mean_limit"] = sigma is None or sigma == 0
            active["4eps"] = sigma is None or sigma > 0
            for key, enabled in active.items():
                self.widgets[key].configure(state=self.base_states[key] if enabled else "disabled")

        def set_value(self, cfg_key, value):
            if cfg_key in self.entries:
                self.entries[cfg_key].set(_display_value(cfg_key, value))

        def get_scalars(self):
            return {k: _raw_value(k, v.get()) for k, v in self.entries.items()}

        def validate(self):
            """按字段类型校验，返回错误信息列表（空=通过）。"""
            errors = []
            for cfg_key, val in self.get_scalars().items():
                if val == "":
                    continue
                if cfg_key in _CHOICES and val not in _CHOICES[cfg_key]:
                    errors.append(f"{_LABELS[cfg_key]}（{cfg_key}）请选择列表中的有效选项，当前值：{val!r}")
                    continue
                typ = self.types[cfg_key]
                if typ in (int, float):
                    try:
                        typ(val)
                    except ValueError:
                        errors.append(f"{_LABELS.get(cfg_key, cfg_key)}（{cfg_key}）需为 {'整数' if typ is int else '数值'}，当前值：{val!r}")
            return errors

        def load_values(self, values):
            """把纯 dict 值写入表单，便于 UI 与测试复用同一读取逻辑。"""
            for cfg_key, value in values.items():
                self.set_value(cfg_key, value)

        def load_from_cfg(self, path):
            """用现有 cfg 回填非路径参数。"""
            self.load_values(load_cfg_form_values(path))

    return ParamsPanel(parent)
