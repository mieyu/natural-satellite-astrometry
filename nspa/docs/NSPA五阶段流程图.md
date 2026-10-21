# ADIAS 五阶段流程图

[项目首页](../../README.md) · [文档导航](../../docs/README.md)

本文按当前 Python 程序说明从原始 FITS 图像到 O−C 报告的处理路径。`N` 表示目标编号，`<观测日>` 表示包含 `fits/` 的日期目录。

## 总览

```mermaid
flowchart LR
    A["原始 FITS 图像"] --> B["01 pre：预处理"]
    B --> C["02 detect：检测星象"]
    A -->|"superflag=0 时使用原图"| C
    C --> D["03 match：位置归算"]
    G["GAIA 参考星表"] --> D
    H["目标历表"] --> D
    D --> E["04 comoc：O−C 统计"]
    E --> F["05 report：绘图"]
```

程序先读取并校验配置，将 `1fitspath` 展开为逐日 `fits/` 目录。单独运行某一阶段时，程序不会自动生成前面阶段所需的文件。

## 01 pre：图像预处理

**输入：** `<观测日>/fits/*.fit` 或 `*.fits`。  
**输出：** `<观测日>/fits_n/*_n.fit`。

```mermaid
flowchart TD
    A["扫描原始 FITS"] --> B{"1superflag"}
    B -->|"0"| C["跳过预处理；detect 读取原图"]
    B -->|"1"| D["中值滤波估计背景"]
    B -->|"2"| E["同态滤波"]
    B -->|"3"| F["Retinex 处理"]
    D --> G["去除或归一化背景；可选均值平滑"]
    E --> H["写入 fits_n 中的处理后 FITS"]
    F --> H
    G --> H
```

`1med_length`、`1med_width`、`1bkgdmode`、`1enhance_flag` 主要影响模式 `1`；`1homo_gauss_cutoff` 只影响模式 `2`。重新运行非零预处理模式时，程序会先清理该观测日 `fits_n/` 中旧的 `_n.fit`、`_n.fits` 文件。

## 02 detect：星象检测

**输入：** 预处理后的 FITS；当 `1superflag=0` 时使用原图。  
**输出：** `<观测日>/fits_reg/*.fit.reg` 或 `*.fits.reg`。

```mermaid
flowchart TD
    A["读取图像像素"] --> B["估计背景均值 B 和噪声 σ"]
    B --> C["以 B + 2bkgd_threshold × σ 分割亮像素"]
    C --> D["相邻亮像素合并为候选星象"]
    D --> E["计算中心、亮度、像素数和 SNR"]
    E --> F{"满足筛选条件？"}
    F -->|"是"| G["写入 DS9 region 星表"]
    F -->|"否"| H["舍弃候选"]
```

`2connectivity` 选择连通域算法，`2pos_method` 控制中心定位的权重，`2snr_threshold` 控制输出筛选，`2detect_workers` 控制文件级并行。此阶段得到的是图像中的像素位置。

## 03 match：参考星匹配与目标位置归算

**输入：** 检测星表、原图 Header、GAIA 参考星表和目标历表。  
**输出：** `<观测日>/fits_ref/*.ref.reg` 与 `<观测日>/fits_out/object_N.out`。

```mermaid
flowchart TD
    A["从 FITS Header 读取观测时间"] --> D["插值目标历表，得到预测赤经和赤纬"]
    B["读取检测星的像素位置"] --> E["与 GAIA 参考星匹配"]
    C["读取 GAIA 星表"] --> E
    D --> E
    E --> F["求像素到天空坐标的底片常数"]
    F --> G["将目标历表位置反算为预测像素位置"]
    D --> G
    G --> H{"3 像素范围内找到目标？"}
    H -->|"是"| I["将目标实际像素位置换算为观测赤经和赤纬"]
    I --> J["写参考星及目标观测结果"]
    H -->|"否"| K["记录该图像或目标匹配失败"]
```

GAIA 星表用于建立图像坐标与天空坐标的对应关系；目标历表给出同一观测时刻的预测位置，也用于寻找图中的目标。`3tele_focal`、`3ccd_scale` 是仪器参数，`3modeltype` 控制底片常数模型，`3match_limit` 控制参考星匹配距离。

## 04 comoc：O−C 统计与离群值剔除

**输入：** 每个观测日的 `fits_out/object_N.out`。  
**输出：** 逐日 `final_*` 文件，以及 `4specified-output` 目录中的跨日 `.dat` 和统计文件。

```mermaid
flowchart TD
    A["读取目标观测结果"] --> B["计算观测位置减历表位置的 O−C"]
    B --> C["分别统计赤经、赤纬残差的均值和标准差"]
    C --> D["按 4std_limit 或 4mean_limit 迭代剔除离群值"]
    D --> E["重算保留样本的统计量"]
    E --> F{"样本数大于 1，且两个方向标准差都小于 0.3 角秒？"}
    F -->|"是"| G["写逐日结果并加入跨日 .dat"]
    F -->|"否"| H["记录该日未纳入跨日汇总"]
```

当 `4std_limit>0` 时，保留数据还须同时满足赤经和赤纬绝对残差均小于 `4eps`。`4del_flag=1` 会删除 `fits_n/`、`fits_reg/`、`fits_ref/` 中的过程文件；`0` 不执行这项清理。

## 05 report：生成 O−C 图

**输入：** 本次 comoc 生成的非空跨日 `.dat`；单独运行 report 时扫描 `4specified-output`。  
**输出：** `OC_summary.png`，以及启用时的单目标 `OC_<历表目标代号>.png`（无法解析代号时使用前缀和编号）。

```mermaid
flowchart TD
    A["读取本次跨日 .dat 文件"] --> B{"存在有效观测记录？"}
    B -->|"否"| C["记录警告，跳过绘图"]
    B -->|"是"| D["按观测年月和目标编号分组"]
    D --> E["以 UTC 观测时间为横轴，绘制赤经和赤纬 O−C"]
    E --> F["保存 OC_summary.png"]
    F --> G{"启用单目标图？"}
    G -->|"是"| H["保存各目标图片"]
    G -->|"否"| I["完成"]
    H --> I
```

图中的点表示实测位置与历表预测位置之差随时间的变化。更详细的处理条件和产物说明见[五阶段运行流程详解](NSPA五阶段运行流程详解.md)，参数取值见[配置说明](configuration.md)。
