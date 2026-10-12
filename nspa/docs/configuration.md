# NSPA 配置说明

本文档说明 `nspa.cfg` / `inputs/configs/*.cfg` 的当前有效配置。运行时以
[nspa/config.py](../config.py)
中的解析表为准；旧 cfg 文件里的说明文字可能仍保留 Fortran 版本或早期 Python
版本的习惯写法。

在仓库根目录使用已安装依赖的 Python 解释器。例如 Windows 项目虚拟环境中的 CLI 入口是：

```powershell
.\.venv\Scripts\python.exe -m nspa.main --config inputs\configs\nspa2023S0.cfg --step all
```

如果不传 `--config`，当前代码里的默认配置文件是
`inputs/configs/nspa2023S0.cfg`。

## 快速模板

下面是一份单目标、完整 5 步运行的最小可用模板。路径可以写相对路径或绝对路径。

```ini
# 01pre
1fitspath=inputs/images/S9/2024/202411
1superflag=1
1median_impl=auto
1med_length=65
1med_width=1
1bkgdmode=2
1enhance_flag=1

# 02detect
2bkgd_threshold=5.0
2snr_threshold=1.0
2pos_method=1
2connectivity=fortran
2detect_workers=0

# 03match
3tele_label=km100B
3tele_focal=13300.0
3ccd_scale=0.0135
3ccd_fieldsize=15
3modeltype=6
3plate_angle=180.0
3obj_ephsource=IMCCE
3gaia_minmag=5.0
3gaia_maxmag=18.5
3match_limit=5.0
3delta_T=0.0
3obj_total=1
3gaia_catfile1=inputs/catalogs/S9/2024/GAIA3_S9_202410.DAT
3obj_ephfile1=inputs/catalogs/S9/2024/EPH_S9_202411.DAT

# 04comoc
4specified-output=outputs/results/S9/2024
4eps=0.2
4std_limit=2.6
4mean_limit=0
4del_flag=0

# 05report
5sat_prefix=U
```

## 基本语法

- 配置格式是 `key=value`，等号前后空格不敏感。
- 空行会被忽略。
- 以 `!`、`;`、`#`、`[` 开头的行会被当作注释。
- 行内 `%` 之后的内容会被当作注释。
- 字符串路径里的反斜杠会按当前系统分隔符转换，Windows 风格路径可以被解析。
- 不能解析的数值字段会保留默认值，并在日志里打印警告。
- 未出现的字段使用代码默认值。

键名前缀对应流水线阶段：

| 前缀 | 阶段 | 模块 | 主要产物 |
|---|---|---|---|
| `1` | `pre` | 超级背景预处理 | `fits_n/*_n.fit` |
| `2` | `detect` | 星象检测 | `fits_reg/*.fit.reg` |
| `3` | `match` | 星象匹配归算 | `fits_ref/*.ref.reg`, `fits_out/object_N.out` |
| `4` | `comoc` | O-C 统计和野值剔除 | `.dat`, `final_*`, `00oc_*.out` |
| `5` | `report` | O-C 图报告 | `OC_summary.png`, `OC_<prefix>N.png` |

## 路径展开规则

`1fitspath` 决定输入观测图目录。程序支持三种写法：

1. 直接指向某个观测日的 `fits` 目录：

   ```ini
   1fitspath=inputs/images/S9/2024/202411/20241103/fits
   ```

2. 指向包含多个日期目录的上级目录，程序会自动展开其中的 `YYYYMMDD/fits` 或
   `YYYYMMDD/FITS`：

   ```ini
   1fitspath=inputs/images/S9/2024/202411
   ```

3. 多个观测目录可以用数字后缀追加：

   ```ini
   1fitspath=inputs/images/S9/2024/202411
   1fitspath2=inputs/images/S9/2024/202412
   1fitspath3=/absolute/path/to/another/fits
   ```

每个观测日目录的阶段产物会写到原始 `fits` 的兄弟目录：

```text
<YYYYMMDD>/
├── fits/       # 原始 FITS 输入
├── fits_n/     # 01pre 输出
├── fits_reg/   # 02detect 输出
├── fits_ref/   # 03match 参考星输出
└── fits_out/   # 03match / 04comoc 日内输出
```

跨日汇总结果由 `4specified-output` 指定，例如：

```ini
4specified-output=outputs/results/S9/2024
```

## 配置校验规则

程序启动时会按本次 `--step` 做配置校验。

所有运行都会检查：

- 至少配置一个 `1fitspath`。
- `1superflag` 必须是 `0`、`1`、`2`、`3`。
- `1median_impl` 必须是 `auto`、`scipy`、`scipy_threaded`、`bottleneck`。
- `2connectivity` 必须是 `fortran` 或 `scipy`。
- `2detect_workers` 必须是非负整数。

运行 `match`、`comoc`、`report` 或 `all` 时还会检查：

- `3obj_total` 必须大于 0。

运行 `match` 或 `all` 时还会检查：

- `3obj_total` 必须等于 `3obj_ephfile*` 的数量。
- `3modeltype` 必须是 `6`、`12`、`20`、`30`。
- 必须配置 `3gaia_catfile1`，且文件存在。
- 所有 `3obj_ephfile*` 都必须存在。

运行 `comoc`、`report` 或 `all` 时还会检查：

- 必须配置 `4specified-output`。

## 01pre: 预处理配置

| 键 | 类型 | 默认值 | 取值 | 说明 |
|---|---:|---:|---|---|
| `1fitspath` | path list | 无 | 路径 | 观测图输入路径。必填，可追加 `1fitspath2`、`1fitspath3`。 |
| `1biasflag` | int | `0` | `0/1` | 当前解析但未实际参与 Python 预处理流程。保留给兼容旧 cfg。 |
| `1darkflag` | int | `0` | `0/1` | 当前解析但未实际参与 Python 预处理流程。 |
| `1flatflag` | int | `0` | `0/1` | 当前解析但未实际参与 Python 预处理流程。 |
| `1superflag` | int | `0` | `0/1/2/3` | 预处理模式。`0` 跳过，`1` 中值滤波超级背景，`2` 同态滤波，`3` BSSR/Retinex。 |
| `1median_impl` | str | `auto` | `auto/scipy/scipy_threaded/bottleneck` | `superflag=1` 时的中值滤波实现选择。 |
| `1pre_workers` | int | `0` | 非负整数 | 预处理文件并行数上限。`1` 串行，`0` 自动（最多 2 个进程），`>1` 显式指定上限。内存不足时用 `1`。 |
| `1med_length` | int | `1` | 正整数 | 中值窗口长度。和 `1med_width` 共同决定滤波核。代码不单独校验正数，非法值会在滤波阶段报错。 |
| `1med_width` | int | `25` | 正整数 | 中值窗口宽度。代码不单独校验正数，非法值会在滤波阶段报错。 |
| `1bkgdmode` | int | `2` | `1/2` | 背景扣除模式。`1` 除法归一化，`2` 减法扣除。 |
| `1enhance_flag` | int | `1` | `0/1` | `1` 表示中值滤波后再做一次 3x3 均值滤波。 |
| `1homo_gauss_cutoff` | float | `50.0` | 正数 | `superflag=2` 同态滤波的频域高斯截止频率。 |
| `1bssr_gauss_size` | int | `9` | 正整数 | `superflag=3` BSSR/Retinex 后的 GaussianBlur 窗口。偶数会自动加 1，非正会回退到 1。 |

### superflag

`1superflag=0` 时跳过预处理，`detect` 会直接读取原始 `fits/*.fit`。

`1superflag=1` 是当前主力模式。流程是：

1. 读取原始 FITS。
2. 计算全图背景和 sigma。
3. 按中值背景做除法或减法扣除。
4. 如 `1enhance_flag=1`，再做 3x3 均值滤波。
5. 输出到 `fits_n/*_n.fit`。

中值滤波结果会按 uint16 方式写出，保留历史 Fortran 对无符号 16 位 FITS 的回绕行为。
这是为了避免饱和亮星区域在浮点写出时产生和 Fortran 不一致的大残差。

`1superflag=2` 使用同态滤波，`1homo_gauss_cutoff` 控制高斯高通截止频率。

`1superflag=3` 使用双边 Retinex，然后用 `1bssr_gauss_size` 控制空间高斯平滑窗口。

### median_impl

| 值 | 行为 | 适用场景 |
|---|---|---|
| `auto` | 带状核走 `bottleneck`，非带状核选择 `scipy_threaded` | 推荐默认值。 |
| `bottleneck` | 使用 `bottleneck.move_median` 做一维移动中值 | `1med_length=1` 或 `1med_width=1` 的带状核最快。 |
| `scipy_threaded` | 带状核沿正交方向切块，多线程调用 `scipy.ndimage.median_filter`；非带状核会退化为单次 scipy median_filter | 想避免 bottleneck 差异时使用。 |
| `scipy` | 单线程 `scipy.ndimage.median_filter` | 最保守，通常用于排查问题。 |

并行层次：

- 文件级并行：默认 `1pre_workers=1`，逐个处理 FITS，降低峰值内存。设置为 `0` 时最多并行 2 个文件；设置大于 1 的值可手动提高上限。
- 滤波内部并行：仅 `median_impl=scipy_threaded` 且文件级并行时会分配内部线程，每个进程最多 4 个线程。

## 02detect: 星象检测配置

| 键 | 类型 | 默认值 | 取值 | 说明 |
|---|---:|---:|---|---|
| `2bkgd_threshold` | float | `5.0` | 正数 | 检测阈值系数。阈值为 `background + factor * sigma`。越大检测星越少。 |
| `2snr_threshold` | float | `5.0` | 数值 | `.reg` 输出过滤阈值。只输出 `snr > 2snr_threshold` 的星象。 |
| `2pos_method` | int | `2` | `1/2/3/...` | 星象中心定位的修正矩阶数。`1` 是一阶权重，`2`、`3` 会提高亮像素权重。 |
| `2connectivity` | str | `fortran` | `fortran/scipy` | 连通域标号算法。 |
| `2detect_workers` | int | `0` | 非负整数 | detect 文件级并行度。`0` 自动，`1` 串行，`>1` 指定上限。 |

### connectivity

`fortran` 是默认值，复刻原 Fortran 的三段式连通域逻辑，并保留 `nr=250` 的局部合并行为。
numba 可用时会走 JIT 加速；numba 不可用时回退 Python/numpy 实现。

`scipy` 使用标准 8 连通标号，内部是更常规的 Union-Find 语义。它不包含 Fortran 的
`nr=250` 局部合并细节，在极少数复杂形状下可能比 Fortran 路径更稳健，但输出不一定和
历史 Fortran 完全一致。

### detect_workers

`2detect_workers=0` 是当前推荐提速状态：

```ini
2detect_workers=0
```

程序自动使用最多 2 个进程，并按图像尺寸及当前可用内存进一步降低并发数。显式指定的上限也受内存预算约束。为了稳定性，detect 阶段仍会先进入一个全新的
`spawn` 子进程隔离 numba，再在这个隔离进程内部按 FITS 文件并行。

排查问题时可以强制串行：

```ini
2detect_workers=1
```

希望限制资源占用时可以指定上限：

```ini
2detect_workers=4
```

## 03match: 匹配归算配置

| 键 | 类型 | 默认值 | 取值 | 说明 |
|---|---:|---:|---|---|
| `3tele_label` | str | `""` | `ss156/ss156_2014/km100/km100B/km100c/lj240` | 望远镜头文件格式标签。 |
| `3tele_focal` | float | `0.0` | 正数 | 望远镜焦距，单位 mm。 |
| `3ccd_scale` | float | `0.0` | 正数 | CCD 像素尺寸，单位 mm。 |
| `3ccd_fieldsize` | int | `0` | 正数 | 视场半宽，单位 arcmin。用于筛选参考星范围。 |
| `3modeltype` | int | `0` | `6/12/20/30` | 底片常数模型项数。 |
| `3plate_angle` | float | `0.0` | 角度 | 底片旋转角初值，单位度。 |
| `3obj_ephsource` | str | `""` | 通常 `IMCCE` | 历表来源标签，当前主要作为配置记录。 |
| `3gaia_minmag` | float | `0.0` | 星等 | GAIA 参考星最亮星等下限。 |
| `3gaia_maxmag` | float | `0.0` | 星等 | GAIA 参考星最暗星等上限。 |
| `3match_limit` | float | `0.0` | 正数 | 匹配距离阈值，单位 arcsec。 |
| `3delta_T` | float | `0.0` | 秒 | FITS 头时间补偿。一般不用。 |
| `3obj_total` | int | `0` | 正整数 | 本次归算目标数量。必须等于 `3obj_ephfile*` 数量。 |
| `3gaia_catfile1` | path | `""` | 文件路径 | GAIA 星表路径。当前解析时多目标会共用第一个 GAIA 文件。 |
| `3obj_ephfileN` | path list | `[]` | 文件路径 | 第 N 个目标的历表路径。 |

### 望远镜标签

当前 FITS 头解析支持以下标签：

| 标签 | 时间字段/行为 |
|---|---|
| `ss156` | 使用 `DATE-OBS`，并从北京时间修正到 UTC。 |
| `ss156_2014` | 使用 `DATE-STA`，并从北京时间修正到 UTC。 |
| `km100` | 使用 `DATE-OBS`。 |
| `km100B` | 使用 `DATE-OBS`。 |
| `km100c` | 使用 `FRAME` 和 `EXPOSURE`，保留小数秒并计算曝光中点。 |
| `lj240` | 使用 `DATE-OBS`。 |

如果新望远镜的 FITS 头时间格式不同，需要先扩展 `read_fits_header` 的解析逻辑。

### 底片模型

底片常数使用列缩放后的 SVD 最小二乘求解，避免对正规矩阵直接求逆。参考星必须多于模型每个坐标的参数数目（6/12/20/30 参数模型至少需要 4/7/11/16 颗），并具备足够的二维分布。缩放矩阵奇异值比低于 `1e-10` 时拒绝该候选解；实际应使用更多分布均匀的参考星。

`3modeltype` 控制底片常数模型复杂度：

| 值 | 含义 | 建议 |
|---:|---|---|
| `6` | 线性模型 | 小视场、参考星数量不多时优先使用。 |
| `12` | 二阶多项式 | 视场畸变明显且参考星较多时使用。 |
| `20` | 三阶多项式 | 更复杂畸变，需更多稳定匹配星。 |
| `30` | 更高项模型 | 代码允许，但部分矢量快路径会回退逐点计算。谨慎使用。 |

匹配阶段现在默认走 KDTree 快路径。快路径异常或匹配不足时会自动回退暴力路径，
因此配置中没有专门的 KDTree 开关。

### 多目标写法

`3obj_total` 必须和 `3obj_ephfile*` 数量一致：

```ini
3obj_total=3
3obj_ephfile1=inputs/catalogs/S/2023/EPH_S1_202311.DAT
3obj_ephfile2=inputs/catalogs/S/2023/EPH_S2_202311.DAT
3obj_ephfile3=inputs/catalogs/S/2023/EPH_S3_202311.DAT
3gaia_catfile1=inputs/catalogs/S/2023/GAIA3_S_202311.DAT
```

虽然旧 cfg 中常写 `3gaia_catfile2`、`3gaia_catfile3`，当前 Python 解析会把
`3gaia_catfile*` 折叠为第一个值，表示多目标共用同一份 GAIA 星表。

## 04comoc: O-C 统计配置

| 键 | 类型 | 默认值 | 取值 | 说明 |
|---|---:|---:|---|---|
| `4specified-output` | path | `""` | 目录 | 跨日汇总输出目录。运行 `comoc/report/all` 必填。 |
| `4eps` | float | `0.0` | 非负数 | sigma 模式下的残差绝对值硬阈值，单位 arcsec。`abs(residual) >= eps` 会被剔除。 |
| `4std_limit` | float | `0.0` | 非负数 | sigma-clipping 倍数。`>0` 时使用 sigma 模式。 |
| `4mean_limit` | float | `0.0` | 非负数 | `4std_limit=0` 时启用的均值偏差阈值。 |
| `4del_flag` | int | `0` | `0/1` | `1` 会删除 `fits_n`、`fits_reg`、`fits_ref` 里的过程文件。 |

### 野值剔除逻辑

`4std_limit > 0` 时使用 sigma 模式。代码在这个模式下同时使用 `4eps`：

```text
保留 abs(res_ra - mean_ra) < std_limit * std_ra
并且 abs(res_de - mean_de) < std_limit * std_de
并且 abs(residual) < eps
```

如果使用 sigma 模式，`4eps` 不能保持默认 `0.0`，否则 `abs(residual) < eps`
几乎不会保留任何非零残差。常见配置会把 `4eps` 设为 `0.2`、`0.5`、`10.0`
这类正数，具体取决于数据质量和目标。

`4std_limit = 0` 时使用 mean-limit 模式。按当前代码，这个模式不使用 `4eps`：

```text
保留 abs(res_ra - mean_ra) < mean_limit
并且 abs(res_de - mean_de) < mean_limit
```

注意：`eps` 是硬阈值。即使某个点通过 sigma 或 mean-limit 检查，只要绝对残差不小于
`eps`，也会被剔除。

### 输出门槛

剔除后，只有当以下条件同时满足时，当日数据才会写入最终 `.dat`：

- 剔除后样本数大于 1。
- `std_ra < 0.3` arcsec。
- `std_de < 0.3` arcsec。

否则该日期会被记录为精度不达标，并不会进入最终月度 `.dat`。

### del_flag

`4del_flag=1` 会删除过程文件：

- `fits_n/*`
- `fits_reg/*`
- `fits_ref/*`

它不会删除原始 `fits/`，也不会删除 `fits_out/` 和 `4specified-output` 下的最终汇总结果。
日常调试建议保持 `0`，确认结果后再按需打开。

## 05report: 报告配置

| 键 | 类型 | 默认值 | 取值 | 说明 |
|---|---:|---:|---|---|
| `5sat_prefix` | str | `S` | 任意短字符串 | 报告图例和单目标图片名的目标前缀。 |

完整流水线只读取本次 comoc 生成的 `run_<run_id>_<目标编号>.dat`。单独运行 report 时，才扫描 `4specified-output` 下的 `*N.dat` 文件。输出如下：

```text
OC_summary.png
OC_<sat_prefix>1.png
OC_<sat_prefix>2.png
...
```

例如：

```ini
5sat_prefix=U
```

历表文件名能解析出目标代号时，优先生成 `OC_<实际代号>.png`（例如 `OC_N0.png`）；只有无法解析时才使用 `5sat_prefix` 加编号。

`ReportConfig` 中还有 `per_satellite=True` 默认值，但当前 cfg 文件没有对应键。
如需关闭单目标图，需要通过代码层配置，而不是 cfg。

report 发现 `.dat` 文件的规则来自 `nspa/core/reporter.py`：只读取文件名 stem
末尾一位数字作为目标编号，例如 `fits1.dat`、`202411031.dat`、`S9_2024_1.dat`
都能归到目标 1。当前规则只看末尾一位数字，因此目标数超过 9 时需要先调整
report 的文件发现逻辑。

## 提速相关配置建议

当前默认推荐是：

```ini
1median_impl=auto
1pre_workers=0
2detect_workers=0
```

含义：

- 预处理带状中值走 `bottleneck`，非带状中值走多线程 scipy。
- 预处理按 FITS 文件并行。
- detect 先隔离 numba，再按 FITS 文件并行。
- match 默认使用 KDTree 快路径，失败自动回退暴力路径。

需要排查稳定性时可逐步降级：

```ini
# 只让 detect 串行，保留其他提速
2detect_workers=1

# 让中值滤波走最保守 scipy 路径
1median_impl=scipy
```

如果只想限制资源占用，不想完全串行：

```ini
2detect_workers=4
```

## 按阶段运行时的最少配置

`--step pre` 至少需要：

```ini
1fitspath=...
1superflag=1
```

`--step detect` 至少需要：

```ini
1fitspath=...
1superflag=0        # 读原始 fits
# 或 1superflag=1 并确保 fits_n 已由 pre 生成
```

`--step match` 至少需要：

```ini
1fitspath=...
3tele_label=...
3tele_focal=...
3ccd_scale=...
3ccd_fieldsize=...
3modeltype=6
3obj_total=1
3gaia_catfile1=...
3obj_ephfile1=...
```

`--step comoc` 至少需要：

```ini
1fitspath=...
3obj_total=1
4specified-output=...
```

`comoc` 生成月度 `.dat` 的文件名来自第一个展开后的 `fitspath` 的目录名加目标编号。
如果 `fitspath` 是某个 `.../fits` 目录，月度文件名会是 `fits1.dat`；
如果输入展开出来的目录名不同，输出文件名前缀也会跟着变化。

`--step report` 至少需要：

```ini
1fitspath=...
3obj_total=1
4specified-output=...
```

## 常见问题

### 1. 配置了多个 GAIA 文件，为什么实际只用第一个？

当前解析逻辑会把 `3gaia_catfile*` 折叠成一个值，只取下标最小的那个。历史上多目标共用同一
GAIA 星表，所以这是有意兼容。多目标只需要写 `3gaia_catfile1`。

### 2. `biasflag/darkflag/flatflag` 现在有效吗？

当前 Python 流水线解析这些字段，但实际预处理代码没有使用它们。真正决定预处理路径的是
`1superflag`。

### 3. detect 是否现在默认就是提速状态？

是。`2detect_workers` 默认是 `0`，表示自动并行。要回到 detect 串行，显式写：

```ini
2detect_workers=1
```

### 4. `1median_impl=auto` 和 `bottleneck` 结果会不会和 `scipy` 完全一致？

带状核内部像素应保持一致；边界处由于 reflect 语义可能有极小差异。完整流水线用 golden test
锁定当前基线。如果要排查数值差异，可以临时设为：

```ini
1median_impl=scipy
```

### 5. 为什么 sigma 模式下 `4eps` 不能随便设得太小？

当 `4std_limit > 0` 时，`4eps` 是硬阈值。设得太小会把本来通过 sigma 剔除的正常点也删除，
导致样本数不足或整日数据不写入 `.dat`。当 `4std_limit = 0` 时，当前代码的 mean-limit
模式不使用 `4eps`。

### 6. 输出图叫 `OC_S1.png` 还是 `OC_U1.png`？

由 `5sat_prefix` 决定。默认是 `S`。想输出 Uranus 卫星习惯名时写：

```ini
5sat_prefix=U
```

### 7. 修改 cfg 后如何验证？

先确认启动解释器有运行依赖、命令行入口可用：

```powershell
.\.venv\Scripts\python.exe -c "import cv2, astropy; print('依赖可用')"
.\.venv\Scripts\python.exe -m nspa.main --help
```

正式运行前，核对 `1fitspath`、GAIA 星表、目标历表和 `4specified-output` 是否指向本次数据。
运行 `pre` 会替换旧的 `fits_n/*_n.fit`，设置 `4del_flag=1` 还会清理过程文件。
运行后根据日志和 `outputs/runs/<run_id>/manifest.json` 核对每个阶段的警告、失败项与产物。
