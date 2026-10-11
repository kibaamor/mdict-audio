import pytest

from mdict_audio.family import FamilyError, discover, select


def _make(tmp_path, names):
    for name in names:
        (tmp_path / name).write_bytes(b"x")


def test_single_family_with_volumes_grouped(tmp_path):
    _make(tmp_path, ["oxford.mdx", "oxford.mdd", "oxford.1.mdd", "oxford.2.mdd"])
    families = discover(tmp_path)
    assert set(families) == {"oxford"}
    fam = families["oxford"]
    assert [p.name for p in fam.mdx] == ["oxford.mdx"]
    assert [p.name for p in fam.mdd] == ["oxford.mdd", "oxford.1.mdd", "oxford.2.mdd"]


def test_year_like_stem_not_misgrouped(tmp_path):
    _make(tmp_path, ["word.2019.mdx"])
    families = discover(tmp_path)
    assert set(families) == {"word.2019"}


def test_volume_merges_when_only_bare_mdd_exists(tmp_path):
    _make(tmp_path, ["foo.mdd", "foo.1.mdd"])
    families = discover(tmp_path)
    assert set(families) == {"foo"}
    assert [p.name for p in families["foo"].mdd] == ["foo.mdd", "foo.1.mdd"]


def test_orphan_numbered_volume_stays_own_family(tmp_path):
    _make(tmp_path, ["foo.1.mdd", "foo.2.mdd"])
    families = discover(tmp_path)
    assert set(families) == {"foo.1", "foo.2"}


def test_extension_case_insensitive(tmp_path):
    _make(tmp_path, ["mixed.MDX", "mixed.mdd"])
    families = discover(tmp_path)
    assert set(families) == {"mixed"}


def test_select_auto_picks_single_family(tmp_path):
    _make(tmp_path, ["oxford.mdx", "oxford.mdd"])
    families = discover(tmp_path)
    assert set(select(families)) == {"oxford"}


def test_select_multiple_families_requires_explicit_choice(tmp_path):
    _make(tmp_path, ["oxford.mdx", "oxford.mdd", "collins.mdx", "collins.mdd"])
    families = discover(tmp_path)
    with pytest.raises(FamilyError) as exc:
        select(families)
    assert "oxford" in str(exc.value)
    assert "collins" in str(exc.value)


def test_select_requested_missing_family_fails(tmp_path):
    _make(tmp_path, ["oxford.mdx"])
    families = discover(tmp_path)
    with pytest.raises(FamilyError):
        select(families, ["nope"])


def test_select_requested_multiple_families_allowed(tmp_path):
    _make(tmp_path, ["oxford.mdx", "collins.mdx"])
    families = discover(tmp_path)
    assert set(select(families, ["oxford", "collins"])) == {"oxford", "collins"}


def test_discover_rejects_missing_directory(tmp_path):
    with pytest.raises(FamilyError):
        discover(tmp_path / "missing")
