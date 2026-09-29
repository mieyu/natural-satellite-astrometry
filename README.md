# NSPA — Natural Satellite Precision Astrometry Software

**天然卫星精密天体测量软件**  
英文名称：Natural Satellite Precision Astrometry Software  
缩写：NSPA

## 软件介绍

本软件面向太阳系各类天然卫星观测任务，集成完整天体测量数据处理流程。依托望远镜与空间载荷原始观测图像，完成标准化图像校正、噪声剔除与几何畸变修正；结合 GAIA 星表实现星点检测、PSF 拟合、参考星匹配与 WCS 天球坐标解算。

针对天然卫星延展目标，支持多算法质心定位，自适应卫星不同相位与光照形态，输出高精度天球坐标。软件依托 IMCCE 和 JPL 天然卫星星历模型，实现实测位置与理论轨道比对及残差分析，支持多历元观测数据结构化管理与归档，为天然卫星高精度天体测量与轨道动力学研究提供核心数据支撑。

## 使用说明

- [处理流程与命令行使用说明](nspa/README.md)
- [桌面界面使用说明](ui/README.md)
- [依赖清单](requirements.txt)
- [处理结果](outputs/results/)

Python 包名为 `nspa`，从项目根目录启动：

```bash
python -m nspa.main
```
