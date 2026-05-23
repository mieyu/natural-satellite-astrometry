"""ADIAS 顶层接口。

只暴露轻量入口：配置解析与观测目录展开。算法 run_* 通过 adias.core.*
显式导入即可，不在顶层 re-export，避免诱导用户绕开 PipelineRunner 的
配置校验与运行 manifest。
"""

from adias.config import AdiasConfig, load_config, parse_config
from adias.paths import ObservationDir, expand_fitspath

__all__ = [
    "AdiasConfig",
    "ObservationDir",
    "expand_fitspath",
    "load_config",
    "parse_config",
]
