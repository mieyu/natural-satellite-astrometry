"""NSPA 桌面 UI 主程序（Tkinter）。

启动：在仓库根执行  python ui/app.py
（cwd 必须是仓库根，cfg 用相对路径，运行时据此解析 inputs/outputs。）

经 subprocess 调用 `python -m nspa.main`，输入/输出根目录可在界面中选择。
CLI 与 UI 可并存。
"""

import os
import platform
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

REPO_ROOT = Path(__file__).resolve().parents[1]
# 让 `import nspa` 可用（从仓库根启动时本就可用，这里兜底）
sys.path.insert(0, str(REPO_ROOT))

from ui import cfg_writer, inputs_panel, params_panel  # noqa: E402
from ui.runner import PipelineRunner  # noqa: E402

DEFAULT_CFG_NAME = "nspa2024.cfg"
STEPS = ["all", "pre", "detect", "match", "comoc", "report"]


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.pack(fill="both", expand=True)
        self.runner = PipelineRunner()
        self._img_ref = None
        self._selection = None
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
        ttk.Combobox(bar, textvariable=self.var_step, values=STEPS,
                     state="readonly", width=8).pack(side="left", padx=4)
        self.btn_run = ttk.Button(bar, text="▶ 运行", command=self._run)
        self.btn_run.pack(side="left", padx=6)
        ttk.Button(bar, text="打开输出目录", command=self._open_output).pack(side="left")

        # 参数表单（横向和纵向可滚）
        pbox = ttk.LabelFrame(self, text="参数（默认值来自 nspa.config，可改）")
        pbox.pack(fill="x", pady=(0, 6))
        canvas = tk.Canvas(pbox, height=245, highlightthickness=0)
        vbar = ttk.Scrollbar(pbox, orient="vertical", command=canvas.yview)
        hbar = ttk.Scrollbar(pbox, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        pbox.columnconfigure(0, weight=1)
        pbox.rowconfigure(0, weight=1)
        canvas.grid(row=0, column=0, sticky="ew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.params = params_panel.build_widget(canvas)
        canvas.create_window((0, 0), window=self.params, anchor="nw")
        self.params.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._bind_mousewheel(canvas)
        self._load_selected_cfg(log=False)

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
        self.img_label = ttk.Label(rbox, text="（运行后显示）", anchor="center")
        self.img_label.pack(fill="both", expand=True)
        self.files_list = tk.Listbox(rbox, height=6)
        self.files_list.pack(fill="x")

    # ── 根目录选择 ──
    def _choose_root(self, kind):
        if self.runner.running:
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
        if self.runner.running:
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
        self._img_ref = None
        self.img_label.config(image="", text="（运行后显示）")
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

    def _bind_mousewheel(self, canvas):
        def on_mousewheel(event):
            direction = -1 if event.delta > 0 else 1
            if event.state & 0x1:
                canvas.xview_scroll(direction, "units")
            else:
                canvas.yview_scroll(direction, "units")
            return "break"

        def on_linux_up(_event):
            canvas.yview_scroll(-3, "units")
            return "break"

        def on_linux_down(_event):
            canvas.yview_scroll(3, "units")
            return "break"

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        canvas.bind("<Button-4>", on_linux_up)
        canvas.bind("<Button-5>", on_linux_down)

    # ── 运行 ──
    def _run(self):
        sel = self.inputs.get_selection()
        if not sel:
            messagebox.showerror("缺少输入", "请先选择有效的目标/观测期（预览须显示 ✓ 解析到观测日）。")
            return
        errors = self.params.validate()
        if errors:
            messagebox.showerror("参数错误", "\n".join(errors))
            return

        scalars = self.params.get_scalars()
        scalars["4specified-output"] = sel["output_dir"]
        scalars["run_manifest_dir"] = sel["run_manifest_dir"]
        scalars["3obj_total"] = str(sel["obj_total"])

        cfg_path = self.input_root / "configs" / "_ui_run.cfg"
        try:
            cfg_writer.write_cfg(cfg_path, scalars, sel["fitspaths"],
                                 sel["eph_files"], sel["gaia_catfile"])
        except OSError as exc:
            messagebox.showerror("配置保存失败", f"无法写入 {cfg_path}：\n{exc}")
            return
        self.log.delete("1.0", "end")
        self._append(f"已生成配置：{cfg_path}")
        self._output_dir = (REPO_ROOT / sel["output_dir"]).resolve()

        self.btn_run.config(state="disabled")
        for button in self.path_buttons:
            button.config(state="disabled")
        try:
            self.runner.start(cfg_path, self.var_step.get(), REPO_ROOT)
        except OSError as exc:
            self.btn_run.config(state="normal")
            for button in self.path_buttons:
                button.config(state="normal")
            messagebox.showerror("启动失败", str(exc))
            return
        self.after(120, self._drain)

    def _drain(self):
        for line in self.runner.poll_lines():
            self._append(line)
        if self.runner.finished:
            self.btn_run.config(state="normal")
            for button in self.path_buttons:
                button.config(state="normal")
            rc = self.runner.returncode
            self._append(f"\n=== 运行结束，退出码 {rc} ===")
            if rc == 0:
                self._show_results()
        else:
            self.after(120, self._drain)

    def _append(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    # ── 结果展示 ──
    def _show_results(self):
        out = getattr(self, "_output_dir", None)
        if not out or not out.is_dir():
            return
        self.files_list.delete(0, "end")
        for p in sorted(out.iterdir()):
            if p.suffix in (".out", ".dat", ".png"):
                self.files_list.insert("end", p.name)
        png = out / "OC_summary.png"
        if png.exists():
            try:
                img = tk.PhotoImage(file=str(png))
                factor = max(1, img.width() // 480)
                if factor > 1:
                    img = img.subsample(factor, factor)
                self._img_ref = img
                self.img_label.config(image=img, text="")
            except Exception as exc:
                self.img_label.config(text=f"无法显示图像：{exc}")
        else:
            self.img_label.config(text="未找到 OC_summary.png")

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
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
