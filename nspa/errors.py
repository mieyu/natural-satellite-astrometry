"""NSPA 分层异常类型。"""


class NspaError(Exception):
    """NSPA 基础异常。"""


class ConfigError(NspaError):
    """配置错误；启动阶段直接失败。"""


class DataFormatError(NspaError):
    """输入或中间文件格式错误。"""


class ProcessingError(NspaError):
    """单个处理项失败但流水线可继续的处理错误。"""
