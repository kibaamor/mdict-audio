import signal
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager

_JOIN_BUDGET = 5.0


def _ignore_control_interrupts():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)


@contextmanager
def interruptible_pool(workers, process=False):
    if process:
        pool = ProcessPoolExecutor(
            max_workers=max(1, workers), initializer=_ignore_control_interrupts
        )
    else:
        pool = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        yield pool
    except BaseException:
        procs = list((getattr(pool, "_processes", None) or {}).values())
        deadline = time.monotonic() + _JOIN_BUDGET
        pool.shutdown(wait=False, cancel_futures=True)
        for proc in procs:
            proc.join(timeout=max(0.0, deadline - time.monotonic()))
            if proc.is_alive():
                proc.terminate()
        call_queue = getattr(pool, "_call_queue", None)
        if call_queue is not None:
            call_queue.cancel_join_thread()
        raise
    pool.shutdown()
