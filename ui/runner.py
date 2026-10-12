"""子进程运行器：调用现有入口 `python -m nspa.main`，流式回传 stdout。

不 import nspa 进程内跑——完全不碰现有代码，且崩溃不拖垮 UI。
后台线程读 stdout 入队，主线程（Tk）轮询取行刷新日志。
"""

import os
import queue
import signal
import subprocess
import sys
import threading

import psutil


class PipelineRunner:
    def __init__(self):
        self.proc = None
        self.queue = queue.Queue()
        self._thread = None
        self._stop_thread = None
        self._transition_thread = None
        self._state_lock = threading.Lock()
        self.transition = None
        self.paused = False
        self._suspended_processes = []
        self._done = False
        self.returncode = None
        self.stopped_by_user = False

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, cfg_path, step, cwd):
        """启动子进程：python -m nspa.main --config <cfg> --step <step>。"""
        if self.proc is not None and self.proc.poll() is None:
            raise RuntimeError("流水线仍在运行")
        self.queue = queue.Queue()
        self._stop_thread = None
        self._transition_thread = None
        self.transition = None
        self.paused = False
        self._suspended_processes = []
        self._done = False
        self.returncode = None
        self.stopped_by_user = False
        cmd = [sys.executable, "-m", "nspa.main",
               "--config", str(cfg_path), "--step", str(step)]
        self.queue.put(f"$ {' '.join(cmd)}  (cwd={cwd})")
        self.proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            start_new_session=(os.name != "nt"),
        )
        self._thread = threading.Thread(target=self._pump, args=(self.proc,), daemon=True)
        self._thread.start()

    def stop(self):
        """异步中止流水线，连同 detect 等阶段启动的子进程。"""
        proc = self.proc
        if proc is None or proc.poll() is not None or self.stopped_by_user:
            return False
        with self._state_lock:
            self.stopped_by_user = True
        self._stop_thread = threading.Thread(target=self._stop_tree, args=(proc,), daemon=True)
        self._stop_thread.start()
        return True

    def pause(self):
        """异步暂停流水线进程及其子进程。"""
        return self._start_transition("pausing")

    def resume(self):
        """异步继续被暂停的流水线。"""
        return self._start_transition("resuming")

    def _start_transition(self, action):
        with self._state_lock:
            if (self.proc is None or self.proc.poll() is not None
                    or self.stopped_by_user or self.transition is not None
                    or self.paused != (action == "resuming")):
                return False
            self.transition = action
            self._transition_thread = threading.Thread(
                target=self._change_pause_state, args=(action, self.proc), daemon=True)
            self._transition_thread.start()
        return True

    def _change_pause_state(self, action, proc):
        try:
            if os.name == "nt":
                if action == "pausing":
                    self._suspend_windows_tree(proc)
                else:
                    self._resume_windows_tree()
            else:
                os.killpg(proc.pid, signal.SIGSTOP if action == "pausing" else signal.SIGCONT)
            with self._state_lock:
                self.paused = action == "pausing"
            if not self.stopped_by_user:
                self.queue.put("=== 已暂停 ===" if self.paused else "=== 已继续 ===")
        except Exception as exc:
            self.queue.put(f"{'暂停' if action == 'pausing' else '继续'}失败：{exc}")
        finally:
            with self._state_lock:
                self.transition = None

    def _suspend_windows_tree(self, proc):
        root = psutil.Process(proc.pid)
        suspended = []
        seen = set()
        try:
            # 先暂停子进程，最后暂停负责调度它们的主进程；再检查刚产生的后代。
            for child in root.children(recursive=True):
                try:
                    child.suspend()
                    suspended.append(child)
                    seen.add(child.pid)
                except psutil.NoSuchProcess:
                    pass
            root.suspend()
            suspended.append(root)
            for child in root.children(recursive=True):
                if child.pid not in seen:
                    try:
                        child.suspend()
                        suspended.append(child)
                    except psutil.NoSuchProcess:
                        pass
            self._suspended_processes = suspended
        except Exception:
            for process in reversed(suspended):
                try:
                    process.resume()
                except psutil.NoSuchProcess:
                    pass
            raise

    def _resume_windows_tree(self):
        # 主进程最后恢复，避免它在子进程仍暂停时继续调度流水线。
        processes = self._suspended_processes
        for process in processes:
            try:
                process.resume()
            except psutil.NoSuchProcess:
                pass
        self._suspended_processes = []

    def _stop_tree(self, proc):
        try:
            transition = self._transition_thread
            if transition is not None and transition.is_alive():
                transition.join(timeout=5)
            if os.name == "nt":
                try:
                    descendants = psutil.Process(proc.pid).children(recursive=True)
                except psutil.NoSuchProcess:
                    descendants = []
                completed = subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
                if completed.returncode != 0 or any(child.is_running() for child in descendants):
                    # 某些环境禁止 taskkill；用已记录的进程对象逐一结束残留进程。
                    if proc.poll() is None:
                        proc.kill()
                    for child in descendants:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    alive = [child for child in descendants if child.is_running()]
                    if alive:
                        _, alive = psutil.wait_procs(alive, timeout=3)
                    if proc.poll() is None or alive:
                        raise OSError(completed.stderr.strip() or "无法结束全部子进程")
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL if self.paused else signal.SIGTERM)
                except ProcessLookupError:
                    return
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
        except Exception as exc:
            self.queue.put(f"中止进程树时出现问题：{exc}")
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError as kill_exc:
                    self.queue.put(f"结束主进程失败：{kill_exc}")
        finally:
            self.paused = False
            self._suspended_processes = []

    def _pump(self, proc):
        try:
            for line in proc.stdout:
                self.queue.put(line.rstrip("\n"))
        except (OSError, UnicodeError) as exc:
            self.queue.put(f"读取运行日志失败：{exc}")
        finally:
            proc.wait()
            self.returncode = proc.returncode
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
        stop_done = self._stop_thread is None or not self._stop_thread.is_alive()
        transition_done = self._transition_thread is None or not self._transition_thread.is_alive()
        return self._done and stop_done and transition_done and self.queue.empty()
