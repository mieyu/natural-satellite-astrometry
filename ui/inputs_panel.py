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

_EPH_RE = re.compile(r"EPH_(.+)_(\d{6})\.DAT$", re.IGNORECASE)
_GAIA_RE = re.compile(r"GAIA3_(.+)_(\d{6})\.DAT$", re.IGNORECASE)
_AUTO_EPH_CHOICE = "自动匹配观测月"
_ALL_DAYS_CHOICE = "全部观测日"


def parse_eph_name(path):
    """EPH_<代号>_<YYYYMM>.DAT -> (代号, 月)；不匹配时月为 None。"""
    m = _EPH_RE.search(Path(path).name)
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
    for f in eph_files:
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


def catalog_selection_errors(months, all_eph, selected_eph, gaia_name, auto_eph,
                             gaia_files):
    """匹配前核对观测月与历表；GAIA 文件可由用户跨月选择。"""
    if len(months) != 1:
        return ["无法确认唯一观测月；请按月选择图像目录"]
    month = months[0]
    errors = []
    available_codes = {parse_eph_name(path)[0] for path in all_eph}
    selected_codes = {parse_eph_name(path)[0] for path in selected_eph}
    missing = sorted(available_codes - selected_codes)
    if missing and auto_eph:
        errors.append(f"{month} 缺少目标历表：{', '.join(missing)}")
    if not selected_eph:
        errors.append(f"{month} 没有选中目标历表")
    for path in selected_eph:
        if parse_eph_name(path)[1] != month:
            errors.append(f"目标历表与观测月 {month} 不一致：{Path(path).name}")
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
    eph = sorted(str(p) for p in cat_dir.glob("EPH_*.DAT"))
    gaia = sorted(str(p) for p in cat_dir.glob("GAIA3_*.DAT"))
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
    from tkinter import ttk

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
            self.var_eph = tk.StringVar()
            self.var_gaia = tk.StringVar()
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
            self.cb_eph = ttk.Combobox(fields, textvariable=self.var_eph,
                                       state="readonly", width=46)
            self.cb_eph.grid(row=row, column=1, columnspan=3, sticky="w", padx=4)
            self.cb_eph.bind("<<ComboboxSelected>>", self._on_eph)

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
            self.var_eph.set("")
            self.var_gaia.set("")
            self.cb_sub["values"] = []
            self.cb_eph["values"] = []
            self.cb_gaia["values"] = []
            self._all_eph_files = []
            self._auto_eph_files = []
            self._eph_files = []
            self._gaia_files = []
            self.cb_epoch["values"] = list_epochs(repo_root, self.var_target.get(), self.input_root)
            self._fitspath_candidate = None
            self._obs_months = []
            self.preview.config(text="（请选择观测期）", foreground="#555")
            self.on_change()

        def _on_epoch(self, _e=None):
            t, e = self.var_target.get(), self.var_epoch.get()
            if not (t and e):
                return
            base = images_root(repo_root, self.input_root) / t / e
            self.cb_sub["values"] = [_ALL_DAYS_CHOICE] + data_subdir_choices(base)
            self.var_sub.set(_ALL_DAYS_CHOICE)
            self._resolve()

        def _on_sub(self, _e=None):
            self._resolve()

        def _on_eph(self, _e=None):
            self._apply_eph_choice()
            self._update_preview()
            self.on_change()

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
                self._obs_months = observation_months(days)
                t, e = self.var_target.get(), self.var_epoch.get()
                eph_all, gaia, cat_dir = scan_catalog(repo_root, t, e, self.input_root)
                self._all_eph_files = eph_all
                obs_month = self._obs_months[0] if len(self._obs_months) == 1 else None
                self._auto_eph_files, _count = select_eph(eph_all, obs_month)
                eph_choices = [_AUTO_EPH_CHOICE] + eph_file_names(eph_all)
                self.cb_eph["values"] = eph_choices
                if self.var_eph.get() not in eph_choices:
                    self.var_eph.set(_AUTO_EPH_CHOICE if eph_all else "")
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
                self.var_eph.set("")
                self.var_gaia.set("")
                self.cb_eph["values"] = []
                self.cb_gaia["values"] = []
                self._all_eph_files = []
                self._auto_eph_files = []
                self._eph_files = []
                self._gaia_files = []
                self.preview.config(
                    text="当前目录未找到观测图像，请选择具体月份或观测日。"
                         if subdirs else "当前目录没有原始 FITS 图像，请检查数据位置。",
                    foreground="#a60",
                )
            self.on_change()

        def _apply_eph_choice(self):
            choice = self.var_eph.get()
            if choice == _AUTO_EPH_CHOICE:
                self._eph_files = list(self._auto_eph_files)
            else:
                self._eph_files = resolve_eph_names(self._all_eph_files, [choice])
            self._obj_total = len(self._eph_files)

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
                self.var_eph.get() == _AUTO_EPH_CHOICE,
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
