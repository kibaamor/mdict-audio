import sys
import time


class ProgressReporter:
    def __init__(self, total, label="Working", interval=100):
        self.total = total
        self.label = label
        self.interval = interval
        self.done = 0
        self.start = time.monotonic()
        self.enabled = sys.stderr.isatty()
        self._last_len = 0

    def update(self, n=1):
        if not self.enabled:
            return
        self.done += n
        if self.done % self.interval == 0 or self.done == self.total:
            self._emit()

    def _emit(self):
        elapsed = time.monotonic() - self.start
        pct = self.done / self.total * 100 if self.total else 100
        rate = self.done / elapsed if elapsed > 0 else 0
        eta = (self.total - self.done) / rate if rate > 0 else 0
        line = "  %s: %d/%d (%.0f%%) %.0f/s ETA %.0fs" % (
            self.label,
            self.done,
            self.total,
            pct,
            rate,
            eta,
        )
        pad = max(0, self._last_len - len(line), 80 - len(line))
        sys.stderr.write("\r" + line + " " * pad)
        self._last_len = len(line)
        sys.stderr.flush()

    def finish(self):
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.start
        line = "  %s: %d/%d (100%%) in %.1fs" % (
            self.label,
            self.total,
            self.total,
            elapsed,
        )
        pad = max(0, self._last_len - len(line), 80 - len(line))
        sys.stderr.write("\r" + line + " " * pad + "\n")
        self._last_len = 0
        sys.stderr.flush()


def counted(entries, progress):
    for item in entries:
        yield item
        progress.update()
