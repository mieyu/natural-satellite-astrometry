# ADIAS 顶层接口：导出 5 步流程入口与配置解析。

from adias.config import parse_config
from adias.core.analyzer import run_comoc
from adias.core.detector import run_detect
from adias.core.matcher import run_match
from adias.core.preprocessor import run_pre
from adias.core.reporter import run_report
from adias.paths import expand_fitspath

__all__ = [
    "parse_config",
    "expand_fitspath",
    "run_pre",
    "run_detect",
    "run_match",
    "run_comoc",
    "run_report",
]
