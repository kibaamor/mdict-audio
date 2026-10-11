import time

import pytest

from mdict_audio.cli import main
from mdict_audio.container.reader import MDictReader
from mdict_audio.container.writer import write_mdict


class TestFix1PoolInterrupt:
    def test_convert_pool_interrupt_stops_promptly(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.pipeline import transcode as transcode_mod

        def slow_or_raise(key, data, src_format, *args, **kwargs):
            if key == "\\audio\\a.ogg":
                raise KeyboardInterrupt()
            time.sleep(3)
            return key, b"", None

        monkeypatch.setattr(transcode_mod, "_transcode_clip", slow_or_raise)
        path = supported_family / "testdict.mdd"
        t0 = time.monotonic()
        with pytest.raises(KeyboardInterrupt):
            transcode_mod.convert_mdd_volumes(
                [(path, MDictReader(path, is_mdd=True))],
                {path: tmp_path / "interrupt.mdd"},
                workers=2,
                spill_dir=tmp_path,
                engine="ffmpeg",
            )
        assert time.monotonic() - t0 < 2

    def test_verify_pool_interrupt_stops_promptly(self, supported_family, monkeypatch):
        from mdict_audio import family as family_mod
        from mdict_audio.commands import verify as verify_mod

        def slow_or_raise(job):
            key, data, fmt, engine = job
            if key == "\\audio\\a.mp3":
                raise KeyboardInterrupt()
            time.sleep(3)
            return key, fmt, True

        monkeypatch.setattr(verify_mod, "_decode_clip", slow_or_raise)
        fams = family_mod.discover(supported_family)
        t0 = time.monotonic()
        with pytest.raises(KeyboardInterrupt):
            verify_mod.verify_family(
                fams["testdict"], workers=2, decode=True, engine="ffmpeg"
            )
        assert time.monotonic() - t0 < 2

    def test_pool_interrupt_cli_returns_130_and_cleans_staging(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.pipeline import transcode as transcode_mod

        def raise_ki(key, data, src_format, *args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(transcode_mod, "_transcode_clip", raise_ki)
        out = tmp_path / "out"
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
        assert rc == 130
        assert not (out / "testdict.manifest.json").exists()
        assert not (out / "testdict.mdx").exists()
        assert not any(p.name.startswith(".tmp-") for p in out.iterdir())


class TestFix2VerifySinglePass:
    def test_corrupt_mdx_record_section_reported_as_problem(self, tmp_path):
        from mdict_audio import family as family_mod
        from mdict_audio.commands.verify import verify_family

        mdx = tmp_path / "bad.mdx"
        with mdx.open("wb") as f:
            write_mdict(f, [("k1", b"<div>content</div>")], is_mdd=False)
        reader = MDictReader(mdx)
        data = bytearray(mdx.read_bytes())
        data[reader._record_start + 48] ^= 0xFF
        mdx.write_bytes(bytes(data))

        fams = family_mod.discover(tmp_path)
        problems = verify_family(fams["bad"])
        assert any("bad.mdx" in p for p in problems)
        rc = main(["verify", str(tmp_path)])
        assert rc == 1


class TestFix3InspectEmptyDir:
    def test_empty_dir_exit_code_consistent(self, tmp_path, capsys):
        (tmp_path / "note.txt").write_text("x", encoding="utf-8")
        assert main(["inspect", str(tmp_path)]) == 1
        assert main(["inspect", str(tmp_path), "--family", "x"]) == 1
        captured = capsys.readouterr()
        assert "no .mdx/.mdd files found" in captured.err
        assert captured.out == ""
