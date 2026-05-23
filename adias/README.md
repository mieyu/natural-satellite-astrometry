# ADIAS

CCD 天文图像处理流水线，5 步将原始 FITS 观测数据归算为天体的 O-C 残差图。

## 5 步流程

| 步骤 | 模块 | 输入 | 输出 |
|---|---|---|---|
| `pre` | preprocessor | `fits/*.fit` | `fits_n/*_n.fit` |
| `detect` | detector | `fits_n/*_n.fit` 或 `fits/*.fit` | `fits_reg/*.fit.reg` |
| `match` | matcher | `fits_reg/*.fit.reg` + GAIA 星表 + 历表 | `fits_ref/*.ref.reg` + `fits_out/object_N.out` |
| `comoc` | analyzer | `fits_out/object_N.out` | `fits_out/final_*` + `<MATH>/*N.dat` |
| `report` | reporter | `<MATH>/*N.dat` | `<MATH>/OC_summary.png` + `OC_UN.png` |

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
| `--config` | `<项目根>/configs/adias2024.cfg` | 配置文件路径 |

观测目录路径由 cfg 的 `1fitspath` 控制（不再需要单独的 `fitspath.in`）。
控制台输出会同时写入当前目录下的 `控制台输出.txt`。

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

跨日汇总（`.dat`、`OC_UN.png`、`OC_summary.png`、`00oc_*.out`、`*_all_*.out`、
`*_obsdata_*.out`）落在 cfg `4specified-output` 指定的目录。

## 作为库调用

5 个入口与配置解析已在顶层包导出：

```python
from adias import (
    parse_config, expand_fitspath,
    run_pre, run_detect, run_match, run_comoc, run_report,
)

config = parse_config("configs/adias2024.cfg")
fitspath_list = expand_fitspath(config["fitspath"])

run_pre(config, fitspath_list)
run_detect(config, fitspath_list)
run_match(config, fitspath_list)
run_comoc(config, fitspath_list)
run_report(config)
```

## 分层

| 层 | 职责 |
|---|---|
| `core/` | 5 步流程编排（pre / detect / match / comoc / report） |
| `domain/` | 领域模型与算法（astrometry、matching、数据模型） |
| `adapters/` | 文件格式适配（GAIA/历表 / object_out / .reg） |
| `application/` | 流水线运行器（PipelineRunner / OutputSink / RunManifest） |
| `io/` | 底层文件 IO |
| `utils/` | 通用工具（图像、数学） |
| `errors.py` | 分层异常：ConfigError / DataFormatError / ProcessingError |
