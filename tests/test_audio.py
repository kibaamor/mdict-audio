import subprocess

import pytest

from mdict_audio.audio import ffmpeg as ffmpeg_mod
from mdict_audio.audio.ffmpeg import TranscodeError, decode_ok, transcode
from mdict_audio.audio.sniff import sniff_format

SOURCES = {
    "ogg": "/audio/hello.ogg",
    "mp3": "/audio/voice.mp3",
    "wav": "/audio/wave.wav",
    "m4a": "/audio/beep.m4a",
}


class TestTranscodeMatrix:
    def test_all_sources_to_both_targets(self, mdd_records):
        for dst, mode, value in (("mp3", "bitrate", "64k"), ("ogg", "quality", "2")):
            for src, path in SOURCES.items():
                out = transcode(mdd_records[path], src, dst, mode, value)
                assert sniff_format(out) == dst
                assert decode_ok(out, dst)

    def test_bitrate_format_consistency(self, mdd_records):
        """64k, 64K, and 64000 must produce identical PyAV output."""
        from mdict_audio.audio.pyav import transcode as pyav_transcode

        clip = mdd_records["/audio/hello.ogg"]
        sizes = {
            len(pyav_transcode(clip, "ogg", "mp3", "bitrate", v))
            for v in ("64k", "64K", "64000")
        }
        assert len(sizes) == 1

    def test_ogg_explicit_bitrate_mode(self, mdd_records):
        out = transcode(mdd_records["/audio/hello.ogg"], "ogg", "ogg", "bitrate", "48k")
        assert sniff_format(out) == "ogg"
        assert decode_ok(out, "ogg")

    def test_ogg_quality_presets(self, mdd_records):
        for value in ("2", "4", "6"):
            out = transcode(
                mdd_records["/audio/beep.m4a"], "m4a", "ogg", "quality", value
            )
            assert sniff_format(out) == "ogg"
            assert decode_ok(out, "ogg")


class TestDecodeChecks:
    def test_decode_ok_rejects_invalid_mp3(self):
        assert not decode_ok(b"this is not audio at all", "mp3")

    def test_decode_ok_accepts_fixture_payloads(self, mdd_records):
        for fmt, path in SOURCES.items():
            assert decode_ok(mdd_records[path], fmt)

    def test_transcode_failure_raises_transcode_error(self):
        with pytest.raises(TranscodeError):
            transcode(b"garbage data, not audio", "ogg", "mp3", "bitrate", "64k")

    def test_ffmpeg_oserror_degrades_to_transcode_error(self, mdd_records, monkeypatch):
        """OSError from subprocess.run becomes TranscodeError, not family abort."""

        def gone_binary(*args, **kwargs):
            raise FileNotFoundError("ffmpeg: no such file")

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", gone_binary)
        with pytest.raises(TranscodeError, match="process error"):
            transcode(mdd_records["/audio/hello.ogg"], "ogg", "mp3", "bitrate", "64k")


class TestSpill:
    def test_spill_writes_temp_files_under_staging_and_cleans(
        self, mdd_records, tmp_path, monkeypatch
    ):
        calls = []
        real_run = subprocess.run

        def spy_run(args, **kwargs):
            calls.append(list(args))
            return real_run(args, **kwargs)

        monkeypatch.setattr(ffmpeg_mod.subprocess, "run", spy_run)
        out = transcode(
            mdd_records["/audio/hello.ogg"],
            "ogg",
            "ogg",
            "quality",
            "2",
            spill_dir=tmp_path,
            spill_threshold=1,
        )
        assert sniff_format(out) == "ogg"
        assert calls
        assert not any("pipe:0" in args for args in calls)
        assert any(".spill-out.ogg" in arg for args in calls for arg in args)
        assert list(tmp_path.iterdir()) == []

    def test_spill_failure_cleans_staging(self, tmp_path):
        with pytest.raises(TranscodeError):
            transcode(
                b"garbage",
                "ogg",
                "mp3",
                "bitrate",
                "64k",
                spill_dir=tmp_path,
                spill_threshold=1,
            )
        assert list(tmp_path.iterdir()) == []
