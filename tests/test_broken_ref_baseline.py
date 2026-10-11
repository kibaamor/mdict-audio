import json

import pytest

from mdict_audio.cli import main
from mdict_audio.container.writer import write_mdict
from mdict_audio.refs import classify_refs, normalize_ref


def test_classify_source_broken():
    data = b'<a href="sound://audio/missing.ogg">play</a>'
    index = {normalize_ref("\\audio\\hello.ogg")}
    assert classify_refs(data, data, index, index) == (1, 0)


def test_classify_introduced_broken():
    orig = b'<a href="sound://audio/hello.ogg">play</a>'
    rewritten = b'<a href="sound://audio/broken.mp3">play</a>'
    orig_index = {normalize_ref("\\audio\\hello.ogg")}
    final_index = {normalize_ref("\\audio\\hello.mp3")}
    assert classify_refs(orig, rewritten, orig_index, final_index) == (0, 1)


def test_classify_healthy():
    data = b'<a href="sound://audio/hello.ogg">play</a>'
    orig_index = {normalize_ref("\\audio\\hello.ogg")}
    final_index = {normalize_ref("\\audio\\hello.mp3")}
    rewritten = b'<a href="sound://audio/hello.mp3">play</a>'
    assert classify_refs(data, rewritten, orig_index, final_index) == (0, 0)


def test_classify_empty_refs_not_counted():
    data = b'<a href="sound://">play</a>'
    assert classify_refs(data, data, set(), set()) == (0, 0)


@pytest.fixture
def broken_ref_family(tmp_path, mdd_records):
    dicts = tmp_path / "dicts"
    dicts.mkdir()
    with (dicts / "broken.mdd").open("wb") as f:
        write_mdict(
            f,
            [("\\audio\\hello.ogg", mdd_records["/audio/hello.ogg"])],
            is_mdd=True,
        )
    with (dicts / "broken.mdx").open("wb") as f:
        write_mdict(
            f,
            [
                ("entry1", b'<div>ok <a href="sound://audio/hello.ogg">p</a></div>'),
                (
                    "entry2",
                    b'<div>bad <a href="sound://audio/missing.ogg">p</a></div>',
                ),
            ],
            is_mdd=False,
        )
    return dicts


class TestBaselineE2E:
    def test_pre_existing_broken_recorded(self, broken_ref_family, tmp_path):
        out = tmp_path / "out"
        rc = main(["convert", str(broken_ref_family), "--out-dir", str(out)])
        assert rc == 0
        manifest = json.loads(
            (out / "broken.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["broken_refs_pre_existing"] == 1
        assert manifest["stats"]["broken_refs_introduced"] == 0

    def test_healthy_family_clean_baseline(self, supported_family, tmp_path):
        out = tmp_path / "out"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["broken_refs_pre_existing"] == 0
        assert manifest["stats"]["broken_refs_introduced"] == 0

    def test_introduced_warning_fires(
        self, supported_family, tmp_path, monkeypatch, capsys
    ):
        from mdict_audio.pipeline import mdx

        monkeypatch.setattr(mdx, "classify_refs", lambda *a, **k: (0, 1))
        out = tmp_path / "out"
        rc = main(["convert", str(supported_family), "--out-dir", str(out)])
        assert rc == 0
        manifest = json.loads(
            (out / "testdict.manifest.json").read_text(encoding="utf-8")
        )
        n = manifest["stats"]["broken_refs_introduced"]
        assert n >= 1
        assert (
            "introduced %d broken reference(s) during rewrite" % n
        ) in capsys.readouterr().out


@pytest.fixture
def collision_family(tmp_path, mdd_records):
    dicts = tmp_path / "dicts"
    dicts.mkdir()
    entries = [
        ("\\audio\\a.mp3", mdd_records["/audio/a.mp3"]),
        ("\\audio\\a.ogg", mdd_records["/audio/a.ogg"]),
    ]
    with (dicts / "collision.mdd").open("wb") as f:
        write_mdict(f, entries, is_mdd=True)
    with (dicts / "collision.mdx").open("wb") as f:
        write_mdict(
            f,
            [
                (
                    "entry1",
                    b'<div><a href="sound://audio/a.ogg">1</a>'
                    b'<a href="sound://audio/a.mp3">2</a></div>',
                ),
            ],
            is_mdd=False,
        )
    return dicts


class TestCollisionRefSafety:
    @pytest.mark.parametrize("strategy", ["skip", "overwrite"])
    def test_collision_keeps_refs_resolvable(
        self, collision_family, tmp_path, strategy, capsys
    ):
        out = tmp_path / ("out-" + strategy)
        rc = main(
            [
                "convert",
                str(collision_family),
                "--out-dir",
                str(out),
                "--on-collision",
                strategy,
                "--engine",
                "ffmpeg",
            ]
        )
        assert rc == 0
        manifest = json.loads(
            (out / "collision.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["stats"]["broken_refs_pre_existing"] == 0
        assert manifest["stats"]["broken_refs_introduced"] == 0
        assert main(["verify", str(out)]) == 0
        capsys.readouterr()
