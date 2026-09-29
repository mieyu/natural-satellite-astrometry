"""NSPA 顶层接口。

只暴露轻量入口：配置解析与观测目录展开。算法 run_* 通过 nspa.core.*
显式导入即可，不在顶层 re-export，避免诱导用户绕开 PipelineRunner 的
配置校验与运行 manifest。
"""

from nspa.config import NspaConfig, load_config, parse_config
from nspa.paths import ObservationDir, expand_fitspath

__all__ = [
    "NspaConfig",
    "ObservationDir",
    "expand_fitspath",
    "load_config",
    "parse_config",
]
