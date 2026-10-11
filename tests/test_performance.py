import json

from mdict_audio.audio.ffmpeg import TranscodeError
from mdict_audio.cli import build_parser, main
from mdict_audio.container.reader import MDictReader
from mdict_audio.pipeline.transcode import convert_mdd_volumes


class TestQualityFlags:
    def test_flag_parsing_and_defaults(self):
        import os

        from mdict_audio import DEFAULT_WORKERS

        args = build_parser().parse_args(["convert", "d"])
        assert args.quality == "speech"
        assert args.bitrate is None
        assert args.workers == DEFAULT_WORKERS == (os.cpu_count() or 1)
        args = build_parser().parse_args(
            [
                "convert",
                "d",
                "--quality",
                "speech",
                "--workers",
                "4",
                "--bitrate",
                "96k",
            ]
        )
        assert args.quality == "speech"
        assert args.workers == 4
        assert args.bitrate == "96k"

    def test_manifest_records_speech_preset(self, supported_family, tmp_path):
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--quality",
                "speech",
                "--workers",
                "2",
            ]
        )
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["quality_mode"] == "bitrate"
        assert manifest["params"]["quality_value"] == "64k"
        assert manifest["params"]["to"] == "mp3"
        assert manifest["params"]["quality"] == "speech"
        assert manifest["params"]["workers"] == 2

    def test_manifest_records_ogg_speech_preset(self, supported_family, tmp_path):
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--to",
                "ogg",
                "--quality",
                "speech",
            ]
        )
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["to"] == "ogg"
        assert manifest["params"]["quality_mode"] == "quality"
        assert manifest["params"]["quality_value"] == "2"

    def test_bitrate_overrides_quality(self, supported_family, tmp_path):
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--quality",
                "speech",
                "--bitrate",
                "32k",
            ]
        )
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["quality_value"] == "32k"
        assert manifest["params"]["quality"] == "speech"

    def test_default_is_speech(self, supported_family, tmp_path):
        out = tmp_path / "out"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["quality_value"] == "64k"
        assert manifest["params"]["quality"] == "speech"


class TestParallelVerify:
    def test_verify_workers_flag_parses(self):
        args = build_parser().parse_args(["verify", "d", "--workers", "4"])
        assert args.workers == 4

    def test_verify_parallel_matches_sequential(self, supported_family):
        from mdict_audio import family as family_mod
        from mdict_audio.commands.verify import verify_family

        fams = family_mod.discover(supported_family)
        seq = verify_family(fams["testdict"], workers=1, decode=True)
        par = verify_family(fams["testdict"], workers=8, decode=True)
        assert seq == par
        assert seq == []

    def test_verify_parallel_reports_same_problems(self, tmp_path, mdd_records):
        from mdict_audio import family as family_mod
        from mdict_audio.commands.verify import verify_family
        from mdict_audio.container.writer import write_mdict

        payload = mdd_records["/audio/voice.mp3"]
        corrupted = payload[:10] + b"\x00\x01\x02garbage-not-frames"
        with (tmp_path / "bad.mdd").open("wb") as f:
            write_mdict(f, [("\\audio\\broken.mp3", corrupted)], is_mdd=True)
        with (tmp_path / "bad.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)

        fams = family_mod.discover(tmp_path)
        seq = verify_family(fams["bad"], workers=1, decode=True)
        par = verify_family(fams["bad"], workers=4, decode=True)
        assert seq == par
        assert len(seq) == 1
        assert "not decodable" in seq[0]


class TestParallelTranscode:
    def test_parallel_matches_sequential(self, supported_family, tmp_path):
        path = supported_family / "testdict.mdd"
        seq_map, seq_warnings, seq_stats = convert_mdd_volumes(
            [(path, MDictReader(path, is_mdd=True))],
            {path: tmp_path / "seq.mdd"},
            workers=1,
            spill_dir=tmp_path,
            engine="ffmpeg",
        )
        par_map, par_warnings, par_stats = convert_mdd_volumes(
            [(path, MDictReader(path, is_mdd=True))],
            {path: tmp_path / "par.mdd"},
            workers=8,
            spill_dir=tmp_path,
            engine="ffmpeg",
        )
        assert seq_map == par_map
        assert seq_stats == par_stats
        assert len(seq_warnings) == len(par_warnings)
        assert (tmp_path / "seq.mdd").read_bytes() == (
            tmp_path / "par.mdd"
        ).read_bytes()

    def test_failure_preserved_under_threads(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.audio import ffmpeg as ffmpeg_mod

        reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        hello_payload = dict(reader.iter_records())["\\audio\\hello.ogg"]
        real_transcode = ffmpeg_mod.transcode

        def flaky_transcode(data, src_format, *args, **kwargs):
            if data == hello_payload:
                raise TranscodeError("boom")
            return real_transcode(data, src_format, *args, **kwargs)

        monkeypatch.setattr(ffmpeg_mod, "transcode", flaky_transcode)

        path = supported_family / "testdict.mdd"
        out = tmp_path / "out.mdd"
        family_map, warnings, stats = convert_mdd_volumes(
            [(path, MDictReader(path, is_mdd=True))],
            {path: out},
            workers=4,
            spill_dir=tmp_path,
            engine="ffmpeg",
        )
        entries = dict(MDictReader(out, is_mdd=True).iter_records())
        assert entries["\\audio\\hello.ogg"] == hello_payload
        assert "\\audio\\hello.ogg" not in family_map
        assert stats["failed"] == 1
        assert stats["transcoded"] >= 3
        assert any("kept original" in w for w in warnings)
