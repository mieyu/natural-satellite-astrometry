"""控制台输出与控制台输出.txt 的统一 tee。"""

import sys


class OutputSink:
    """同时写 stdout 与日志文件；兼容既有 print 输出。"""

    def __init__(self, file_path="控制台输出.txt"):
        self.file_path = file_path
        self._stdout = None
        self._file = None

    def install(self):
        if self._file is not None:
            return self
        self._stdout = sys.stdout
        self._file = open(self.file_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = self
        return self

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def write_line(self, text=""):
        self.write(f"{text}\n")

    def close(self):
        if self._file is None:
            return
        sys.stdout = self._stdout
        self._file.close()
        self._file = None
        self._stdout = None

    def __enter__(self):
        return self.install()

    def __exit__(self, exc_type, exc, tb):
        self.close()
