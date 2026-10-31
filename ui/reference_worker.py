"""A cancellable preparation job. The worker never accesses Tk variables."""

import queue
import threading

from nspa.reference_data import PreparationCancelled, prepare_references


class ReferenceWorker:
    def __init__(self):
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, request):
        if self.running:
            raise RuntimeError('参考数据正在准备中。')
        self.cancel = threading.Event()
        self.events = queue.Queue()

        def work():
            try:
                result = prepare_references(request, lambda text: self.events.put(('progress', text)), self.cancel)
                if self.cancel.is_set():
                    raise PreparationCancelled('已取消参考数据准备。')
                self.events.put(('complete', result))
            except PreparationCancelled as exc:
                self.events.put(('cancelled', str(exc)))
            except Exception as exc:
                self.events.put(('error', str(exc)))

        self.thread = threading.Thread(target=work, daemon=True, name='NSPA-reference-preparation')
        self.thread.start()
