# NSPA 桌面 UI

把命令行的「改 cfg → 跑流水线 → 看结果」搬进一个 Tkinter 窗口，经子进程调用
`python -m nspa.main`，CLI 与 UI 可并存。

## 启动

必须在**仓库根**目录启动（cfg 用相对路径，运行时据此解析 `inputs/`、`outputs/`）。
Windows 本机可直接双击仓库根目录的 `start_ui.cmd`，它会自动进入项目目录并使用项目虚拟环境打开界面。也可在普通 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe ui\app.py
```

若从受限执行环境启动时反复出现 `Failed to find real location of D:\ANACONDA\python.exe`，请关闭该界面，再从 Windows 资源管理器双击 `start_ui.cmd`。本机已确认受限环境的真实路径查询会返回“拒绝访问”，而普通桌面启动时路径查询正常；此情形无需重装 Python。

UI 运行流水线时沿用启动 UI 的 Python 解释器。其他系统也应使用装好
`requirements.txt` 中依赖的解释器，例如：

```bash
python ui/app.py
```

## 用法

1. **数据位置**：默认使用项目内的 `inputs` 和 `outputs`。点各自的「选择…」可指定其他位置（包括外接盘），点「恢复默认」返回项目目录。选择的是 `inputs` / `outputs` 文件夹本身，不是它们的上级目录。更换 inputs 会重新扫描数据和配置模板；更换 outputs 保留已选数据。
2. **输入区**：从所选 inputs 的 `images/` 里用下拉框选「目标 / 观测期」。树深度不一致时，
   预览提示「未解析到观测日」就用「子目录」下拉继续下钻，直到显示 `✓ 解析到 N 个观测日`。
   选定后会自动扫所选 inputs 的 `catalogs/<目标>/<观测期>/`，可用「目标历表」下拉选择自动匹配或某个历表，
   并用「GAIA 星表」下拉选择星表；最终结果保存到所选 outputs 的 `results/<目标>/<观测期>/`。
   界面所说的「GAIA 文件 N 个」是可选文件数，不是参考星颗数。匹配阶段只接受与原始图像观测月一致的历表和 GAIA 文件；缺少对应月份、或一次选中多个观测月时会提示并阻止运行。
3. **参数区**：所有 cfg 标量参数按 pre/detect/match/comoc 分组，默认值来自 `nspa.config`，
   可直接改。顶部「配置模板」下拉会从所选 inputs 的 `configs/*.cfg` 载入非路径参数；fitspath、历表、
   星表、输出目录和 `obj_total` 仍由输入区选择结果决定。
   `1pre_workers` 和 `2detect_workers` 控制两个阶段的进程数：`0` 表示自动（最多 2 个），`1` 表示串行，其他正数表示上限。程序还会按图像尺寸和当前可用内存降低实际并发；日志会显示最终进程数。若检测工作进程仍异常退出，可先设置 `2detect_workers=1`，仅重跑 `detect` 阶段，并保留完整日志排查。
4. 选「步骤」（`all` 或单步）→ 点 **▶ 运行**：日志实时滚动；结束后右侧仅显示本次生成的 `OC_summary.png`
   和产物（`*.out` / `*.dat` / `*.png`）。本次没有有效 O−C 数据时，退出码为 1，不展示旧报告图。运行中可点 **⏸ 暂停**，暂停流水线及其子进程；
   按钮会变成 **▶ 继续**，从暂停处继续运行。暂停期间仍可点 **■ 中止**，结束流水线及检测阶段的子进程；
   中止时已经写出的文件可能不完整。关闭正在运行的窗口也会先中止流水线。
   「打开输出目录」可在文件管理器中查看。

## 工作原理

- 表单 → 在所选 inputs 的 `configs/_ui_run.cfg` 生成配置（沿用现有 cfg 格式，不覆盖手维护的 cfg）。
- 子进程 `python -m nspa.main --config <所选 inputs>/configs/_ui_run.cfg --step <步骤>`，仍在项目根目录启动。
- 所选 inputs 保持 `images/`、`catalogs/`、`configs/` 的原目录结构；所选 outputs 保持 `results/`、`runs/` 的原目录结构。
- 中间产物继续保存到观测日目录中的 `fits_n`、`fits_reg`、`fits_ref`、`fits_out`，即跟随原始图像所在位置。
- UI 写出的 `run_manifest_dir` 指向所选 outputs 的 `runs/`。未配置此键的旧 cfg 仍默认写到运行目录的 `outputs/runs/`。
- `comoc` 每次新建 `run_<运行编号>_<目标序号>.dat`，历史汇总文件保留；同一次 `all` 运行的报告只读取本次新建的文件。单独运行 `report` 时仍会读取输出目录中已有的 `.dat`。
- 复用 `nspa.paths.expand_fitspath` 解析观测日、`nspa.config` 作字段表与默认值来源。

## 文件

| 文件 | 职责 |
|------|------|
| `app.py` | 主窗口、布局、运行生命周期、结果展示 |
| `inputs_panel.py` | 扫描 `inputs/` + 级联下拉 + fitspath/历表/星表解析（含纯函数） |
| `params_panel.py` | 分组参数表单（字段取自 `nspa.config._SCALAR_FIELDS`） |
| `cfg_writer.py` | 表单值 → cfg 文本 |
| `runner.py` | 子进程运行 + stdout 流式回传 |
