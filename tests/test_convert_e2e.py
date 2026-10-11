import hashlib
import json
import shutil
from pathlib import Path

import pytest
from conftest import make_stub_mdx_bytes

from mdict_audio.audio.sniff import sniff_format
from mdict_audio.cli import main
from mdict_audio.container.reader import MDictReader


def _digest_dir(path):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(path).iterdir())
    }


class TestFamilyConversion:
    def test_convert_writes_output_and_leaves_inputs_unchanged(
        self, supported_family, tmp_path
    ):
        before = _digest_dir(supported_family)
        out = tmp_path / "converted"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 0
        assert _digest_dir(supported_family) == before
        assert (out / "testdict.mdx").is_file()
        assert (out / "testdict.mdd").is_file()
        assert (out / "testdict.manifest.json").is_file()
        assert not any(p.name.startswith(".tmp-") for p in out.iterdir())

        reader = MDictReader(out / "testdict.mdd", is_mdd=True)
        records = dict(reader.iter_records())
        assert "\\audio\\hello.mp3" in records
        assert "\\audio\\hello.ogg" not in records
        assert sniff_format(records["\\audio\\hello.mp3"]) == "mp3"
        assert sniff_format(records["\\audio\\beep.mp3"]) == "mp3"
        assert sniff_format(records["\\audio\\voice.mp3"]) == "mp3"
        assert records["\\img\\logo.png"].startswith(b"\x89PNG")
        assert records["\\css\\style.css"] == b"body{color:#333}"
        assert "\\audio\\a.converted-2.mp3" in records
        assert "\\audio\\a.mp3" in records

        mdx = dict(MDictReader(out / "testdict.mdx").iter_records())
        assert b"sound://audio/hello.mp3" in mdx["hello"]
        assert b"sound://audio/hello.ogg" not in mdx["hello"]
        assert b"sound://\\audio\\world.mp3" in mdx["world"]
        assert b"sound://audio/voice.mp3" in mdx["voice"]

    def test_converted_output_reads_back_in_reference_reader(
        self, supported_family, tmp_path
    ):
        from mdict_utils.base.readmdict import MDD, MDX

        out = tmp_path / "converted"
        assert main(["convert", str(supported_family), "--out-dir", str(out)]) == 0

        mdd = MDD(str(out / "testdict.mdd"))
        ref_keys = {k.decode() for k in mdd.keys()}
        assert "\\audio\\hello.mp3" in ref_keys
        assert "\\audio\\a.converted-2.mp3" in ref_keys
        assert "\\audio\\hello.ogg" not in ref_keys

        mdx = MDX(str(out / "testdict.mdx"))
        html = {k.decode(): v for k, v in mdx.items()}
        assert b"sound://audio/hello.mp3" in html["hello"]

    def test_default_out_dir_lands_under_input(self, supported_family, tmp_path):
        dicts = tmp_path / "dicts"
        shutil.copytree(supported_family, dicts)
        rc = main(["convert", str(dicts)])
        assert rc == 0
        converted = dicts / "converted"
        assert (converted / "testdict.mdx").is_file()
        assert (converted / "testdict.mdd").is_file()
        assert (converted / "testdict.manifest.json").is_file()

    def test_unsupported_family_rejected_before_writing(self, tmp_path, capsys):
        (tmp_path / "bad.mdx").write_bytes(make_stub_mdx_bytes(version="3.0"))
        out = tmp_path / "converted"
        rc = main(["convert", str(tmp_path), "--out-dir", str(out)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "rejected" in captured.err
        assert not (out / "bad.mdx").exists()
        assert not (out / "bad.manifest.json").exists()


class TestStagedCommit:
    def test_injected_failure_cleans_staging_and_leaves_no_manifest(
        self, supported_family, tmp_path, monkeypatch, capsys
    ):
        from mdict_audio.commands import convert as convert_command

        def boom(*args, **kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(convert_command, "convert_mdx", boom)
        out = tmp_path / "converted"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "failed" in captured.err
        assert not (out / "testdict.manifest.json").exists()
        assert not (out / "testdict.mdx").exists()
        assert not (out / "testdict.mdd").exists()
        assert not any(p.name.startswith(".tmp-") for p in out.iterdir())


class TestConversionInterruption:
    def test_interrupt_cleans_staging_and_exits_130(
        self, supported_family, tmp_path, monkeypatch, capsys
    ):
        from mdict_audio.commands import convert as convert_command

        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(convert_command, "convert_mdx", interrupt)
        out = tmp_path / "converted"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 130
        assert not (out / "testdict.manifest.json").exists()
        assert not (out / "testdict.mdx").exists()
        assert not (out / "testdict.mdd").exists()
        assert not any(p.name.startswith(".tmp-") for p in out.iterdir())


class TestManifest:
    def test_manifest_records_renames_params_and_inputs(
        self, supported_family, tmp_path
    ):
        out = tmp_path / "converted"
        assert main(["convert", str(supported_family), "--out-dir", str(out)]) == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["family"] == "testdict"
        assert manifest["tool_version"]
        assert manifest["params"]["to"] == "mp3"
        assert manifest["params"]["engine"] in ("ffmpeg", "pyav")
        assert manifest["params"]["collision"] == "rename"
        assert manifest["rename_map"]["\\audio\\hello.ogg"] == "\\audio\\hello.mp3"
        assert manifest["rename_map"]["\\audio\\a.ogg"] == "\\audio\\a.converted-2.mp3"
        assert "\\audio\\voice.mp3" not in manifest["rename_map"]
        assert {i["path"] for i in manifest["inputs"]} == {
            str(supported_family / "testdict.mdx"),
            str(supported_family / "testdict.mdd"),
        }
        assert all(
            i["size"] > 0 and i["mtime"] and len(i["header_hash"]) == 64
            for i in manifest["inputs"]
        )
        assert manifest["stats"]["transcoded"] >= 3
        assert any("collision" in w for w in manifest["warnings"])


class TestTargetFormatOgg:
    def test_convert_to_ogg_e2e(self, supported_family, tmp_path):
        src_records = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        out = tmp_path / "out"
        rc = main(
            ["convert", str(supported_family), "--out-dir", str(out), "--to", "ogg"]
        )
        assert rc == 0

        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\hello.ogg"] == src_records["\\audio\\hello.ogg"]
        assert records["\\audio\\a.ogg"] == src_records["\\audio\\a.ogg"]
        for key in (
            "\\audio\\voice.ogg",
            "\\audio\\beep.ogg",
            "\\audio\\wave.ogg",
            "\\audio\\a.converted-2.ogg",
        ):
            assert sniff_format(records[key]) == "ogg"
        assert "\\audio\\voice.mp3" not in records
        assert "\\audio\\a.mp3" not in records

        mdx = dict(MDictReader(out / "testdict.mdx").iter_records())
        assert b"sound://audio/hello.ogg" in mdx["hello"]
        assert b"sound://audio/voice.ogg" in mdx["voice"]
        assert b"sound://audio/voice.mp3" not in mdx["voice"]
        assert b"sound://audio/a.ogg" in mdx["clash"]

        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["to"] == "ogg"
        assert manifest["params"]["quality_mode"] == "quality"
        assert manifest["params"]["quality_value"] == "2"
        assert manifest["rename_map"]["\\audio\\voice.mp3"] == "\\audio\\voice.ogg"
        assert manifest["rename_map"]["\\audio\\a.mp3"] == "\\audio\\a.converted-2.ogg"
        assert manifest["stats"]["collisions"] == 1
        assert any("collision" in w for w in manifest["warnings"])
        assert main(["verify", str(out)]) == 0

    def test_invalid_target_rejected(self, supported_family, tmp_path):
        import pytest

        out = tmp_path / "out"
        with pytest.raises(SystemExit) as exc:
            main(
                ["convert", str(supported_family), "--out-dir", str(out), "--to", "wav"]
            )
        assert exc.value.code == 2
        assert not out.exists()


class TestForceReencode:
    def test_flag_parsing(self):
        from mdict_audio.cli import build_parser

        args = build_parser().parse_args(["convert", "d", "--force"])
        assert args.force is True
        assert build_parser().parse_args(["convert", "d"]).force is False

    def test_plan_renames_force(self, supported_family):
        from mdict_audio.refs import plan_renames_by_format

        reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        records = list(reader.iter_records())
        rename_map, transcode = plan_renames_by_format(
            ((key, sniff_format(data)) for key, data in records),
            target="mp3",
            force=True,
        )
        assert "\\audio\\voice.mp3" in transcode
        assert "\\audio\\voice.mp3" not in rename_map
        assert "\\audio\\a.mp3" in transcode
        assert "\\audio\\a.mp3" not in rename_map
        assert rename_map["\\audio\\hello.ogg"] == "\\audio\\hello.mp3"
        assert "\\audio\\hello.ogg" in transcode
        assert "\\img\\logo.png" not in transcode

    def test_force_e2e_mp3(self, supported_family, tmp_path):
        src = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--force",
                "--quality",
                "speech",
            ]
        )
        assert rc == 0

        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\voice.mp3"] != src["\\audio\\voice.mp3"]
        assert sniff_format(records["\\audio\\voice.mp3"]) == "mp3"
        assert records["\\audio\\a.mp3"] != src["\\audio\\a.mp3"]
        assert "\\audio\\hello.mp3" in records
        assert "\\audio\\hello.ogg" not in records
        assert "\\audio\\a.converted-2.mp3" in records

        mdx = dict(MDictReader(out / "testdict.mdx").iter_records())
        assert b"sound://audio/voice.mp3" in mdx["voice"]
        assert b"sound://audio/hello.mp3" in mdx["hello"]
        assert b"sound://audio/hello.ogg" not in mdx["hello"]

        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["force"] is True
        assert "\\audio\\voice.mp3" not in manifest["rename_map"]
        assert manifest["rename_map"]["\\audio\\hello.ogg"] == "\\audio\\hello.mp3"
        assert manifest["stats"] == {
            "transcoded": 7,
            "passed_through": 2,
            "failed": 0,
            "collisions": 1,
            "overwritten": 0,
            "skipped": 0,
            "broken_refs_pre_existing": 0,
            "broken_refs_introduced": 0,
        }
        assert main(["verify", str(out)]) == 0

    def test_force_failure_keeps_original(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.audio import ffmpeg as ffmpeg_mod
        from mdict_audio.audio.ffmpeg import TranscodeError

        src = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        voice_payload = src["\\audio\\voice.mp3"]
        real_transcode = ffmpeg_mod.transcode

        def flaky_transcode(data, src_format, *args, **kwargs):
            if data == voice_payload:
                raise TranscodeError("boom")
            return real_transcode(data, src_format, *args, **kwargs)

        monkeypatch.setattr(ffmpeg_mod, "transcode", flaky_transcode)
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--force",
                "--quality",
                "speech",
                "--engine",
                "ffmpeg",
            ]
        )
        assert rc == 0
        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\voice.mp3"] == voice_payload
        assert (
            "\\audio\\voice.mp3"
            not in json.loads(
                (out / "testdict.manifest.json").read_text(encoding="utf-8")
            )["rename_map"]
        )
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["failed"] == 1
        assert any(
            "voice.mp3" in w and "kept original" in w for w in manifest["warnings"]
        )


class TestCollisionStrategiesE2E:
    def test_overwrite_e2e(self, supported_family, tmp_path):
        src = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--on-collision",
                "overwrite",
            ]
        )
        assert rc == 0
        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\a.mp3"] != src["\\audio\\a.mp3"]
        assert sniff_format(records["\\audio\\a.mp3"]) == "mp3"
        assert "\\audio\\a.ogg" not in records
        assert "\\audio\\a.converted-2.mp3" not in records
        assert records["\\audio\\voice.mp3"] == src["\\audio\\voice.mp3"]
        mdx = dict(MDictReader(out / "testdict.mdx").iter_records())
        assert b"sound://audio/a.mp3" in mdx["clash"]
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["collision"] == "overwrite"
        assert manifest["stats"]["overwritten"] == 1
        assert manifest["stats"]["skipped"] == 0
        assert any("overwrote existing key" in w for w in manifest["warnings"])
        assert main(["verify", str(out)]) == 0

    def test_skip_e2e(self, supported_family, tmp_path):
        src = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--on-collision",
                "skip",
            ]
        )
        assert rc == 0
        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\a.mp3"] == src["\\audio\\a.mp3"]
        assert "\\audio\\a.ogg" not in records
        assert "\\audio\\a.converted-2.mp3" not in records
        mdx = dict(MDictReader(out / "testdict.mdx").iter_records())
        assert b"sound://audio/a.mp3" in mdx["clash"]
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["params"]["collision"] == "skip"
        assert manifest["stats"]["skipped"] == 1
        assert manifest["stats"]["overwritten"] == 0
        assert manifest["stats"]["transcoded"] == 4
        assert any("skipped conversion" in w for w in manifest["warnings"])
        assert main(["verify", str(out)]) == 0

    def test_overwrite_force_interplay(self, supported_family, tmp_path):
        src = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        out = tmp_path / "out"
        rc = main(
            [
                "convert",
                str(supported_family),
                "--out-dir",
                str(out),
                "--on-collision",
                "overwrite",
                "--force",
                "--quality",
                "speech",
            ]
        )
        assert rc == 0
        records = dict(MDictReader(out / "testdict.mdd", is_mdd=True).iter_records())
        assert records["\\audio\\a.mp3"] != src["\\audio\\a.mp3"]
        assert records["\\audio\\voice.mp3"] != src["\\audio\\voice.mp3"]
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["transcoded"] == 6
        assert manifest["stats"]["overwritten"] == 1

    def test_collision_flag_parsing(self):
        from mdict_audio.cli import build_parser

        args = build_parser().parse_args(["convert", "d", "--on-collision", "skip"])
        assert args.on_collision == "skip"
        assert build_parser().parse_args(["convert", "d"]).on_collision == "rename"


class TestOutputExists:
    def test_rerun_rejected_without_redo(self, supported_family, tmp_path, capsys):
        out = tmp_path / "converted"
        assert main(["convert", str(supported_family), "--out-dir", str(out)]) == 0
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "already exists" in captured.err
        assert "--redo" in captured.err

    def test_rerun_with_redo_succeeds(self, supported_family, tmp_path):
        out = tmp_path / "converted"
        assert main(["convert", str(supported_family), "--out-dir", str(out)]) == 0
        assert (
            main(["convert", str(supported_family), "--out-dir", str(out), "--redo"])
            == 0
        )

    def test_debug_env_reraises_family_failure(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.commands import convert as convert_cmd

        def fail(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setenv("MDICT_AUDIO_DEBUG", "1")
        monkeypatch.setattr(convert_cmd, "convert_mdd_volumes", fail)

        with pytest.raises(RuntimeError, match="boom"):
            main(["convert", str(supported_family), "--out-dir", str(tmp_path / "out")])


class TestMdxHeaderPreservation:
    def test_convert_preserves_mdx_stylesheet(self, tmp_path):
        """Full convert pipeline preserves source MDX StyleSheet."""
        from mdict_audio.container.reader import MDictReader
        from mdict_audio.container.writer import write_mdict

        dicts = tmp_path / "dicts"
        dicts.mkdir()
        with (dicts / "test.mdx").open("wb") as f:
            write_mdict(
                f,
                [("hello", b"<div>hello</div>")],
                is_mdd=False,
                header={"StyleSheet": "/data/style.css"},
            )
        with (dicts / "test.mdd").open("wb") as f:
            write_mdict(f, [(r"\img\logo.png", b"\x89PNG")], is_mdd=True)

        out = tmp_path / "out"
        assert main(["convert", str(dicts), "--out-dir", str(out)]) == 0

        reader = MDictReader(out / "test.mdx", is_mdd=False)
        assert reader.header["StyleSheet"] == "/data/style.css"
