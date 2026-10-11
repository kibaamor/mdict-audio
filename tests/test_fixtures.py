from mdict_utils import reader


def norm_keys(path):
    return [k.replace("\\", "/").lstrip("/") for k in reader.get_keys(str(path))]


def test_supported_family_fixture_is_valid(supported_family):
    mdx = supported_family / "testdict.mdx"
    mdd = supported_family / "testdict.mdd"
    assert mdx.is_file() and mdd.is_file()
    assert mdx.stat().st_size > 0 and mdd.stat().st_size > 0

    meta = reader.meta(str(mdx))
    assert str(meta["version"]).startswith("2")
    assert meta["encrypted"] == "No"

    assert set(norm_keys(mdx)) == {"hello", "world", "plain", "clash", "voice"}

    mdd_keys = set(norm_keys(mdd))
    assert {
        "audio/hello.ogg", "audio/world.ogg", "audio/a.ogg", "audio/a.mp3",
        "audio/voice.mp3", "audio/wave.wav", "audio/beep.m4a",
        "img/logo.png", "css/style.css",
    } <= mdd_keys


def test_multi_family_fixture_has_two_families(multi_family_dir):
    assert (multi_family_dir / "testdict.mdx").is_file()
    assert (multi_family_dir / "collins.mdx").is_file()
    assert (multi_family_dir / "testdict.mdd").is_file()
