import pytest

from mdict_audio.audio.ffmpeg import TranscodeError
from mdict_audio.audio.sniff import sniff_format
from mdict_audio.container.reader import MDictReader
from mdict_audio.container.writer import write_mdict
from mdict_audio.pipeline.mdx import convert_mdx
from mdict_audio.pipeline.transcode import convert_mdd_volumes
from mdict_audio.refs import (
    build_match_index,
    extract_sound_refs,
    plan_renames_by_format,
    replace_ext,
    resolve_collisions,
    rewrite_sound_refs,
)


def _fixture_records(supported_family):
    reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
    return list(reader.iter_records())


def _plan_renames(records, target="mp3", force=False):
    return plan_renames_by_format(
        ((key, sniff_format(data)) for key, data in records), target, force
    )


class TestRenameMap:
    def test_non_mp3_audio_maps_to_mp3(self, supported_family):
        records = _fixture_records(supported_family)
        rename_map, transcode = _plan_renames(records)
        assert rename_map["\\audio\\hello.ogg"] == "\\audio\\hello.mp3"
        assert rename_map["\\audio\\world.ogg"] == "\\audio\\world.mp3"
        assert rename_map["\\audio\\a.ogg"] == "\\audio\\a.mp3"
        assert rename_map["\\audio\\wave.wav"] == "\\audio\\wave.mp3"
        assert rename_map["\\audio\\beep.m4a"] == "\\audio\\beep.mp3"

    def test_already_mp3_and_non_audio_unchanged(self, supported_family):
        records = _fixture_records(supported_family)
        rename_map, transcode = _plan_renames(records)
        assert "\\audio\\voice.mp3" not in rename_map
        assert "\\audio\\a.mp3" not in rename_map
        assert "\\img\\logo.png" not in rename_map
        assert "\\css\\style.css" not in rename_map
        assert "\\audio\\voice.mp3" not in transcode
        assert "\\img\\logo.png" not in transcode

    def test_replace_ext_preserves_separator_style(self):
        assert replace_ext("\\audio\\a.ogg", ".mp3") == "\\audio\\a.mp3"
        assert replace_ext("audio/a.ogg", ".mp3") == "audio/a.mp3"
        assert replace_ext("a.ogg", ".mp3") == "a.mp3"
        assert replace_ext("noext", ".mp3") == "noext.mp3"


class TestCollisionSafety:
    def test_collision_gets_safe_suffix_and_existing_target_kept(self):
        all_keys = ["\\audio\\a.ogg", "\\audio\\a.mp3", "\\audio\\b.ogg"]
        rename_map = {
            "\\audio\\a.ogg": "\\audio\\a.mp3",
            "\\audio\\b.ogg": "\\audio\\b.mp3",
        }
        resolved, collisions, dropped, skipped = resolve_collisions(
            rename_map, all_keys
        )
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.converted-2.mp3"
        assert resolved["\\audio\\b.ogg"] == "\\audio\\b.mp3"
        assert collisions == [
            (
                "\\audio\\a.ogg",
                "\\audio\\a.mp3",
                "renamed",
                "\\audio\\a.converted-2.mp3",
            )
        ]
        assert dropped == set() and skipped == set()

    def test_family_level_collision_across_volumes(self):
        all_keys = ["\\audio\\a.ogg", "\\audio\\a.mp3"]
        rename_map = {"\\audio\\a.ogg": "\\audio\\a.mp3"}
        resolved, _, _, _ = resolve_collisions(rename_map, all_keys)
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.converted-2.mp3"


class TestCollisionStrategies:
    def test_overwrite_takes_the_name_and_drops_victim(self):
        all_keys = ["\\audio\\a.ogg", "\\audio\\a.mp3"]
        rename_map = {"\\audio\\a.ogg": "\\audio\\a.mp3"}
        resolved, collisions, dropped, skipped = resolve_collisions(
            rename_map, all_keys, "overwrite"
        )
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.mp3"
        assert dropped == {"\\audio\\a.mp3"}
        assert skipped == set()
        assert collisions == [
            ("\\audio\\a.ogg", "\\audio\\a.mp3", "overwritten", "\\audio\\a.mp3")
        ]

    def test_skip_keeps_existing_and_drops_challenger(self):
        all_keys = ["\\audio\\a.ogg", "\\audio\\a.mp3"]
        rename_map = {"\\audio\\a.ogg": "\\audio\\a.mp3"}
        resolved, collisions, dropped, skipped = resolve_collisions(
            rename_map, all_keys, "skip"
        )
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.mp3"
        assert skipped == {"\\audio\\a.ogg"}
        assert dropped == set()
        assert collisions == [
            ("\\audio\\a.ogg", "\\audio\\a.mp3", "skipped", "\\audio\\a.mp3")
        ]

    def test_multi_challenger_overwrite_first_wins_rest_rename(self):
        all_keys = ["\\audio\\a.mp3", "\\audio\\a.ogg", "\\audio\\a.wav"]
        rename_map = {
            "\\audio\\a.ogg": "\\audio\\a.mp3",
            "\\audio\\a.wav": "\\audio\\a.mp3",
        }
        resolved, collisions, dropped, skipped = resolve_collisions(
            rename_map, all_keys, "overwrite"
        )
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.mp3"
        assert resolved["\\audio\\a.wav"] == "\\audio\\a.converted-2.mp3"
        assert dropped == {"\\audio\\a.mp3"}
        actions = [c[2] for c in collisions]
        assert actions == ["overwritten", "renamed"]

    def test_multi_challenger_skip_unlimited(self):
        all_keys = ["\\audio\\a.mp3", "\\audio\\a.ogg", "\\audio\\a.wav"]
        rename_map = {
            "\\audio\\a.ogg": "\\audio\\a.mp3",
            "\\audio\\a.wav": "\\audio\\a.mp3",
        }
        resolved, collisions, dropped, skipped = resolve_collisions(
            rename_map, all_keys, "skip"
        )
        assert resolved["\\audio\\a.ogg"] == "\\audio\\a.mp3"
        assert resolved["\\audio\\a.wav"] == "\\audio\\a.mp3"
        assert skipped == {"\\audio\\a.ogg", "\\audio\\a.wav"}
        assert all(c[2] == "skipped" for c in collisions)

    def test_unknown_collision_strategy_rejected(self):
        with pytest.raises(ValueError, match="unknown collision strategy"):
            resolve_collisions({"\\audio\\a.ogg": "\\audio\\a.mp3"}, [], "bogus")


class TestSoundRewrite:
    def _index(self):
        return build_match_index(
            {
                "\\audio\\hello.ogg": "\\audio\\hello.mp3",
                "\\audio\\world.ogg": "\\audio\\world.mp3",
            }
        )

    def test_forward_slash_reference_rewritten(self):
        rec = b'<div><a href="sound://audio/hello.ogg">play</a></div>'
        out = rewrite_sound_refs(rec, self._index())
        assert b"sound://audio/hello.mp3" in out
        assert b"hello.ogg" not in out

    def test_backslash_reference_rewritten_in_its_own_style(self):
        rec = b'<div><a href="sound://\\audio\\world.ogg">play</a></div>'
        out = rewrite_sound_refs(rec, self._index())
        assert b"sound://\\audio\\world.mp3" in out
        assert b"world.ogg" not in out

    def test_unknown_reference_left_alone(self):
        rec = b'<a href="sound://audio/missing.ogg">x</a>'
        out = rewrite_sound_refs(rec, self._index())
        assert out == rec

    def test_utf16_reference_rewritten(self):
        rec = '<a href="sound://audio/hello.ogg">x</a>'.encode("utf-16-le")
        out = rewrite_sound_refs(rec, self._index(), encoding="utf-16-le")
        assert "sound://audio/hello.mp3".encode("utf-16-le") in out
        assert "sound://audio/hello.ogg".encode("utf-16-le") not in out
        assert extract_sound_refs(out, encoding="utf-16-le") == ["audio/hello.mp3"]

    def test_text_path_keeps_non_ascii_space_in_filename(self):
        space = "\u3000"
        index = build_match_index({"audio/a%sb.ogg" % space: "audio/a%sb.mp3" % space})
        rec = ('<a href="sound://audio/a%sb.ogg">x</a>' % space).encode()
        out = rewrite_sound_refs(rec, index)
        assert ("sound://audio/a%sb.mp3" % space).encode() in out
        assert extract_sound_refs(out) == ["audio/a%sb.mp3" % space]

    def test_convert_mdx_uses_reader_encoding(self, tmp_path):
        src = tmp_path / "utf16.mdx"
        out = tmp_path / "out.mdx"
        with src.open("wb") as f:
            write_mdict(
                f,
                [("entry", '<a href="sound://audio/hello.ogg">x</a>')],
                is_mdd=False,
                encoding="UTF-16",
            )

        convert_mdx(MDictReader(src), {"audio/hello.ogg": "audio/hello.mp3"}, out)

        record = dict(MDictReader(out).iter_records())["entry"]
        assert "sound://audio/hello.mp3".encode("utf-16-le") in record
        assert "sound://audio/hello.ogg".encode("utf-16-le") not in record


class TestUnsupportedFormsUnchanged:
    def test_href_src_url_datauri_and_text_resources_unchanged(self):
        index = build_match_index({"\\audio\\hello.ogg": "\\audio\\hello.mp3"})
        css = b"body{background:url('audio/hello.ogg')}"
        html = (
            b'<img src="audio/hello.ogg">'
            b'<link rel="stylesheet" href="audio/hello.ogg">'
            b'<audio controls src="data:audio/ogg;base64,T2dnUw=="></audio>'
            b'<a href="entry://word">x</a>'
        )
        assert rewrite_sound_refs(css, index) == css
        assert rewrite_sound_refs(html, index) == html


class TestFailurePreservation:
    def test_failing_transcode_keeps_key_and_reference(
        self, supported_family, tmp_path, monkeypatch
    ):
        from mdict_audio.audio import ffmpeg as ffmpeg_mod
        from mdict_audio.container.collation import check_key_order

        reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        mdx_reader = MDictReader(supported_family / "testdict.mdx")
        original = dict(reader.iter_records())
        hello_payload = original["\\audio\\hello.ogg"]
        real_transcode = ffmpeg_mod.transcode

        def flaky_transcode(data, src_format, *args, **kwargs):
            if data == hello_payload:
                raise TranscodeError("boom")
            return real_transcode(data, src_format, *args, **kwargs)

        monkeypatch.setattr(ffmpeg_mod, "transcode", flaky_transcode)

        path = supported_family / "testdict.mdd"
        out_mdd = tmp_path / "out.mdd"
        out_mdx = tmp_path / "out.mdx"
        family_map, warnings, stats = convert_mdd_volumes(
            [(path, MDictReader(path, is_mdd=True))],
            {path: out_mdd},
            spill_dir=tmp_path,
            engine="ffmpeg",
        )
        entries = dict(MDictReader(out_mdd, is_mdd=True).iter_records())
        assert entries["\\audio\\hello.ogg"] == hello_payload
        assert "\\audio\\hello.ogg" not in family_map
        assert stats["failed"] == 1
        assert stats["transcoded"] >= 3
        assert any("hello.ogg" in w and "kept original" in w for w in warnings)
        assert check_key_order(list(entries), is_mdd=True)

        convert_mdx(mdx_reader, family_map, out_mdx, spool_dir=tmp_path)
        mdx_entries = dict(MDictReader(out_mdx).iter_records())
        assert b"sound://audio/hello.ogg" in mdx_entries["hello"]
        assert b"sound://\\audio\\world.mp3" in mdx_entries["world"]
        assert b"sound://audio/voice.mp3" in mdx_entries["voice"]
