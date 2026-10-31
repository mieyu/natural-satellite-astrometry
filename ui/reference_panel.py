"""Compact source controls and dialogs; all network work runs outside Tk."""

from pathlib import Path
import re
import tkinter as tk
from tkinter import messagebox, ttk

from nspa.reference_data.models import ReferenceError, ReferenceRequest
from nspa.reference_data.providers.imcce import TARGETS

INPUTS = 'inputs 已有文件'
DOWNLOAD = '自动下载'


class ReferencePanel(ttk.Frame):
    def __init__(self, parent, on_change):
        super().__init__(parent)
        self.on_change = on_change
        self.on_prepare = lambda: None
        self.on_cancel = lambda: None
        self.eph_source = tk.StringVar(value=INPUTS)
        self.gaia_source = tk.StringVar(value=INPUTS)
        self.observatory = tk.StringVar()
        self.network = tk.StringVar(value='直连')
        self.step = tk.StringVar(value='60')
        self.padding = tk.StringVar(value='5')
        self.margin = tk.StringVar(value='5')
        self.cache_override = tk.StringVar()
        self.cone_ra = tk.StringVar()
        self.cone_dec = tk.StringVar()
        self.cone_radius = tk.StringVar()
        self.download_targets = []
        self._inferred_station = ''
        self._busy = False
        self.status = tk.StringVar(value='默认使用 inputs 文件；自动下载不会覆盖已有文件。')
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        for label, variable in (('历表来源', self.eph_source), ('星表来源', self.gaia_source)):
            ttk.Label(bar, text=label).pack(side='left', padx=(4, 3))
            combo = ttk.Combobox(bar, textvariable=variable, values=(INPUTS, DOWNLOAD), width=13, state='readonly')
            combo.pack(side='left', padx=(0, 8))
            combo.bind('<<ComboboxSelected>>', lambda _e: self.changed())
        ttk.Button(bar, text='下载设置…', command=self.settings).pack(side='left', padx=3)
        self.btn_prepare = ttk.Button(bar, text='准备数据', command=lambda: self.on_prepare())
        self.btn_prepare.pack(side='left', padx=3)
        self.btn_cancel = ttk.Button(bar, text='取消下载', command=lambda: self.on_cancel(), state='disabled')
        self.btn_cancel.pack(side='left', padx=3)
        ttk.Label(self, textvariable=self.status, width=1, anchor='w', wraplength=900).pack(fill='x', padx=4, pady=(2, 0))

    @property
    def auto_eph(self):
        return self.eph_source.get() == DOWNLOAD

    @property
    def auto_gaia(self):
        return self.gaia_source.get() == DOWNLOAD

    @property
    def needs_download(self):
        return self.auto_eph or self.auto_gaia

    def changed(self):
        if not self._busy:
            self.status.set('待准备：将根据所选图像确定 UTC 时段和参考星天区。' if self.needs_download
                            else '使用 inputs 文件；保留本地历表多选。')
        self.on_change()

    def infer_station(self, paths):
        stations = set()
        for path in paths:
            try:
                with Path(path).open(encoding='utf-8-sig') as stream:
                    text = ''.join(next(stream, '') for _ in range(10))
                match = re.search(r'Observatory N:\s*(\w+)\s*-', text)
                if match:
                    stations.add(match[1])
            except (OSError, UnicodeError):
                continue
        station = next(iter(stations)) if len(stations) == 1 else ''
        if self.observatory.get() in ('', self._inferred_station):
            self.observatory.set(station)
        self._inferred_station = station

    def choose_targets(self, system, initial=()):
        codes = [code for code, item in TARGETS.items() if item['system'] == system]
        if not codes:
            messagebox.showwarning('请选择目标系统', '请先选择有效的观测目标目录。', parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title('选择下载的目标（可多选）')
        dialog.transient(self.winfo_toplevel())
        dialog.geometry('540x430')
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(dialog, text='每个勾选目标下载一份历表；目标数量自动同步。', padding=10).grid(row=0, column=0, columnspan=2, sticky='w')
        box = tk.Listbox(dialog, selectmode='multiple', exportselection=False)
        box.grid(row=1, column=0, sticky='nsew', padx=(10, 0))
        scroll = ttk.Scrollbar(dialog, command=box.yview)
        scroll.grid(row=1, column=1, sticky='ns', padx=(0, 10))
        box.configure(yscrollcommand=scroll.set)
        for index, code in enumerate(codes):
            box.insert('end', f'{code}   {TARGETS[code]["name"]}')
            if code in (self.download_targets or initial):
                box.selection_set(index)
        ttk.Label(dialog, text='单击即可选择/取消，可连续选择多个目标。', padding=8).grid(row=2, column=0, sticky='w')

        def apply():
            chosen = [codes[i] for i in box.curselection()]
            if not chosen:
                messagebox.showwarning('未选择目标', '请至少选择一个目标。', parent=dialog)
                return
            self.download_targets = chosen
            self.changed()
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=8)
        buttons.grid(row=3, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text='清空', command=lambda: box.selection_clear(0, 'end')).pack(side='left', padx=4)
        ttk.Button(buttons, text='取消', command=dialog.destroy).pack(side='left', padx=4)
        ttk.Button(buttons, text='应用选择', command=apply).pack(side='left')
        dialog.bind('<Escape>', lambda _e: dialog.destroy())
        dialog.grab_set()

    def settings(self):
        dialog = tk.Toplevel(self)
        dialog.title('自动下载设置')
        dialog.transient(self.winfo_toplevel())
        dialog.columnconfigure(1, weight=1)
        fields = [('IAU 观测站代码', self.observatory), ('连接方式', self.network),
                  ('历表步长（秒）', self.step), ('时间余量（分钟）', self.padding),
                  ('天区余量（角分）', self.margin), ('缓存目录（留空使用 inputs 下独立目录）', self.cache_override),
                  ('指定 Gaia 中心 RA（度，可留空）', self.cone_ra),
                  ('指定 Gaia 中心 Dec（度）', self.cone_dec), ('指定 Gaia 半径（角分）', self.cone_radius)]
        temporary = []
        for row, (label, original) in enumerate(fields):
            variable = tk.StringVar(value=original.get())
            temporary.append(variable)
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky='w', padx=10, pady=5)
            if original is self.network:
                widget = ttk.Combobox(dialog, textvariable=variable, values=('直连', '系统代理'), state='readonly', width=32)
            else:
                widget = ttk.Entry(dialog, textvariable=variable, width=34)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=5)
        ttk.Label(dialog, text='默认根据所有目标轨迹计算 Gaia 天区；指定天区时必须同时填写三项。\n'
                  '测站从已有历表建议填写，缺失时请明确指定。程序会核验实际返回模型。',
                  padding=10, wraplength=560).grid(row=len(fields), column=0, columnspan=2, sticky='w')

        def apply():
            values = [v.get().strip() for v in temporary]
            try:
                step, padding, margin = int(values[2]), float(values[3]), float(values[4])
                if not (1 <= step <= 3600 and 0 <= padding <= 60 and 0 <= margin <= 60):
                    raise ValueError('步长/余量超出允许范围')
                if any(values[6:]) and not all(values[6:]):
                    raise ValueError('指定 Gaia 天区的三项必须同时填写')
                if all(values[6:]):
                    a, b, r = map(float, values[6:])
                    if not (0 <= a < 360 and -90 <= b <= 90 and 0 < r <= 300):
                        raise ValueError('Gaia 中心或半径范围无效')
            except ValueError as exc:
                messagebox.showerror('下载设置无效', str(exc), parent=dialog)
                return
            for (_label, original), value in zip(fields, values):
                original.set(value)
            self.changed()
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=10)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text='取消', command=dialog.destroy).pack(side='left', padx=5)
        ttk.Button(buttons, text='应用设置', command=apply).pack(side='left')
        dialog.bind('<Escape>', lambda _e: dialog.destroy())
        dialog.grab_set()

    def make_request(self, selection, scalars, input_root, repo_root, local_hints=()):
        path = lambda p: (Path(repo_root) / p).resolve()
        try:
            cone = None
            values = [v.get().strip() for v in (self.cone_ra, self.cone_dec, self.cone_radius)]
            if any(values):
                if not all(values):
                    raise ValueError('指定 Gaia 天区的三项必须同时填写')
                a, b, radius = map(float, values)
                cone = (a, b, radius / 60)
            request = ReferenceRequest(
                fitspaths=tuple(path(p) for p in selection['fitspaths']),
                cache_root=Path(self.cache_override.get()).expanduser().resolve() if self.cache_override.get()
                           else Path(input_root) / 'catalogs/_downloaded',
                eph_source='download' if self.auto_eph else 'inputs',
                gaia_source='download' if self.auto_gaia else 'inputs',
                local_eph_files=tuple(path(p) for p in (local_hints if self.auto_eph else selection['eph_files'])),
                local_gaia_file=path(selection['gaia_catfile']) if selection['gaia_catfile'] else None,
                targets=tuple(self.download_targets), tele_label=scalars.get('3tele_label', ''),
                observatory=self.observatory.get().strip(), field_half_arcmin=float(scalars['3ccd_fieldsize']),
                delta_t=float(scalars.get('3delta_T', 0)), step_seconds=int(self.step.get()),
                padding_seconds=int(float(self.padding.get()) * 60), sky_margin_arcmin=float(self.margin.get()),
                network_mode='system' if self.network.get() == '系统代理' else 'direct', gaia_cone=cone)
        except (ValueError, KeyError) as exc:
            raise ReferenceError(f'下载参数不完整：{exc}') from exc
        if self.auto_eph and not re.fullmatch(r'\d{3}|[A-Za-z]\d{2}', request.observatory):
            raise ReferenceError('请在“下载设置”中明确填写三位 IAU 观测站代码，例如 286 或 500。')
        return request
