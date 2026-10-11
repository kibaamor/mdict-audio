
from mdict_audio.pipeline.transcode import _should_verify


class TestSampling:
    def test_all_always_true(self):
        assert _should_verify("\\audio\\a.ogg", "all")
        assert _should_verify("\\audio\\z.wav", "all")
        assert _should_verify("any", "all")

    def test_off_always_false(self):
        assert not _should_verify("\\audio\\a.ogg", "off")
        assert not _should_verify("any", "off")

    def test_sample_deterministic(self):
        keys = ["\\audio\\a.ogg", "\\audio\\b.ogg", "\\audio\\c.ogg", "\\audio\\d.ogg"]
        for k in keys:
            first = _should_verify(k, "sample")
            second = _should_verify(k, "sample")
            assert first == second, "non-deterministic for %r" % k

    def test_sample_approximately_10_percent(self):
        checked = sum(
            1 for i in range(1000) if _should_verify("key_%03d" % i, "sample")
        )
        assert 50 <= checked <= 180, "sample rate %d/1000 outside 5-18%%" % checked


class TestInlineVerifyModes:
    def test_flag_parsing(self):
        from mdict_audio.cli import build_parser

        args = build_parser().parse_args(["convert", "d"])
        assert args.inline_verify == "sample"
        args = build_parser().parse_args(["convert", "d", "--inline-verify", "all"])
        assert args.inline_verify == "all"
        args = build_parser().parse_args(["convert", "d", "--inline-verify", "off"])
        assert args.inline_verify == "off"

    def test_manifest_records_mode(self, supported_family, tmp_path):
        import json

        from mdict_audio.cli import main

        out = tmp_path / "out"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 0
        m = json.loads((out / "testdict.manifest.json").read_text(encoding="utf-8"))
        assert m["params"]["inline_verify"] == "sample"

        out2 = tmp_path / "out2"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out2),
                "--inline-verify",
                "all",
            ]
        )
        assert rc == 0
        m2 = json.loads((out2 / "testdict.manifest.json").read_text(encoding="utf-8"))
        assert m2["params"]["inline_verify"] == "all"

    def test_off_mode_skips_decode_check(self, mdd_records, monkeypatch):
        from mdict_audio.audio import Backend
        from mdict_audio.audio.ffmpeg import transcode as real_transcode
        from mdict_audio.pipeline import transcode as transcode_mod

        backend = Backend(
            "ffmpeg", "test", real_transcode, lambda data, fmt, **kw: False, False
        )
        key, out, reason = transcode_mod._transcode_clip(
            "test",
            mdd_records["/audio/hello.ogg"],
            "ogg",
            "mp3",
            "bitrate",
            "64k",
            None,
            backend,
            inline_verify="off",
        )
        assert out is not None
        assert reason is None

    def test_all_mode_catches_decode_failure(self, mdd_records, monkeypatch):
        from mdict_audio.audio import Backend
        from mdict_audio.audio.ffmpeg import transcode as real_transcode
        from mdict_audio.pipeline import transcode as transcode_mod

        backend = Backend(
            "ffmpeg", "test", real_transcode, lambda data, fmt, **kw: False, False
        )
        key, out, reason = transcode_mod._transcode_clip(
            "test",
            mdd_records["/audio/hello.ogg"],
            "ogg",
            "mp3",
            "bitrate",
            "64k",
            None,
            backend,
            inline_verify="all",
        )
        assert out is None
        assert "decode check failed" in reason

    def test_sample_mode_partial_coverage(self, mdd_records, monkeypatch):
        from mdict_audio.audio import Backend
        from mdict_audio.audio.ffmpeg import transcode as real_transcode
        from mdict_audio.pipeline import transcode as transcode_mod

        decode_calls = []
        backend = Backend(
            "ffmpeg",
            "test",
            real_transcode,
            lambda data, fmt, **kw: (decode_calls.append(1), True)[1],
            False,
        )
        for i in range(20):
            transcode_mod._transcode_clip(
                "key_%02d" % i,
                mdd_records["/audio/hello.ogg"],
                "ogg",
                "mp3",
                "bitrate",
                "64k",
                None,
                backend,
                inline_verify="sample",
            )
        assert 0 < len(decode_calls) < 20
