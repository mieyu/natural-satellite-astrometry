"""ADIAS 顶层接口。

配置与路径模型保持轻量导入；计算入口通过 __getattr__ 懒加载，避免导入
adias.config 时强制加载 numpy/scipy/astropy 等算法依赖。
"""

from adias.config import AdiasConfig, load_config, parse_config
from adias.paths import ObservationDir, expand_fitspath

__all__ = [
    "AdiasConfig",
    "parse_config",
    "load_config",
    "expand_fitspath",
    "ObservationDir",
    "run_pre",
    "run_detect",
    "run_match",
    "run_comoc",
    "run_report",
]


def __getattr__(name):
    if name == "run_pre":
        from adias.core.preprocessor import run_pre

        return run_pre
    if name == "run_detect":
        from adias.core.detector import run_detect

        return run_detect
    if name == "run_match":
        from adias.core.matcher import run_match

        return run_match
    if name == "run_comoc":
        from adias.core.analyzer import run_comoc

        return run_comoc
    if name == "run_report":
        from adias.core.reporter import run_report

        return run_report
    raise AttributeError(f"module 'adias' has no attribute {name!r}")
