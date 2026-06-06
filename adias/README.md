# ADIAS

CCD 天文图像处理流水线，5 步将原始 FITS 观测数据归算为天体的 O-C 残差图。

## 5 步流程

| 步骤 | 模块 | 输入 | 输出 |
|---|---|---|---|
| `pre` | preprocessor | `fits/*.fit` | `fits_n/*_n.fit` |
| `detect` | detector | `fits_n/*_n.fit` 或 `fits/*.fit` | `fits_reg/*.fit.reg` |
| `match` | matcher | `fits_reg/*.fit.reg` + GAIA 星表 + 历表 | `fits_ref/*.ref.reg` + `fits_out/object_N.out` |
| `comoc` | analyzer | `fits_out/object_N.out` | `fits_out/final_*` + `<MATH>/*N.dat` |
| `report` | reporter | `<MATH>/*N.dat` | `<MATH>/OC_summary.png` + `OC_U{N}.png` |

`<MATH>` 为 cfg 中 `4specified-output` 指定的跨日汇总目录。

## 安装

```bash
pip install numpy scipy astropy opencv-python matplotlib
```

## 运行

从项目根目录调用：

```bash
# 跑完整 5 步
python -m adias.main

# 跑指定单步
python -m adias.main --step pre
python -m adias.main --step detect
python -m adias.main --step match
python -m adias.main --step comoc
python -m adias.main --step report

# 指定配置文件
python -m adias.main --config /path/to/adias2024.cfg
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--step` | `all` | 运行阶段：`pre` / `detect` / `match` / `comoc` / `report` / `all` |
| `--config` | `<项目根>/inputs/configs/adias2024.cfg` | 配置文件路径 |

观测目录路径由 cfg 的 `1fitspath` 控制（不再需要单独的 `fitspath.in`）。
控制台输出会同时写入当前目录下的 `控制台输出.txt`。

## 项目输入/输出路径约定

当前仓库按 `inputs/` 放输入、`outputs/` 放结果组织数据：

```
inputs/
├── configs/                 # cfg 配置文件
├── images/<目标>/<观测期>/... # 原始观测图目录树
└── catalogs/<目标>/<观测期>/  # 历表与 GAIA 星表

outputs/
└── results/<目标>/<观测期>/   # UI 默认生成的跨日汇总输出目录
```

观测图的最终输入单元仍是某个观测日下的 `fits/*.fit`。`1fitspath` 可以指向：

- 单个观测日的 `fits` 目录；
- 包含多个 `YYYYMMDD/fits` 子目录的上级目录；
- 更高一级的目标/观测期目录，只要程序能从中展开到有效观测日。

星表和历表按同一个目标/观测期查找，例如：

```
inputs/catalogs/S9/2024/EPH_S9_202411.DAT
inputs/catalogs/S9/2024/GAIA3_S9_202410.DAT
```

输出目录由 cfg 的 `4specified-output` 决定。当前 UI 生成 cfg 时使用
`outputs/results/<目标>/<观测期>`，例如选择 `S9` + `2024` 时输出到
`outputs/results/S9/2024`；即使实际 `1fitspath` 进一步落到 `202411` 或
`202412`，输出目录仍按目标/观测期这一层确定。

## 配置文件

`adias2024.cfg` 用键值对形式分 5 段，每个键以数字前缀对应步骤（`1xxx`=pre，`2xxx`=detect，…）。常用项：

```ini
# pre
1fitspath=observation_images/observation_image_S/202411   # 观测目录（支持 YYYYMMDD/fits 自动展开，可写相对工作目录或绝对路径）
1fitspath2=observation_images/observation_image_S/202412  # 多个时可加序号 1fitspath2/1fitspath3 ...
1superflag=1          # 0=跳过；1=中值滤波；2=同态滤波；3=Retinex
1med_length=65        # 中值滤波窗口长
1med_width=1          # 中值滤波窗口宽（长/宽其一为 1 时走串联单向滤波）
1bkgdmode=2           # 1=除法归一化；2=减法扣除
1enhance_flag=1       # 1=滤波后再做一次 3×3 均值降噪

# detect
2bkgd_threshold=5.0   # 背景阈值系数（越大检测星越少）
2snr_threshold=1.0    # 信噪比下限
2pos_method=1         # 1/2/3 阶修正矩定中心

# match
3tele_label=km100B    # 望远镜标签：ss156 / ss156_2014 / km100 / km100B / lj240
3tele_focal=13300.0   # 焦距 (mm)
3ccd_scale=0.0135     # 像素尺寸 (mm)
3ccd_fieldsize=15     # 视场半宽 (arcmin)
3modeltype=6          # 底片常数项数：6 / 12 / 20 / 30
3plate_angle=180.0    # 底片旋转角初值（度）
3gaia_minmag=5.0
3gaia_maxmag=18.5
3match_limit=5.0      # 匹配距离阈值 (arcsec)
3obj_total=1          # 待归算目标数
3gaia_catfile1=...    # GAIA 星表路径
3obj_ephfile1=...     # 目标 1 的 IMCCE 历表路径
# 多目标则依次写 3obj_ephfile2、3obj_ephfile3 ...

# comoc
4specified-output=... # 跨日汇总目录（.dat / OC_*.png 落在这里）
4eps=10.0             # 残差绝对值上限 (arcsec)
4std_limit=2.5        # 野值剔除 sigma 倍数（>0 用 sigma 模式）
4mean_limit=1.0       # 野值剔除均值偏差阈值（std_limit=0 时启用）
4del_flag=0           # 1=运行后删除 fits_n / fits_reg / fits_ref
```

注释行用 `;` / `#` / `!` / `[` 开头；行内 `%` 之后视为注释。

## 产物落地约定

输入：`<root>/<YYYYMMDD>/fits/*.fit`

每次跑完后产物按阶段分子目录组织在 `<root>/<YYYYMMDD>/` 下：

```
<YYYYMMDD>/
├── fits/             # 原始观测图（输入，不动）
├── fits_n/           # 01pre 产物：*_n.fit
├── fits_reg/         # 02detect 产物：*.fit.reg
├── fits_ref/         # 03match 产物：*.fitN.ref.reg
└── fits_out/         # 03/04 产物：object_N.out, final_object_N.out, final_oc_N.out
```

跨日汇总（`.dat`、`OC_U{N}.png`、`OC_summary.png`、`00oc_*.out`、`*_all_*.out`、
`*_obsdata_*.out`）落在 cfg `4specified-output` 指定的目录。

## 作为库调用

推荐复用 CLI 相同的流水线封装，这样会保留配置校验与 `runs/<run_id>/manifest.json` 记录：

```python
from adias.application.context import build_context
from adias.application.pipeline import PipelineRunner
from adias.application.steps import select_steps, selected_step_names
from adias.config import load_config

step = "all"  # 或 pre / detect / match / comoc / report
step_names = selected_step_names(step)

config = load_config("configs/adias2024.cfg", steps=step_names)
ctx = build_context(config, step_names)

PipelineRunner(select_steps(step)).run(ctx)
```

如需直接调用单步核心函数，应从 `adias.core.*` 显式导入：

```python
from adias.config import load_config
from adias.core.preprocessor import run_pre
from adias.paths import expand_fitspath

config = load_config("configs/adias2024.cfg", steps=["pre"])
fitspath_list = expand_fitspath(config.fitspaths)

run_pre(config, fitspath_list)
```

## 分层

| 层 | 职责 |
|---|---|
| `core/` | 5 步流程编排（pre / detect / match / comoc / report） |
| `domain/` | 领域模型与算法（astrometry、matching、数据模型） |
| `application/` | 流水线运行器、运行上下文与 manifest 记录（PipelineRunner / RunManifest） |
| `io/` | 文件格式读写（FITS、GAIA/历表、object_out、.reg） |
| `utils/` | 通用工具（图像、数学） |
| `errors.py` | 分层异常：ConfigError / DataFormatError / ProcessingError |
