"""ADIAS 分层错误类型。"""


class AdiasError(Exception):
    """ADIAS 基础异常。"""


class ConfigError(AdiasError):
    """配置错误；启动阶段直接失败。"""


class DataFormatError(AdiasError):
    """输入或中间文件格式错误。"""


class ProcessingError(AdiasError):
    """单个处理项失败但流水线可继续的处理错误。"""
