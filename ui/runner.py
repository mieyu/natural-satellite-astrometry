"""子进程运行器：调用现有入口 `python -m nspa.main`，流式回传 stdout。

不 import nspa 进程内跑——完全不碰现有代码，且崩溃不拖垮 UI。
后台线程读 stdout 入队，主线程（Tk）轮询取行刷新日志。
"""

import queue
import subprocess
import sys
import threading


class PipelineRunner:
    def __init__(self):
        self.proc = None
        self.queue = queue.Queue()
        self._thread = None
        self._done = False
        self.returncode = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, cfg_path, step, cwd):
        """启动子进程：python -m nspa.main --config <cfg> --step <step>。"""
        self._done = False
        self.returncode = None
        cmd = [sys.executable, "-m", "nspa.main",
               "--config", str(cfg_path), "--step", str(step)]
        self.queue.put(f"$ {' '.join(cmd)}  (cwd={cwd})")
        self.proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        for line in self.proc.stdout:
            self.queue.put(line.rstrip("\n"))
        self.proc.wait()
        self.returncode = self.proc.returncode
        self._done = True

    def poll_lines(self):
        """非阻塞取出当前已到达的所有日志行。"""
        out = []
        try:
            while True:
                out.append(self.queue.get_nowait())
        except queue.Empty:
            pass
        return out

    @property
    def finished(self):
        return self._done and self.queue.empty()
