import json
import sys

import pytest

from mdict_audio.audio import EngineError, resolve_engine
from mdict_audio.audio.ffmpeg import TranscodeError
from mdict_audio.cli import main

try:
    import av  # noqa: F401

    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False


def _no_ffmpeg(monkeypatch):
    def fail():
        raise TranscodeError(
            "ffmpeg not found on PATH; install ffmpeg to convert audio"
        )

    monkeypatch.setattr("mdict_audio.audio.find_ffmpeg", fail)


class TestResolveEngineMatrix:
    @pytest.mark.skipif(not AV_AVAILABLE, reason="pyav not installed")
    def test_auto_mp3_prefers_pyav(self):
        assert resolve_engine("auto", "mp3") == ("pyav", "auto")

    @pytest.mark.skipif(not AV_AVAILABLE, reason="pyav not installed")
    def test_explicit_pyav_mp3(self):
        assert resolve_engine("pyav", "mp3") == ("pyav", "requested")

    def test_auto_mp3_without_pyav_falls_back(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "av", None)
        assert resolve_engine("auto", "mp3") == (
            "ffmpeg",
            "auto; pyav not installed",
        )

    def test_auto_mp3_no_engine_at_all(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "av", None)
        _no_ffmpeg(monkeypatch)
        with pytest.raises(EngineError):
            resolve_engine("auto", "mp3")

    def test_explicit_pyav_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "av", None)
        with pytest.raises(EngineError) as ei:
            resolve_engine("pyav", "mp3")
        assert "mdict-audio[pyav]" in str(ei.value)

    def test_pyav_ogg_rejected(self):
        with pytest.raises(EngineError) as ei:
            resolve_engine("pyav", "ogg")
        assert "libvorbis" in str(ei.value)

    def test_auto_ogg_uses_ffmpeg(self):
        assert resolve_engine("auto", "ogg") == (
            "ffmpeg",
            "ogg target requires ffmpeg",
        )

    def test_explicit_ffmpeg(self):
        assert resolve_engine("ffmpeg", "mp3") == ("ffmpeg", "requested")

    def test_explicit_ffmpeg_missing(self, monkeypatch):
        _no_ffmpeg(monkeypatch)
        with pytest.raises(EngineError) as ei:
            resolve_engine("ffmpeg", "mp3")
        assert "ffmpeg not found" in str(ei.value)


class TestAutoFallbackE2E:
    def test_auto_without_pyav_transcodes_via_ffmpeg(
        self, supported_family, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setitem(sys.modules, "av", None)
        out = tmp_path / "converted"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        err = capsys.readouterr().err
        assert rc == 0
        assert "engine: ffmpeg (auto; pyav not installed)" in err
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["rename_map"]
        assert manifest["stats"]["transcoded"] > 0
        assert manifest["stats"]["failed"] == 0
        assert manifest["params"]["engine"] == "ffmpeg"
        assert manifest["params"]["engine_reason"] == "auto; pyav not installed"


class TestWorkerEngineFailure:
    def test_worker_engine_failure_keeps_original(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.pipeline import transcode

        calls = {"n": 0}
        real = transcode.get_backend

        def flaky(engine, dst_fmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return real(engine, dst_fmt)
            raise EngineError("worker engine divergence")

        monkeypatch.setattr(transcode, "get_backend", flaky)
        out = tmp_path / "converted"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--engine",
                "ffmpeg",
            ]
        )
        assert rc == 0
        assert calls["n"] > 1
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["failed"] > 0
        assert manifest["stats"]["transcoded"] == 0
        assert any(
            "engine unavailable" in w and "kept original resource" in w
            for w in manifest["warnings"]
        )


class TestVerifyEngineWiring:
    def test_verify_decode_pyav_missing_errors(
        self, supported_family, monkeypatch, capsys
    ):
        monkeypatch.setitem(sys.modules, "av", None)
        rc = main(["verify", str(supported_family), "--decode", "--engine", "pyav"])
        err = capsys.readouterr().err
        assert rc == 2
        assert "mdict-audio[pyav]" in err

    def test_verify_without_decode_has_no_engine_line(self, supported_family, capsys):
        rc = main(["verify", str(supported_family)])
        err = capsys.readouterr().err
        assert rc == 0
        assert "engine:" not in err

    def test_verify_decode_displays_engine(self, supported_family, capsys):
        rc = main(["verify", str(supported_family), "--decode", "--engine", "ffmpeg"])
        err = capsys.readouterr().err
        assert rc == 0
        assert "engine: ffmpeg (requested)" in err


class TestConvertEngineWiring:
    def test_pyav_with_ogg_target_rejected(self, supported_family, tmp_path, capsys):
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(tmp_path / "out"),
                "--engine",
                "pyav",
                "--to",
                "ogg",
            ]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "libvorbis" in err

    def test_pyav_missing_rejected(
        self, supported_family, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setitem(sys.modules, "av", None)
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(tmp_path / "out"),
                "--engine",
                "pyav",
            ]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "mdict-audio[pyav]" in err

    def test_ogg_run_displays_and_records_engine(
        self, supported_family, tmp_path, capsys
    ):
        out = tmp_path / "out"
        rc = main(
            ["convert", str(supported_family), "--out-dir", str(out), "--to", "ogg"]
        )
        err = capsys.readouterr().err
        assert rc == 0
        assert "engine: ffmpeg (ogg target requires ffmpeg)" in err
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["engine"] == "ffmpeg"
        assert manifest["params"]["engine_reason"] == "ogg target requires ffmpeg"
