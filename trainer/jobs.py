"""One serialized background job, with results delivered on the Qt UI thread."""
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, QTimer


class Jobs(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ra2-memory")
        self.future = None
        self.callback = None
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.poll)

    @property
    def busy(self):
        return self.future is not None

    def submit(self, function, callback):
        if self.busy:
            return False
        self.future = self.pool.submit(function)
        self.callback = callback
        self.timer.start()
        return True

    def poll(self):
        if not self.future or not self.future.done():
            return
        future, callback = self.future, self.callback
        self.future = self.callback = None
        self.timer.stop()
        try:
            result, error = future.result(), None
        except Exception as exc:
            result, error = None, exc
        callback(result, error)

    def close(self):
        self.timer.stop()
        # The process handle and controllers may be released immediately after
        # this returns. Never leave a memory job running against that handle.
        self.pool.shutdown(wait=True, cancel_futures=True)

    def drain(self):
        """Finish the current job and deliver its result before a synchronous edit."""
        if self.future is not None:
            try:
                self.future.result()
            except Exception:
                pass
            self.poll()
