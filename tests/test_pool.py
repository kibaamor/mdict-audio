import signal
import time

import pytest

from mdict_audio.pipeline.pool import interruptible_pool


def _control_interrupts_are_ignored():
    ignored = signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    if hasattr(signal, "SIGBREAK"):
        ignored = ignored and signal.getsignal(signal.SIGBREAK) is signal.SIG_IGN
    return ignored


def _sleep_task(seconds):
    time.sleep(seconds)
    return "done"


class TestProcessPoolInterrupt:
    def test_workers_ignore_control_interrupts(self):
        with interruptible_pool(2, process=True) as pool:
            future = pool.submit(_control_interrupts_are_ignored)
            assert future.result(timeout=30) is True

    def test_interrupt_joins_inflight_workers(self):
        t0 = time.monotonic()
        pools = []
        with pytest.raises(KeyboardInterrupt):
            with interruptible_pool(2, process=True) as pool:
                pools.append(pool)
                pool.submit(_sleep_task, 8.0)
                time.sleep(0.5)
                raise KeyboardInterrupt()
        elapsed = time.monotonic() - t0
        assert elapsed < 8.0
        for proc in list((getattr(pools[0], "_processes", None) or {}).values()):
            proc.join(timeout=2.0)
            assert not proc.is_alive()

    def test_thread_pool_has_no_initializer_path(self):
        with interruptible_pool(2, process=False) as pool:
            assert pool.submit(lambda: 1).result(timeout=30) == 1
