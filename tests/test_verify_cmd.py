import hashlib
from pathlib import Path

import pytest
from conftest import make_stub_mdx_bytes

from mdict_audio.cli import main
from mdict_audio.container.writer import write_mdict


def _write_mdd(path, entries):
    with path.open("wb") as f:
        write_mdict(f, entries, is_mdd=True)


def _write_mdx(path, entries):
    with path.open("wb") as f:
        write_mdict(f, entries, is_mdd=False)


class TestVerifyCommand:
    def test_valid_family_passes(self, supported_family, capsys):
        rc = main(["verify", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "family testdict (v2.0): OK" in out

    def test_unsupported_container_fails(self, tmp_path, capsys):
        (tmp_path / "bad.mdx").write_bytes(make_stub_mdx_bytes(version="3.0"))
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "FAILED" in out
        assert "2.0" in out

    def test_unsorted_mdd_keys_fail(self, tmp_path, capsys):
        with (tmp_path / "unsorted.mdd").open("wb") as f:
            write_mdict(
                f, [("B.ogg", b"x"), ("a.ogg", b"y")], is_mdd=True, sort_entries=False
            )
        _write_mdx(
            tmp_path / "unsorted.mdx",
            [("k", b"<div>no refs</div>")],
        )
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "not sorted" in out

    def test_unsorted_mdx_keys_not_flagged(self, tmp_path, capsys):
        with (tmp_path / "u.mdx").open("wb") as f:
            write_mdict(
                f, [("Word", b"x"), ("apple", b"y")], is_mdd=False, sort_entries=False
            )
        _write_mdd(tmp_path / "u.mdd", [("a.ogg", b"x")])
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "not sorted" not in out


class TestReferenceClosure:
    def test_missing_reference_fails_and_is_reported(self, tmp_path, capsys):
        _write_mdd(tmp_path / "ghost.mdd", [("\\img\\real.png", b"\x89PNGdata")])
        _write_mdx(
            tmp_path / "ghost.mdx",
            [("entry", b'<a href="sound://audio/ghost.ogg">play</a>')],
        )
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "ghost.ogg" in out
        assert "broken sound reference" in out

    def test_backslash_reference_resolves(self, tmp_path, capsys):
        _write_mdd(tmp_path / "ok.mdd", [("\\audio\\word.bin", b"\x00\x01binary")])
        _write_mdx(
            tmp_path / "ok.mdx",
            [("entry", b'<a href="sound://\\audio\\word.bin">play</a>')],
        )
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "family ok (v2.0): OK" in out


class TestDecodeChecks:
    def test_corrupted_mp3_fails_decode(self, tmp_path, mdd_records, capsys):
        payload = mdd_records["/audio/voice.mp3"]
        corrupted = payload[:10] + b"\x00\x01\x02garbage-not-frames"
        _write_mdd(tmp_path / "broken.mdd", [("\\audio\\broken.mp3", corrupted)])
        _write_mdx(tmp_path / "broken.mdx", [("k", b"<div>x</div>")])
        rc = main(["verify", str(tmp_path), "--decode"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "not decodable" in out
        assert "broken.mp3" in out


class TestVerifyEndToEnd:
    def test_convert_inspect_verify_chain(self, supported_family, tmp_path, capsys):
        def digests():
            return {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(supported_family.iterdir())
            }

        before = digests()
        out = tmp_path / "converted"
        assert main(["convert", str(supported_family), "--out-dir", str(out)]) == 0
        assert main(["inspect", str(out)]) == 0
        assert main(["verify", str(out)]) == 0
        out_text = capsys.readouterr().out
        assert "family testdict (v2.0): OK" in out_text
        assert digests() == before


class TestSmokeTestDoc:
    def test_smoke_test_documented(self):
        doc = Path(__file__).resolve().parents[1] / "docs" / "smoke-test.md"
        text = doc.read_text(encoding="utf-8")
        assert "GoldenDict" in text
        assert "MDict" in text
        assert "convert" in text
        assert "verify" in text
        assert "Pass criteria" in text


class TestFullProblemReporting:
    def test_utf16_mdx_sound_refs_are_verified(self, tmp_path):
        from mdict_audio import family as family_mod
        from mdict_audio.commands.verify import verify_family
        from mdict_audio.container.writer import write_mdict

        with (tmp_path / "utf16.mdx").open("wb") as f:
            write_mdict(
                f,
                [("entry", '<a href="sound://audio/missing.ogg">x</a>')],
                is_mdd=False,
                encoding="UTF-16",
            )

        problems = verify_family(family_mod.discover(tmp_path)["utf16"])
        assert any("audio/missing.ogg" in p for p in problems)

    def test_duplicate_keys_are_not_problems(self, tmp_path, capsys):
        from mdict_audio.container.writer import write_mdict

        with (tmp_path / "dup.mdx").open("wb") as f:
            write_mdict(
                f,
                [("alpha", b"<div>1</div>"), ("alpha", b"<div>2</div>")],
                is_mdd=False,
            )
        with (tmp_path / "dup.mdd").open("wb") as f:
            write_mdict(f, [("\\x\\a.bin", b"data")], is_mdd=True)
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "duplicate" not in out

    def test_empty_sound_refs_reported(self, tmp_path, mdd_records, capsys):
        from mdict_audio.container.writer import write_mdict

        entry = b'<div><a href="sound://">empty</a> <a href="sound://audio/hello.ogg">ok</a></div>'
        with (tmp_path / "emp.mdx").open("wb") as f:
            write_mdict(f, [("k", entry)], is_mdd=False)
        with (tmp_path / "emp.mdd").open("wb") as f:
            write_mdict(
                f,
                [("\\audio\\hello.ogg", mdd_records["/audio/hello.ogg"])],
                is_mdd=True,
            )
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "empty sound reference" in out
        assert "1 occurrence(s)" in out
        assert "broken" not in out

    def test_no_false_duplicates_on_healthy_family(self, supported_family, capsys):
        rc = main(["verify", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "duplicate" not in out
        assert "empty sound" not in out


class TestLightweightVerify:
    def test_default_no_ffmpeg_calls(self, supported_family, monkeypatch):
        from mdict_audio.audio import ffmpeg as ffmpeg_mod

        calls = []
        real = ffmpeg_mod.decode_ok

        def spy(data, fmt=None):
            calls.append(fmt)
            return real(data, fmt)

        monkeypatch.setattr(ffmpeg_mod, "decode_ok", spy)
        rc = main(["verify", str(supported_family)])
        assert rc == 0
        assert calls == []

    def test_decode_flag_triggers_backend(self, supported_family, monkeypatch):
        from mdict_audio.audio import ffmpeg as ffmpeg_mod

        calls = []
        real = ffmpeg_mod.decode_ok

        def spy(data, fmt=None):
            calls.append(fmt)
            return real(data, fmt)

        monkeypatch.setattr(ffmpeg_mod, "decode_ok", spy)
        rc = main(["verify", str(supported_family), "--decode", "--engine", "ffmpeg"])
        assert rc == 0
        assert len(calls) > 0

    def test_decode_flag_pyav_engine(self, supported_family):
        pytest.importorskip("av")
        rc = main(["verify", str(supported_family), "--decode", "--engine", "pyav"])
        assert rc == 0

    def test_extension_mismatch_detected(self, tmp_path, mdd_records, capsys):
        from mdict_audio.container.writer import write_mdict

        ogg_payload = mdd_records["/audio/hello.ogg"]
        with (tmp_path / "mism.mdd").open("wb") as f:
            write_mdict(f, [("\\audio\\fake.mp3", ogg_payload)], is_mdd=True)
        with (tmp_path / "mism.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "extension mismatch" in out
        assert "fake.mp3" in out
        assert "content is ogg" in out

    def test_spx_ogg_not_mismatch(self, tmp_path, mdd_records, capsys):
        from mdict_audio.container.writer import write_mdict

        ogg_payload = mdd_records["/audio/hello.ogg"]
        with (tmp_path / "spx.mdd").open("wb") as f:
            write_mdict(f, [("\\audio\\word.spx", ogg_payload)], is_mdd=True)
        with (tmp_path / "spx.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)
        rc = main(["verify", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "mismatch" not in out

    def test_correct_extension_no_mismatch(self, supported_family, capsys):
        rc = main(["verify", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "extension mismatch" not in out

    def test_decode_reports_unknown_format_audio(self, tmp_path, capsys):
        """--decode reports unrecognized audio-ext content as not decodable."""
        with (tmp_path / "unk.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)
        with (tmp_path / "unk.mdd").open("wb") as f:
            write_mdict(f, [(r"\audio\broken.mp3", b"\x00" * 100)], is_mdd=True)

        # Non-decode: unknown format with audio ext is skipped
        rc = main(["verify", str(tmp_path)])
        assert rc == 0
        assert "not decodable" not in capsys.readouterr().out

        # Decode: garbage content with .mp3 ext is reported
        rc = main(["verify", str(tmp_path), "--decode"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "not decodable" in out
        assert "broken.mp3" in out
