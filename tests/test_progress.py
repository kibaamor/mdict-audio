import io

from mdict_audio.pipeline.progress import ProgressReporter


class TtyStringIO(io.StringIO):
    def isatty(self):
        return True


def test_progress_clears_long_previous_line(monkeypatch):
    stderr = TtyStringIO()
    times = iter([0, 1, 100])
    monkeypatch.setattr("sys.stderr", stderr)
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    label = "Transcoding Oxford-Advanced-Learner-s-English-Chinese-Dictionary-10th-edition-Simplified"
    progress = ProgressReporter(245508, label, interval=1)

    progress.update(213000)
    progress.update(1)

    writes = [part for part in stderr.getvalue().split("\r") if part]
    assert len(writes[1]) >= len(writes[0])
    assert writes[1].endswith(" ")
