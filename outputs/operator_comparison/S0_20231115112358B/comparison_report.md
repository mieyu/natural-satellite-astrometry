# 当前算子与 DrizzlePac 对比

| 项目 | 当前 ADIAS 算子 | DrizzlePac |
|---|---:|---:|
| 初始检测 | 16 | 136 |
| 最终输出 | 15 | 2 |
| 当前最终星表与 DrizzlePac 候选重合（3 px） | 7 | - |
| 两边最终星表重合（3 px） | 1 | 1 |

共同星点的质心距离：0.0398 px。

当前方法使用 45×1、1×45 中值背景扣除、3×3 均值平滑、连通域和一次修正矩；DrizzlePac 使用高斯卷积、DAOFIND 式质心以及 sharpness/roundness 筛选。
