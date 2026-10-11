from conftest import make_stub_mdx_bytes

from mdict_audio.cli import main


def test_inspect_reports_support_and_audio_counts(supported_family, capsys):
    rc = main(["inspect", str(supported_family)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "family testdict" in out
    assert "testdict.mdx" in out
    assert "supported" in out
    assert "ogg=3" in out
    assert "mp3=2" in out
    assert "wav=1" in out
    assert "m4a=1" in out
    assert "other: css=1, png=1" in out
    assert "unknown=" not in out


def test_inspect_reports_unsupported_family(tmp_path, capsys):
    (tmp_path / "weird.mdx").write_bytes(make_stub_mdx_bytes(version="3.0"))
    rc = main(["inspect", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "weird.mdx" in out
    assert "unsupported" in out
    assert "3.0" in out


def test_inspect_reports_encrypted_family(tmp_path, capsys):
    (tmp_path / "locked.mdx").write_bytes(make_stub_mdx_bytes(encrypted="Yes"))
    rc = main(["inspect", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "locked.mdx" in out
    assert "unsupported" in out
    assert "user-encrypted" in out


def test_inspect_reports_corrupt_file(tmp_path, capsys):
    (tmp_path / "broken.mdx").write_bytes(b"\x00\x01\x02garbage")
    rc = main(["inspect", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "broken.mdx" in out
    assert "corrupt" in out


class TestCorruptMddRecordSection:
    def test_corrupt_mdd_records_reported_not_crashed(self, tmp_path, capsys):
        from mdict_audio.container.reader import MDictReader
        from mdict_audio.container.writer import write_mdict

        mdd = tmp_path / "bad.mdd"
        with mdd.open("wb") as f:
            write_mdict(f, [("\\audio\\a.ogg", b"OggSdata")], is_mdd=True)
        reader = MDictReader(mdd, is_mdd=True)
        data = bytearray(mdd.read_bytes())
        data[reader._record_start + 48] ^= 0xFF
        mdd.write_bytes(bytes(data))
        rc = main(["inspect", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "bad.mdd" in out
        assert "corrupt" in out


class TestOtherHistogram:
    def test_non_audio_by_extension_and_none_extension(
        self, tmp_path, mdd_records, capsys
    ):
        from mdict_audio.container.writer import write_mdict

        entries = [
            ("\\img\\pic.jpg", b"\xff\xd8\xff\xe0junk"),
            ("\\img\\pic.jpg", b"\xff\xd8\xff\xe0junk"),
            ("\\res\\font.ttf", b"\x00\x01\x00\x00ttf"),
            ("\\plain", b"no extension here"),
            ("\\trailing.", b"dotted"),
        ]
        with (tmp_path / "res.mdd").open("wb") as f:
            write_mdict(f, entries, is_mdd=True)
        with (tmp_path / "res.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)
        rc = main(["inspect", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "other: (none)=2, jpg=2, ttf=1" in out
        assert "audio:" not in out
        assert "unknown=" not in out

    def test_audio_only_mdd_has_no_other_suffix(self, supported_family, capsys):
        rc = main(["inspect", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "other: css=1, png=1" in out


class TestVersionDisplay:
    def test_inspect_shows_version(self, supported_family, capsys):
        rc = main(["inspect", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "supported (v2.0)" in out

    def test_inspect_encrypted_shows_version(self, tmp_path, capsys):
        (tmp_path / "locked.mdx").write_bytes(make_stub_mdx_bytes(encrypted="Yes"))
        rc = main(["inspect", str(tmp_path)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "(engine v2.0)" in out
        assert "unsupported" in out

    def test_verify_family_line_shows_version(self, supported_family, capsys):
        rc = main(["verify", str(supported_family)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "family testdict (v2.0): OK" in out

    def test_convert_summary_shows_version(self, supported_family, tmp_path, capsys):
        rc = main(
            ["convert", str(supported_family), "--out-dir", str(tmp_path / "out")]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "family testdict (v2.0):" in out
