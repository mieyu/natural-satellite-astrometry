"""统一日志：同时写 stdout 与控制台输出日志文件。

格式上只输出消息本体，保留与历史 print 完全等价的字面行——下游脚本与
golden 比对依赖这些行的原样落地。
"""

import logging
import sys
from pathlib import Path

LOGGER_NAME = "nspa"
_DEFAULT_LOG_FILE = "控制台输出.txt"


def get_logger(name: str | None = None) -> logging.Logger:
    """获取 NSPA 子 logger；未传 name 时返回包根 logger。"""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def setup_logging(log_file: str | Path = _DEFAULT_LOG_FILE) -> logging.Logger:
    """在 stdout 与日志文件上都挂一份 INFO handler；重复调用幂等。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 清掉旧 handler，便于反复初始化（如测试间）
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    fmt = logging.Formatter("%(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def teardown_logging() -> None:
    """关闭并卸载 nspa logger 上的所有 handler。"""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
