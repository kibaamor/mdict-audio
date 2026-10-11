import hashlib

from mdict_audio.cli import main


def _digest_dir(path):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.iterdir())
    }


def test_inspect_lists_families_without_modifying_inputs(supported_family, capsys):
    before = _digest_dir(supported_family)
    rc = main(["inspect", str(supported_family)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "testdict" in captured.out
    assert "testdict.mdx" in captured.out
    assert "testdict.mdd" in captured.out
    assert _digest_dir(supported_family) == before


def test_inspect_multiple_families_lists_all(multi_family_dir, capsys):
    rc = main(["inspect", str(multi_family_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "testdict" in out
    assert "collins" in out


def test_convert_multiple_families_fails_before_writing(
    multi_family_dir, tmp_path, capsys
):
    out_dir = tmp_path / "out"
    rc = main(["convert", str(multi_family_dir), "--out-dir", str(out_dir)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "testdict" in captured.err
    assert "collins" in captured.err
    assert "--family" in captured.err
    assert not out_dir.exists()
