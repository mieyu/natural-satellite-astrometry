"""输入选择面板：扫描 inputs/ 目录，用级联下拉框选数据集。

设计要点
--------
输入树深度不统一（S9/2024 下是月目录、U/2020 下直接是日目录、有的平铺），
所以不写死层数：选完 目标/观测期 后，用 nspa.paths.expand_fitspath 试解析候选路径，
解析不出观测日就再露出一级子目录下拉，直到解析成功。

本模块上半部是纯函数（可无 GUI 测试），下半部是 Tk 控件。
"""

import re
from datetime import datetime
from pathlib import Path

from nspa.paths import STAGE_DIRS, expand_fitspath, list_fits

_EPH_RE = re.compile(r"(?:Q_)?EPH_(.+)_(\d{6})\.DAT$", re.IGNORECASE)
_GAIA_RE = re.compile(r"(?:Q_)?GAIA3_(.+)_(\d{6})\.DAT$", re.IGNORECASE)
_AUTO_EPH_CHOICE = "自动匹配观测月"
_ALL_DAYS_CHOICE = "全部观测日"


def parse_eph_name(path):
    """EPH_<代号>_<YYYYMM>.DAT -> (代号, 月)；不匹配时月为 None。"""
    m = _EPH_RE.fullmatch(Path(path).name)
    if not m:
        return Path(path).stem, None
    return m.group(1), m.group(2)


def derive_obs_month(candidate):
    """从候选路径里取 6 位 YYYYMM（如 .../202411）；取不到返回 None。"""
    for part in reversed(Path(candidate).parts):
        if re.fullmatch(r"\d{6}", part):
            return part
    return None


def observation_months(days):
    """从观测日目录或原始 FITS 文件名确认全部观测月。无法确认时返回空列表。"""
    months = set()
    for day in days:
        files = list_fits(day)
        if not files:
            return []
        dirname = Path(day).parent.name
        for file in files:
            candidates = [dirname, file.name[:8]]
            candidates.extend(re.findall(r"(?:19|20)\d{6}", file.stem))
            dates = [value for value in candidates if _is_calendar_date(value)]
            if not dates:
                return []
            months.update(value[:6] for value in dates)
    return sorted(months)


def _is_calendar_date(value):
    if not re.fullmatch(r"\d{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def select_eph(eph_files, obs_month=None):
    """按目标代号分组挑选历表，返回 (每目标一个 eph 列表, 已选目标数)。

    仅选择与观测月一致的文件；未知月份或缺文件时不猜测。
    """
    groups = {}
    # Q_ 是现有 2006 配置使用的完整历表组；同目标同月优先使用该版本。
    for f in sorted(eph_files, key=lambda p: (not Path(p).name.upper().startswith("Q_"), str(p))):
        code, month = parse_eph_name(f)
        groups.setdefault(code, []).append((month, f))
    selected = []
    for code, variants in groups.items():
        chosen = next((f for month, f in variants if month == obs_month), None)
        if chosen is not None:
            selected.append(chosen)
    return selected, len(selected)


def matching_gaia_name(gaia_files, obs_month, current_name=""):
    """保留有效的手动选择；否则仅在观测月有唯一星表时自动选择。"""
    if current_name in gaia_file_names(gaia_files):
        return current_name
    matches = []
    for path in gaia_files:
        match = _GAIA_RE.fullmatch(Path(path).name)
        if match and match.group(2) == obs_month:
            matches.append(Path(path).name)
    return matches[0] if len(matches) == 1 else ""


def ephemeris_selection_errors(months, selected_eph):
    """每个目标选一份同月历表，避免把重复文件当成两个目标。"""
    if len(months) != 1:
        return ["无法确认唯一观测月；请按月选择图像目录"]
    month = months[0]
    errors = []
    if not selected_eph:
        errors.append(f"{month} 没有选中目标历表")
    codes = set()
    for path in selected_eph:
        code, eph_month = parse_eph_name(path)
        if eph_month != month:
            errors.append(f"目标历表与观测月 {month} 不一致：{Path(path).name}")
        if code in codes:
            errors.append(f"目标 {code} 选中了多份历表；每个目标请只选一份")
        codes.add(code)
    return errors


def catalog_selection_errors(months, all_eph, selected_eph, gaia_name, auto_eph,
                             gaia_files):
    """匹配前核对观测月与历表；GAIA 文件可由用户跨月选择。"""
    errors = ephemeris_selection_errors(months, selected_eph)
    if len(months) != 1:
        return errors
    month = months[0]
    available_codes = {parse_eph_name(path)[0] for path in all_eph}
    selected_codes = {parse_eph_name(path)[0] for path in selected_eph}
    missing = sorted(available_codes - selected_codes)
    if missing and auto_eph:
        errors.append(f"{month} 缺少目标历表：{', '.join(missing)}")
    if not gaia_name:
        errors.append(f"{month} 没有选中 GAIA 星表")
    elif gaia_name not in gaia_file_names(gaia_files):
        errors.append(f"GAIA 星表不在当前数据目录中：{gaia_name}")
    return errors


def eph_file_names(eph_files):
    """返回历表文件的可见名称，按文件名排序。"""
    return sorted(Path(p).name for p in eph_files)


def default_eph_names(eph_files, obs_month=None):
    """返回自动匹配观测月后默认选中的历表文件名。"""
    selected, _count = select_eph(eph_files, obs_month)
    return eph_file_names(selected)


def resolve_eph_names(eph_files, names):
    """把 UI 中显示的历表文件名映射回 cfg 使用的路径。"""
    by_name = {Path(p).name: p for p in eph_files}
    return [by_name[name] for name in names if name in by_name]


def gaia_file_names(gaia_files):
    """返回 GAIA 星表文件的可见名称，按文件名排序。"""
    return sorted(Path(p).name for p in gaia_files)


def resolve_gaia_name(gaia_files, name):
    """把 UI 中显示的 GAIA 文件名映射回 cfg 使用的路径。"""
    by_name = {Path(p).name: p for p in gaia_files}
    return by_name.get(name, "")


# ── 纯函数：目录扫描与解析（无 Tk 依赖） ─────────────────────────────────────

def _subdir_names(path):
    p = Path(path)
    if not p.is_dir():
        return []
    return sorted(d.name for d in p.iterdir() if d.is_dir())


def images_root(repo_root, input_root=None):
    root = Path(input_root) if input_root is not None else Path(repo_root) / "inputs"
    return root / "images"


def catalogs_root(repo_root, input_root=None):
    root = Path(input_root) if input_root is not None else Path(repo_root) / "inputs"
    return root / "catalogs"


def list_targets(repo_root, input_root=None):
    """inputs/images 下的目标目录名（J / S9 / U ...）。"""
    return _subdir_names(images_root(repo_root, input_root))


def list_epochs(repo_root, target, input_root=None):
    """inputs/images/<target> 下的观测期目录名（2024 / 2020 ...）。"""
    if not target:
        return []
    return _subdir_names(images_root(repo_root, input_root) / target)


def resolve_fitspath(candidate):
    """对候选目录调用 expand_fitspath，返回 (观测日列表, 更深子目录名列表)。

    - 观测日列表非空 → candidate 可直接作为 fitspath。
    - 为空 → 返回其子目录名，供再下钻一层。
    """
    candidate = Path(candidate)
    # 选中某一天时，直接定位其原始图像目录，无需再选择 fits。
    for name in ("fits", "FITS"):
        raw = candidate / name
        if raw.is_dir() and list_fits(raw):
            return [raw], []
    days = expand_fitspath([str(candidate)]) if candidate.is_dir() else []
    # expand_fitspath 在“直接模式”下会原样返回 candidate，需确认确有 .fit
    valid_days = [d for d in days if list_fits(d)]
    if valid_days:
        return valid_days, []
    return [], _subdir_names(candidate)


def data_subdir_choices(base):
    """列出相对观测期的可选目录；保留月份/日期层级，不列处理产物。"""
    base = Path(base)
    choices = []

    def visit(parent):
        if list_fits(parent):
            return
        if any((parent / name).is_dir() and list_fits(parent / name)
               for name in ("fits", "FITS")):
            return
        for name in _subdir_names(parent):
            child = parent / name
            if name.lower() in {*STAGE_DIRS, "fits"} or child.is_symlink():
                continue
            choices.append(child.relative_to(base).as_posix())
            visit(child)

    visit(base)
    return choices


def scan_catalog(repo_root, target, epoch, input_root=None):
    """返回 (eph 文件列表, gaia 文件列表, 星表目录 Path)，均为该 target/epoch 下。"""
    cat_dir = catalogs_root(repo_root, input_root) / target / epoch
    if not cat_dir.is_dir():
        return [], [], cat_dir
    files = [p for p in cat_dir.iterdir() if p.is_file()]
    eph = sorted(str(p) for p in files if _EPH_RE.fullmatch(p.name))
    gaia = sorted(str(p) for p in files if _GAIA_RE.fullmatch(p.name))
    return eph, gaia, cat_dir


def default_output_dir(repo_root, target, epoch, output_root=None):
    root = Path(output_root) if output_root is not None else Path(repo_root) / "outputs"
    return root / "results" / target / epoch


def relpath(repo_root, path):
    """尽量转成相对仓库根的路径（cfg 用相对路径，运行时 cwd=仓库根）。"""
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        return str(path)


# ── Tk 控件 ────────────────────────────────────────────────────────────────

def build_widget(parent, repo_root, on_change, input_root=None, output_root=None):
    """构造输入面板（延迟导入 tkinter，便于纯函数无 GUI 测试）。"""
    import tkinter as tk
    from tkinter import messagebox, ttk

    class EphemerisDialog(tk.Toplevel):
        def __init__(self, panel):
            super().__init__(panel)
            self.title("选择目标历表（可多选）")
            self.transient(panel.winfo_toplevel())
            self.geometry("620x400")
            self.minsize(480, 300)
            self.columnconfigure(0, weight=1)
            self.rowconfigure(1, weight=1)
            self.panel = panel
            month = panel._obs_months[0]
            heading = ttk.Label(self, text=f"观测月：{month}。勾选本次处理的目标，每个目标选择一份历表。",
                                padding=10, width=1, wraplength=580)
            heading.grid(row=0, column=0, columnspan=2, sticky="ew")
            heading.bind("<Configure>", lambda event: heading.configure(wraplength=max(1, event.width - 20)))
            canvas = tk.Canvas(self, width=1, highlightthickness=0, yscrollincrement=18)
            canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0))
            scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
            scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 10))
            canvas.configure(yscrollcommand=scrollbar.set)
            choices = ttk.Frame(canvas)
            window = canvas.create_window((0, 0), window=choices, anchor="nw")
            canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
            choices.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

            def scroll(event):
                if event.num in (4, 5):
                    units = -3 if event.num == 4 else 3
                else:
                    units = -int(event.delta / 120) if abs(event.delta) >= 120 else -int(event.delta)
                if canvas.yview() != (0.0, 1.0):
                    canvas.yview_scroll(units, "units")
                return "break"

            self.variables = {}
            selected = set(eph_file_names(panel._eph_files))
            for name in eph_file_names(panel._all_eph_files):
                same_month = parse_eph_name(name)[1] == month
                var = tk.BooleanVar(value=name in selected)
                self.variables[name] = var
                checkbox = ttk.Checkbutton(choices, variable=var, command=self._update_count,
                    text=name if same_month else f"{name}（与观测月不符）",
                    state="normal" if same_month else "disabled")
                checkbox.pack(fill="x", pady=3)
            for widget in (canvas, choices, *choices.winfo_children()):
                for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    widget.bind(sequence, scroll)
            controls = ttk.Frame(self, padding=10)
            controls.grid(row=2, column=0, columnspan=2, sticky="ew")
            ttk.Button(controls, text="选择本月全部目标", command=self._select_month).pack(side="left")
            ttk.Button(controls, text="清空", command=lambda: self._set_checked([])).pack(side="left", padx=6)
            self.count = ttk.Label(controls)
            self.count.pack(side="left")
            actions = ttk.Frame(self, padding=(10, 0, 10, 10))
            actions.grid(row=3, column=0, columnspan=2, sticky="e")
            ttk.Button(actions, text="取消", command=self.destroy).pack(side="left", padx=6)
            ttk.Button(actions, text="应用选择", command=self._apply).pack(side="left")
            self._update_count()
            self.bind("<Escape>", lambda _e: self.destroy())
            self.bind("<Return>", lambda _e: self._apply())
            self.grab_set()

        def _update_count(self):
            self.count.configure(text=f"已选 {sum(var.get() for var in self.variables.values())} 份历表")

        def _set_checked(self, names):
            for name, var in self.variables.items():
                var.set(name in names)
            self._update_count()

        def _select_month(self):
            self._set_checked(eph_file_names(self.panel._auto_eph_files))

        def _apply(self):
            names = [name for name, var in self.variables.items() if var.get()]
            try:
                self.panel.set_eph_names(names)
            except ValueError as exc:
                messagebox.showwarning("历表选择不完整", str(exc), parent=self)
                return
            self.destroy()

    class InputsPanel(ttk.LabelFrame):
        def __init__(self, master):
            super().__init__(master, text="输入数据集（从 inputs/ 选择）")
            self.repo_root = Path(repo_root)
            self.on_change = on_change
            self.input_root = Path(input_root) if input_root is not None else self.repo_root / "inputs"
            self.output_root = Path(output_root) if output_root is not None else self.repo_root / "outputs"

            self.var_target = tk.StringVar()
            self.var_epoch = tk.StringVar()
            self.var_sub = tk.StringVar()
            self.var_eph_summary = tk.StringVar(value="（请先选择目标和观测期）")
            self.var_gaia = tk.StringVar()
            self._eph_mode = "auto"
            self._manual_eph_names = []
            self._eph_dialog = None
            self._all_eph_files = []
            self._auto_eph_files = []
            self._eph_files = []      # 每目标挑选后的历表
            self._gaia_files = []
            self._obj_total = 1
            self._fitspath_candidate = None
            self._preview_days = []
            self._obs_months = []

            # 选择控件独立布局，预览文字不参与其列宽计算。
            fields = ttk.Frame(self)
            fields.pack(anchor="w", fill="x")
            row = 0
            ttk.Label(fields, text="目标").grid(row=row, column=0, sticky="w", padx=4, pady=3)
            self.cb_target = ttk.Combobox(fields, textvariable=self.var_target,
                                          state="readonly", width=18,
                                          values=list_targets(repo_root, self.input_root))
            self.cb_target.grid(row=row, column=1, sticky="w", padx=4)
            self.cb_target.bind("<<ComboboxSelected>>", self._on_target)

            ttk.Label(fields, text="观测期").grid(row=row, column=2, sticky="w", padx=4)
            self.cb_epoch = ttk.Combobox(fields, textvariable=self.var_epoch,
                                         state="readonly", width=14)
            self.cb_epoch.grid(row=row, column=3, sticky="w", padx=4)
            self.cb_epoch.bind("<<ComboboxSelected>>", self._on_epoch)

            ttk.Label(fields, text="观测日 / 子目录").grid(row=row, column=4, sticky="w", padx=4)
            self.cb_sub = ttk.Combobox(fields, textvariable=self.var_sub,
                                       state="readonly", width=22)
            self.cb_sub.grid(row=row, column=5, sticky="w", padx=4)
            self.cb_sub.bind("<<ComboboxSelected>>", self._on_sub)

            row += 1
            ttk.Label(fields, text="目标历表").grid(row=row, column=0, sticky="w", padx=4, pady=3)
            eph_controls = ttk.Frame(fields)
            eph_controls.grid(row=row, column=1, columnspan=5, sticky="ew", padx=4)
            eph_controls.columnconfigure(0, weight=1)
            ttk.Entry(eph_controls, textvariable=self.var_eph_summary, state="readonly",
                      width=46).grid(row=0, column=0, sticky="ew")
            self.btn_eph = ttk.Button(eph_controls, text="选择历表…（可多选）",
                                      command=self._choose_eph, state="disabled")
            self.btn_eph.grid(row=0, column=1, padx=6)
            self.btn_auto_eph = ttk.Button(eph_controls, text=_AUTO_EPH_CHOICE,
                                           command=self.set_eph_names, state="disabled")
            self.btn_auto_eph.grid(row=0, column=2)

            row += 1
            ttk.Label(fields, text="GAIA 星表").grid(row=row, column=0, sticky="w", padx=4, pady=3)
            self.cb_gaia = ttk.Combobox(fields, textvariable=self.var_gaia,
                                        state="readonly", width=46)
            self.cb_gaia.grid(row=row, column=1, columnspan=3, sticky="w", padx=4)
            self.cb_gaia.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())

            self.preview = ttk.Label(self, text="（请选择目标/观测期）", foreground="#555",
                                     width=1, anchor="w", justify="left", wraplength=400)
            self.preview.pack(fill="x", padx=4, pady=4)
            self.preview.bind("<Configure>", lambda event: self.preview.configure(
                wraplength=max(1, event.width - 8)))

        # —— 级联事件 ——
        def set_roots(self, input_root, output_root):
            input_root, output_root = Path(input_root), Path(output_root)
            input_changed = input_root != self.input_root
            self.input_root, self.output_root = input_root, output_root
            if input_changed:
                self.cb_target["values"] = list_targets(repo_root, self.input_root)
                self.var_target.set("")
                self._on_target()
                self.preview.config(text="（请选择目标/观测期）", foreground="#555")
            else:
                self.on_change()

        def _on_target(self, _e=None):
            self.var_epoch.set("")
            self.var_sub.set("")
            self.var_gaia.set("")
            self.cb_sub["values"] = []
            self.cb_gaia["values"] = []
            self._eph_mode = "auto"
            self._manual_eph_names = []
            self._all_eph_files = []
            self._auto_eph_files = []
            self._eph_files = []
            self._gaia_files = []
            self._apply_eph_choice()
            self.cb_epoch["values"] = list_epochs(repo_root, self.var_target.get(), self.input_root)
            self._fitspath_candidate = None
            self._obs_months = []
            self.preview.config(text="（请选择观测期）", foreground="#555")
            self.on_change()

        def _on_epoch(self, _e=None):
            t, e = self.var_target.get(), self.var_epoch.get()
            if not (t and e):
                return
            self._eph_mode = "auto"
            self._manual_eph_names = []
            base = images_root(repo_root, self.input_root) / t / e
            self.cb_sub["values"] = [_ALL_DAYS_CHOICE] + data_subdir_choices(base)
            self.var_sub.set(_ALL_DAYS_CHOICE)
            self._resolve()

        def _on_sub(self, _e=None):
            self._resolve()

        def set_eph_names(self, names=None):
            """None 恢复自动匹配；列表提交手动多选，失败时保留原选择。"""
            if names is None:
                self._eph_mode = "auto"
            else:
                names = list(dict.fromkeys(names))
                unknown = set(names) - set(eph_file_names(self._all_eph_files))
                if unknown:
                    raise ValueError("历表不在当前数据目录中：" + ", ".join(sorted(unknown)))
                selected = resolve_eph_names(self._all_eph_files, names)
                errors = ephemeris_selection_errors(self._obs_months, selected)
                if errors:
                    raise ValueError("\n".join(errors))
                self._manual_eph_names = names
                self._eph_mode = "manual"
            self._apply_eph_choice()
            self._update_preview()
            self.on_change()

        def _choose_eph(self):
            if len(self._obs_months) != 1:
                messagebox.showwarning("请先选择观测月", "请先选择同一月份的观测图像。", parent=self)
                return
            if self._eph_dialog is not None and self._eph_dialog.winfo_exists():
                self._eph_dialog.lift()
                return
            self._eph_dialog = EphemerisDialog(self)

        def _candidate_path(self):
            t, e, s = self.var_target.get(), self.var_epoch.get(), self.var_sub.get()
            if not (t and e):
                return None
            base = images_root(repo_root, self.input_root) / t / e
            return base / s if s and s != _ALL_DAYS_CHOICE else base

        def _resolve(self):
            cand = self._candidate_path()
            if cand is None:
                return
            days, subdirs = resolve_fitspath(cand)
            if days:
                self._fitspath_candidate = (
                    days[0] if len(days) == 1 and days[0].parent == cand else cand
                )
                self._preview_days = days
                months = observation_months(days)
                if months != self._obs_months:
                    self._eph_mode = "auto"
                    self._manual_eph_names = []
                self._obs_months = months
                t, e = self.var_target.get(), self.var_epoch.get()
                eph_all, gaia, cat_dir = scan_catalog(repo_root, t, e, self.input_root)
                self._all_eph_files = eph_all
                obs_month = self._obs_months[0] if len(self._obs_months) == 1 else None
                self._auto_eph_files, _count = select_eph(eph_all, obs_month)
                self._apply_eph_choice()
                self._gaia_files = gaia
                gaia_choices = gaia_file_names(gaia)
                self.cb_gaia["values"] = gaia_choices
                self.var_gaia.set(matching_gaia_name(
                    gaia, obs_month, self.var_gaia.get()))
                self._update_preview()
            else:
                self._fitspath_candidate = None
                self._preview_days = []
                self._obs_months = []
                self.var_gaia.set("")
                self.cb_gaia["values"] = []
                self._eph_mode = "auto"
                self._manual_eph_names = []
                self._all_eph_files = []
                self._auto_eph_files = []
                self._eph_files = []
                self._gaia_files = []
                self._apply_eph_choice()
                self.preview.config(
                    text="当前目录未找到观测图像，请选择具体月份或观测日。"
                         if subdirs else "当前目录没有原始 FITS 图像，请检查数据位置。",
                    foreground="#a60",
                )
            self.on_change()

        def _apply_eph_choice(self):
            if self._eph_mode == "auto":
                self._eph_files = list(self._auto_eph_files)
            else:
                self._eph_files = resolve_eph_names(self._all_eph_files, self._manual_eph_names)
            self._obj_total = len(self._eph_files)
            names = eph_file_names(self._eph_files)
            mode = _AUTO_EPH_CHOICE if self._eph_mode == "auto" else "手动多选"
            summary = f"{mode} · 已选 {len(names)} 份"
            if names:
                summary += "：" + ", ".join(names[:2]) + (" …" if len(names) > 2 else "")
            self.var_eph_summary.set(summary)
            state = "normal" if self._all_eph_files else "disabled"
            self.btn_eph.configure(state=state)
            self.btn_auto_eph.configure(state=state)

        def _update_preview(self):
            if self._fitspath_candidate is None:
                return
            day_names = ", ".join(d.parent.name for d in self._preview_days[:6])
            eph_names = ", ".join(Path(p).name for p in self._eph_files[:4])
            if len(self._eph_files) > 4:
                eph_names += " ..."
            gaia_count = len(self.cb_gaia["values"])
            selected_gaia = self.var_gaia.get()
            issues = self.selection_errors("match")
            self.preview.config(
                text=f"✓ 解析到 {len(self._preview_days)} 个观测日："
                     f"{day_names}{' ...' if len(self._preview_days) > 6 else ''}"
                     f"  |  目标数 {self._obj_total}，历表 {len(self._eph_files)} 个"
                     f"{f'：{eph_names}' if eph_names else ''}"
                     f"，GAIA 已选 {1 if selected_gaia else 0}/{gaia_count}"
                     f"{f'：{selected_gaia}' if selected_gaia else ''}"
                     f"{'  |  ⚠ ' + issues[0] if issues else ''}",
                foreground="#a60" if issues else "#0a0",
            )

        def selection_errors(self, step="all"):
            """匹配前核对观测月与所选历表；其他步骤不依赖这些星表。"""
            if step not in {"all", "match"}:
                return []
            return catalog_selection_errors(
                self._obs_months,
                self._all_eph_files,
                self._eph_files,
                self.var_gaia.get(),
                self._eph_mode == "auto",
                self._gaia_files,
            )

        # —— 对外取值 ——
        def get_selection(self):
            if self._fitspath_candidate is None:
                return None
            t, e = self.var_target.get(), self.var_epoch.get()
            return {
                "fitspaths": [relpath(repo_root, self._fitspath_candidate)],
                "eph_files": [relpath(repo_root, p) for p in self._eph_files],
                "gaia_catfile": relpath(repo_root, resolve_gaia_name(self._gaia_files, self.var_gaia.get()))
                                if self.var_gaia.get() else "",
                "output_dir": relpath(repo_root, default_output_dir(repo_root, t, e, self.output_root)),
                "run_manifest_dir": relpath(repo_root, self.output_root / "runs"),
                "obj_total": self._obj_total,
            }

    return InputsPanel(parent)
