"""NSPA 桌面 UI 主程序（Tkinter）。

启动：在仓库根执行  python ui/app.py
（cwd 必须是仓库根，cfg 用相对路径，运行时据此解析 inputs/outputs。）

经 subprocess 调用 `python -m nspa.main`，输入/输出根目录可在界面中选择。
CLI 与 UI 可并存。
"""

import os
import platform
import queue
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
# 让 `import nspa` 可用（从仓库根启动时本就可用，这里兜底）
sys.path.insert(0, str(REPO_ROOT))

from ui import cfg_writer, inputs_panel, params_panel  # noqa: E402
from ui.image_viewer import ResultImageViewer  # noqa: E402
from ui.runner import PipelineRunner  # noqa: E402
from ui.reference_worker import ReferenceWorker  # noqa: E402

DEFAULT_CFG_NAME = "nspa2024.cfg"
STEPS = ["all", "pre", "detect", "match", "comoc", "report"]


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.pack(fill="both", expand=True)
        self.runner = PipelineRunner()
        self.reference_worker = ReferenceWorker()
        self._preparing = False
        self._run_after_prepare = False
        self._locked_widgets = []
        self._reference_poll = None
        self._pipeline_poll = None
        self._img_ref = None
        self._result_png = None
        self._image_viewer = None
        self._close_pending = False
        self._selection = None
        self._resolved_selection = None
        self.input_root = REPO_ROOT / "inputs"
        self.output_root = REPO_ROOT / "outputs"
        self.var_input_root = tk.StringVar(value=str(self.input_root))
        self.var_output_root = tk.StringVar(value=str(self.output_root))
        self.path_buttons = []

        paths = ttk.LabelFrame(self, text="数据位置")
        paths.pack(fill="x", pady=(0, 6))
        paths.columnconfigure(1, weight=1)
        for row, (label, variable, kind) in enumerate([
            ("inputs 文件夹", self.var_input_root, "input"),
            ("outputs 文件夹", self.var_output_root, "output"),
        ]):
            ttk.Label(paths, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
            ttk.Entry(paths, textvariable=variable, state="readonly").grid(
                row=row, column=1, sticky="ew", padx=4)
            choose = ttk.Button(paths, text="选择…", command=lambda k=kind: self._choose_root(k))
            choose.grid(row=row, column=2, padx=4)
            reset = ttk.Button(paths, text="恢复默认", command=lambda k=kind: self._reset_root(k))
            reset.grid(row=row, column=3, padx=4)
            self.path_buttons.extend([choose, reset])

        # 输入面板
        self.inputs = inputs_panel.build_widget(
            self, REPO_ROOT, self._on_inputs_change, self.input_root, self.output_root)
        self.inputs.pack(fill="x", pady=(0, 6))
        self.inputs.references.on_prepare = self._prepare_references
        self.inputs.references.on_cancel = self._cancel_prepare

        # 控制条
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="配置模板").pack(side="left")
        cfg_names = params_panel.list_config_files(REPO_ROOT, self.input_root)
        initial_cfg = DEFAULT_CFG_NAME if DEFAULT_CFG_NAME in cfg_names else (cfg_names[0] if cfg_names else "")
        self.var_cfg = tk.StringVar(value=initial_cfg)
        self.cb_cfg = ttk.Combobox(bar, textvariable=self.var_cfg, values=cfg_names,
                                   state="readonly", width=18)
        self.cb_cfg.pack(side="left", padx=4)
        self.cb_cfg.bind("<<ComboboxSelected>>", self._load_selected_cfg)
        ttk.Label(bar, text="  步骤").pack(side="left")
        self.var_step = tk.StringVar(value="all")
        self.cb_step = ttk.Combobox(bar, textvariable=self.var_step, values=STEPS,
                                    state="readonly", width=8)
        self.cb_step.pack(side="left", padx=4)
        self.btn_run = ttk.Button(bar, text="▶ 运行", command=self._run)
        self.btn_run.pack(side="left", padx=6)
        self.btn_pause = ttk.Button(bar, text="⏸ 暂停", command=self._toggle_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 6))
        self.btn_stop = ttk.Button(bar, text="■ 中止", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="打开输出目录", command=self._open_output).pack(side="left")

        # 按阶段切换参数，表单在页内自适应宽度。
        pbox = ttk.LabelFrame(self, text="处理参数（按阶段切换，修改会保留）")
        pbox.pack(fill="x", pady=(0, 6))
        self.params = params_panel.build_widget(pbox)
        self.params.pack(fill="both", expand=True, padx=4, pady=4)
        self._load_selected_cfg(log=False)
        for key in ('3tele_label', '3ccd_fieldsize', '3delta_T'):
            self.params.entries[key].trace_add('write', self._invalidate_references)

        # 下方：日志 + 结果
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=True)

        logbox = ttk.LabelFrame(bottom, text="运行日志")
        logbox.pack(side="left", fill="both", expand=True)
        self.log = tk.Text(logbox, wrap="none", height=20, font=("Menlo", 11))
        lscroll = ttk.Scrollbar(logbox, command=self.log.yview)
        self.log.configure(yscrollcommand=lscroll.set)
        lscroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        rbox = ttk.LabelFrame(bottom, text="结果 (OC_summary.png) 与产物")
        rbox.pack(side="right", fill="both", expand=True)
        self.btn_enlarge = ttk.Button(rbox, text="放大查看结果图", command=self._open_result_image,
                                      state="disabled")
        self.btn_enlarge.pack(anchor="e", padx=6, pady=(4, 0))
        self.img_label = ttk.Label(rbox, text="（运行后显示）", anchor="center")
        self.img_label.pack(fill="both", expand=True)
        self.img_label.bind("<Double-Button-1>", self._open_result_image)
        self.files_list = tk.Listbox(rbox, height=6)
        self.files_list.pack(fill="x")

    # ── 根目录选择 ──
    def _choose_root(self, kind):
        if self.runner.running or self._preparing:
            return
        current = self.input_root if kind == "input" else self.output_root
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="选择 inputs 文件夹（内含 images、catalogs、configs）" if kind == "input" else "选择 outputs 文件夹",
            initialdir=str(current if current.is_dir() else current.parent),
            mustexist=True,
        )
        if not chosen:
            return
        path = Path(chosen).resolve()
        if kind == "input" and not (path / "images").is_dir():
            messagebox.showerror("目录不匹配", "请选择包含 images 文件夹的 inputs 目录。")
            return
        self._set_roots(input_root=path) if kind == "input" else self._set_roots(output_root=path)

    def _reset_root(self, kind):
        if self.runner.running or self._preparing:
            return
        if kind == "input":
            self._set_roots(input_root=REPO_ROOT / "inputs")
        else:
            self._set_roots(output_root=REPO_ROOT / "outputs")

    def _set_roots(self, input_root=None, output_root=None):
        input_root = Path(input_root).expanduser().resolve() if input_root is not None else self.input_root
        output_root = Path(output_root).expanduser().resolve() if output_root is not None else self.output_root
        input_changed = input_root != self.input_root
        self.input_root, self.output_root = input_root, output_root
        self.var_input_root.set(str(input_root))
        self.var_output_root.set(str(output_root))
        self.inputs.set_roots(input_root, output_root)
        self._output_dir = None
        self.files_list.delete(0, "end")
        self._close_image_viewer()
        self._img_ref = None
        self._result_png = None
        self.btn_enlarge.config(state="disabled")
        self.img_label.config(image="", text="（运行后显示）", cursor="")
        if input_changed:
            names = params_panel.list_config_files(REPO_ROOT, input_root)
            self.cb_cfg["values"] = names
            current = self.var_cfg.get()
            if current not in names:
                current = DEFAULT_CFG_NAME if DEFAULT_CFG_NAME in names else (names[0] if names else "")
            self.var_cfg.set(current)
            self._load_selected_cfg(log=False)

    # ── 输入联动 ──
    def _on_inputs_change(self):
        sel = self.inputs.get_selection()
        self._selection = sel
        self._apply_input_owned_values(sel)
        self._invalidate_references()

    def _invalidate_references(self, *_args):
        if hasattr(self, 'inputs') and not self._preparing:
            self._resolved_selection = None
            refs = self.inputs.references
            if refs.needs_download:
                refs.status.set('待准备：以当前图像、目标和参数确定下载范围；已有缓存会先校验再复用。')

    def _apply_input_owned_values(self, sel=None):
        sel = self._selection if sel is None else sel
        if not sel:
            return
        self.params.set_value("4specified-output", sel["output_dir"])
        self.params.set_value("3obj_total", sel["obj_total"])

    def _load_selected_cfg(self, _event=None, log=True):
        cfg_name = self.var_cfg.get()
        if not cfg_name:
            return
        cfg_path = self.input_root / "configs" / cfg_name
        if cfg_path.exists():
            self.params.load_from_cfg(cfg_path)
            # 路径和目标数继续由输入区下拉框决定。
            self._apply_input_owned_values()
            if log and hasattr(self, "log"):
                self._append(f"已从 {cfg_name} 载入非路径参数。")
        else:
            messagebox.showwarning("提示", f"未找到 {cfg_path}")

    # ── 运行 ──
    def _run(self):
        if self.runner.running or self._preparing:
            return
        sel = self.inputs.get_selection()
        if not sel:
            messagebox.showerror("缺少输入", "请先选择有效的目标/观测期（预览须显示 ✓ 解析到观测日）。")
            return
        input_errors = self.inputs.selection_errors(self.var_step.get())
        if input_errors:
            messagebox.showerror("输入月份不匹配", "\n".join(input_errors))
            return
        errors = self.params.validate()
        if errors:
            messagebox.showerror("参数错误", "\n".join(errors))
            return

        if self.inputs.references.needs_download and self.var_step.get() in {'all', 'match'}:
            self._prepare_references(run_after=True)
            return
        if self.inputs.references.auto_eph and self.var_step.get() in {'comoc', 'report'}:
            if self._resolved_selection is None:
                messagebox.showerror('请先准备历表', '请先点击“准备数据”，确保当前多目标顺序与输出编号一致。')
                return
            sel = self._resolved_selection
        self._start_pipeline(sel)

    def _set_locked(self, locked):
        if locked:
            if self._locked_widgets:
                return
            def freeze(widget):
                if 'state' in widget.keys():
                    self._locked_widgets.append((widget, str(widget.cget('state'))))
                    widget.configure(state='disabled')
                for child in widget.winfo_children():
                    freeze(child)
            for widget in (self.inputs, self.params, self.cb_cfg, self.cb_step, *self.path_buttons):
                freeze(widget)
        else:
            for widget, state in self._locked_widgets:
                if widget.winfo_exists():
                    widget.configure(state=state)
            self._locked_widgets = []

    def _prepare_references(self, run_after=False):
        if self.runner.running or self._preparing:
            return
        selection = self.inputs.get_selection()
        if not selection:
            messagebox.showerror('缺少输入', '请先选择有效的目标、观测期和观测日。')
            return
        errors = self.inputs.selection_errors('match')
        if errors:
            messagebox.showerror('参考数据选择不完整', '\n'.join(errors))
            return
        try:
            request = self.inputs.references.make_request(selection, self.params.get_scalars(),
                self.input_root, REPO_ROOT, self.inputs._auto_eph_files)
        except ValueError as exc:
            messagebox.showerror('参考数据设置错误', str(exc))
            return
        self._prepare_selection = dict(selection)
        self._prepare_scalars = self.params.get_scalars()
        self._prepare_step = self.var_step.get()
        self._run_after_prepare = run_after
        self._resolved_selection = None
        self._preparing = True
        self.inputs.references._busy = True
        self._set_locked(True)
        self.inputs.references.btn_cancel.configure(state='normal')
        self.btn_run.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self.btn_pause.configure(state='disabled')
        self.inputs.references.status.set('正在准备参考数据…')
        if run_after:
            self.log.delete('1.0', 'end')
        self._append('开始准备星表/历表；原有 inputs 文件和配置不会被覆盖。')
        self.reference_worker.start(request)
        self._reference_poll = self.after(100, self._drain_references)

    def _cancel_prepare(self):
        if self._preparing:
            self.reference_worker.cancel.set()
            self._run_after_prepare = False
            self.inputs.references.status.set('正在取消，等待当前网络请求结束（有超时限制）…')
            self.inputs.references.btn_cancel.configure(state='disabled')
            self.btn_stop.configure(state='disabled')

    def _drain_references(self):
        self._reference_poll = None
        terminal = None
        while True:
            try:
                kind, payload = self.reference_worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                self._append(payload)
                if not self.reference_worker.cancel.is_set():
                    self.inputs.references.status.set(payload)
            else:
                terminal = (kind, payload)
        if terminal is None or self.reference_worker.running:
            if terminal is not None:
                self.reference_worker.events.put(terminal)
            self._reference_poll = self.after(100, self._drain_references)
            return
        kind, payload = terminal
        if kind == 'complete' and self.reference_worker.cancel.is_set():
            kind, payload = 'cancelled', '已取消参考数据准备。'
        self._preparing = False
        self.inputs.references._busy = False
        self._set_locked(False)
        self.inputs.references.btn_cancel.configure(state='disabled')
        self.btn_run.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        if self._close_pending:
            self.winfo_toplevel().destroy()
            return
        if kind == 'complete' and not self.reference_worker.cancel.is_set():
            selection = self._prepare_selection
            selection.update(eph_files=[str(p) for p in payload.eph_files],
                             gaia_catfile=str(payload.gaia_catfile), obj_total=payload.obj_total,
                             reference_manifest=str(payload.manifest_path) if payload.manifest_path else '')
            self._resolved_selection = dict(selection)
            self.inputs.references.status.set(f'就绪：{payload.obj_total} 份历表、1 份 Gaia 星表；文件来源可在日志中查看。')
            self._append('历表：' + ', '.join(selection['eph_files']))
            self._append('Gaia：' + selection['gaia_catfile'])
            self._apply_input_owned_values(selection)
            if self._run_after_prepare:
                self._start_pipeline(selection, self._prepare_scalars, self._prepare_step)
        else:
            self.inputs.references.status.set('已取消参考数据准备。' if kind == 'cancelled'
                                             else '准备失败，详情见运行日志；可调整下载设置后重试。')
            self._append(str(payload))
            if kind == 'error':
                messagebox.showerror('参考数据准备失败', str(payload))
        self._run_after_prepare = False

    def _start_pipeline(self, sel, scalars=None, step=None):
        scalars = dict(self.params.get_scalars() if scalars is None else scalars)
        step = self.var_step.get() if step is None else step

        scalars["4specified-output"] = sel["output_dir"]
        scalars["run_manifest_dir"] = sel["run_manifest_dir"]
        scalars["3obj_total"] = str(sel["obj_total"])

        cfg_path = self.output_root / 'runs' / ('ui_' + uuid4().hex) / 'config.cfg'
        try:
            cfg_writer.write_cfg(cfg_path, scalars, sel["fitspaths"],
                                 sel["eph_files"], sel["gaia_catfile"])
            if sel.get('reference_manifest'):
                with cfg_path.open('a', encoding='utf-8') as stream:
                    stream.write('; reference_manifest=' + sel['reference_manifest'] + '\n')
        except OSError as exc:
            messagebox.showerror("配置保存失败", f"无法写入 {cfg_path}：\n{exc}")
            return
        if not sel.get('reference_manifest'):
            self.log.delete("1.0", "end")
        self._append(f"已生成配置：{cfg_path}")
        if sel.get('reference_manifest'):
            self._append('参考数据来源：' + sel['reference_manifest'])
        self._output_dir = (REPO_ROOT / sel["output_dir"]).resolve()
        self._run_started_ns = time.time_ns()
        self.files_list.delete(0, "end")
        self._close_image_viewer()
        self._img_ref = None
        self._result_png = None
        self.btn_enlarge.config(state="disabled")
        self.img_label.config(image="", text="（本次运行后显示）", cursor="")

        self._set_locked(True)
        self.btn_run.config(state="disabled")
        for button in self.path_buttons:
            button.config(state="disabled")
        try:
            self.runner.start(cfg_path, step, REPO_ROOT)
        except (OSError, RuntimeError) as exc:
            self._set_locked(False)
            self.btn_run.config(state="normal")
            for button in self.path_buttons:
                button.config(state="normal")
            messagebox.showerror("启动失败", str(exc))
            return
        self.btn_stop.config(state="normal")
        self.btn_pause.config(text="⏸ 暂停", state="normal")
        self._pipeline_poll = self.after(120, self._drain)

    def _toggle_pause(self):
        if self.runner.paused:
            if self.runner.resume():
                self.btn_pause.config(state="disabled")
                self._append("正在继续流水线及其子进程…")
        elif self.runner.pause():
            self.btn_pause.config(state="disabled")
            self._append("正在暂停流水线及其子进程…")

    def _stop(self):
        if self._preparing:
            self._cancel_prepare()
            return
        if self.runner.stop():
            self.btn_stop.config(state="disabled")
            self.btn_pause.config(state="disabled")
            self._append("正在中止流水线及其子进程…")

    def _on_close(self):
        if self._preparing:
            self._close_pending = True
            self._cancel_prepare()
            return
        proc = self.runner.proc
        if proc is not None and proc.poll() is None:
            self._close_pending = True
            self._stop()
            return
        self.winfo_toplevel().destroy()

    def _drain(self):
        self._pipeline_poll = None
        for line in self.runner.poll_lines():
            self._append(line)
        if self.runner.finished:
            self._set_locked(False)
            self.btn_run.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.btn_pause.config(text="⏸ 暂停", state="disabled")
            for button in self.path_buttons:
                button.config(state="normal")
            rc = self.runner.returncode
            if self.runner.stopped_by_user:
                self._append(f"\n=== 已中止，退出码 {rc} ===")
            else:
                self._append(f"\n=== 运行结束，退出码 {rc} ===")
            if rc == 0 and not self.runner.stopped_by_user:
                self._show_results()
            if self._close_pending:
                self.winfo_toplevel().destroy()
                return
        else:
            if not self.runner.stopped_by_user:
                self.btn_pause.config(
                    text="▶ 继续" if self.runner.paused else "⏸ 暂停",
                    state="disabled" if self.runner.transition else "normal",
                )
            self._pipeline_poll = self.after(120, self._drain)

    def destroy(self):
        self.reference_worker.cancel.set()
        for identifier in (self._reference_poll, self._pipeline_poll):
            if identifier is not None:
                self.after_cancel(identifier)
        super().destroy()

    def _append(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    # ── 结果展示 ──
    def _show_results(self):
        out = getattr(self, "_output_dir", None)
        if not out or not out.is_dir():
            return
        self.files_list.delete(0, "end")
        started_ns = getattr(self, "_run_started_ns", 0)
        for p in sorted(out.iterdir()):
            if p.suffix in (".out", ".dat", ".png") and p.stat().st_mtime_ns >= started_ns:
                self.files_list.insert("end", p.name)
        png = out / "OC_summary.png"
        if png.exists() and png.stat().st_mtime_ns >= started_ns:
            try:
                img = tk.PhotoImage(file=str(png))
                factor = max(1, img.width() // 480)
                if factor > 1:
                    img = img.subsample(factor, factor)
                self._img_ref = img
                self._result_png = png
                self.btn_enlarge.config(state="normal")
                self.img_label.config(image=img, text="", cursor="hand2")
            except Exception as exc:
                self.img_label.config(text=f"无法显示图像：{exc}")
        else:
            self.img_label.config(text="本次运行未生成 OC_summary.png")

    def _open_result_image(self, _event=None):
        png = self._result_png
        if png is None or not png.is_file():
            return
        if self._image_viewer is not None and self._image_viewer.winfo_exists():
            self._image_viewer.lift()
            self._image_viewer.focus_set()
            return
        try:
            self._image_viewer = ResultImageViewer(self.winfo_toplevel(), png)
        except tk.TclError as exc:
            messagebox.showerror("无法打开结果图", str(exc))

    def _close_image_viewer(self):
        if self._image_viewer is not None and self._image_viewer.winfo_exists():
            self._image_viewer.destroy()
        self._image_viewer = None

    def _open_output(self):
        out = getattr(self, "_output_dir", None)
        if not out or not out.is_dir():
            messagebox.showinfo("提示", "尚无输出目录（请先运行）。")
            return
        if platform.system() == "Darwin":
            subprocess.run(["open", str(out)])
        elif platform.system() == "Windows":
            os.startfile(str(out))  # noqa: SIM115
        else:
            subprocess.run(["xdg-open", str(out)])


def main():
    root = tk.Tk()
    root.title("NSPA 流水线 UI")
    root.geometry("1180x820")
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
