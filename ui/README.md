# ADIAS 桌面 UI

把命令行的「改 cfg → 跑流水线 → 看结果」搬进一个 Tkinter 窗口。**纯附加层**：不改动
`adias/` 任何代码，经子进程调用 `python -m adias.main`，CLI 与 UI 可并存。

## 启动

必须在**仓库根**目录启动（cfg 用相对路径，运行时据此解析 `inputs/`、`outputs/`）：

```bash
python ui/app.py
```

使用装好运行依赖（numpy/astropy/cv2/scipy）的解释器，例如本机的 conda 环境：

```bash
/opt/anaconda3/envs/AstroPyFITS/bin/python ui/app.py
```

## 用法

1. **输入区**：从 `inputs/images/` 里用下拉框选「目标 / 观测期」。树深度不一致时，
   预览提示「未解析到观测日」就用「子目录」下拉继续下钻，直到显示 `✓ 解析到 N 个观测日`。
   选定后会自动扫 `inputs/catalogs/<目标>/<观测期>/`，可用「目标历表」下拉选择自动匹配或某个历表，
   并用「GAIA 星表」下拉选择星表；输出目录默认 `outputs/results/<目标>/<观测期>/`。
2. **参数区**：所有 cfg 标量参数按 pre/detect/match/comoc 分组，默认值来自 `adias.config`，
   可直接改。顶部「配置模板」下拉会从 `inputs/configs/*.cfg` 载入非路径参数；fitspath、历表、
   星表、输出目录和 `obj_total` 仍由输入区选择结果决定。
3. 选「步骤」（`all` 或单步）→ 点 **▶ 运行**：日志实时滚动；结束后右侧显示 `OC_summary.png`
   并列出产物（`*.out` / `*.dat` / `*.png`）。「打开输出目录」可在文件管理器中查看。

## 工作原理

- 表单 → 生成 `inputs/configs/_ui_run.cfg`（沿用现有 cfg 格式，不覆盖手维护的 cfg）。
- 子进程 `python -m adias.main --config inputs/configs/_ui_run.cfg --step <步骤>`。
- 复用 `adias.paths.expand_fitspath` 解析观测日、`adias.config` 作字段表与默认值来源。

## 文件

| 文件 | 职责 |
|------|------|
| `app.py` | 主窗口、布局、运行生命周期、结果展示 |
| `inputs_panel.py` | 扫描 `inputs/` + 级联下拉 + fitspath/历表/星表解析（含纯函数） |
| `params_panel.py` | 分组参数表单（字段取自 `adias.config._SCALAR_FIELDS`） |
| `cfg_writer.py` | 表单值 → cfg 文本 |
| `runner.py` | 子进程运行 + stdout 流式回传 |
