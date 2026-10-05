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
    "pre": "01 预处理 (pre)",
    "detect": "02 检测 (detect)",
    "match": "03 匹配归算 (match)",
    "comoc": "04 O-C 统计 (comoc)",
}
_SECTION_ORDER = ["pre", "detect", "match", "comoc"]


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

    class ParamsPanel(ttk.Frame):
        def __init__(self, master):
            super().__init__(master)
            self.entries = {}  # cfg_key -> tk.StringVar
            self.types = {}    # cfg_key -> python type

            grouped = fields_by_section()
            for col, section in enumerate(_SECTION_ORDER):
                box = ttk.LabelFrame(self, text=_SECTION_TITLES[section])
                box.grid(row=0, column=col, sticky="nw", padx=5, pady=4)
                for r, (cfg_key, attr, typ, default) in enumerate(grouped[section]):
                    ttk.Label(box, text=cfg_key).grid(row=r, column=0, sticky="w", padx=3, pady=1)
                    var = tk.StringVar(value="" if default is None else str(default))
                    state = "readonly" if cfg_key in _INPUT_OWNED_SCALAR_KEYS else "normal"
                    ttk.Entry(box, textvariable=var, width=14, state=state).grid(
                        row=r, column=1, sticky="w", padx=3, pady=1
                    )
                    self.entries[cfg_key] = var
                    self.types[cfg_key] = typ

        def set_value(self, cfg_key, value):
            if cfg_key in self.entries:
                self.entries[cfg_key].set("" if value is None else str(value))

        def get_scalars(self):
            return {k: v.get() for k, v in self.entries.items()}

        def validate(self):
            """按字段类型校验，返回错误信息列表（空=通过）。"""
            errors = []
            for cfg_key, var in self.entries.items():
                val = var.get().strip()
                if val == "":
                    continue
                typ = self.types[cfg_key]
                if typ in (int, float):
                    try:
                        typ(val)
                    except ValueError:
                        errors.append(f"{cfg_key} 需为 {typ.__name__}，当前值：{val!r}")
            return errors

        def load_values(self, values):
            """把纯 dict 值写入表单，便于 UI 与测试复用同一读取逻辑。"""
            for cfg_key, value in values.items():
                self.set_value(cfg_key, value)

        def load_from_cfg(self, path):
            """用现有 cfg 回填非路径参数。"""
            self.load_values(load_cfg_form_values(path))

    return ParamsPanel(parent)
