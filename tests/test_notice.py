from pathlib import Path


def test_notice_names_mdict_utils_attribution():
    notice = Path(__file__).resolve().parents[1] / "NOTICE"
    text = notice.read_text(encoding="utf-8")
    assert "mdict-utils" in text
    assert "MIT" in text
    assert "mdict_audio/container/" in text
    assert "runtime dependency" in text
