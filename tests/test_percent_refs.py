
from mdict_audio.refs import (
    build_match_index,
    resolve_ref,
    rewrite_sound_refs,
)


class TestPercentReferenceLadder:
    def test_exact_match_first(self):
        index = {"audio/a b.spx": "audio/a b.mp3"}
        assert resolve_ref("audio/a b.spx", index) == ("audio/a b.spx", None)

    def test_percent20_decoded_match(self):
        index = {"audio/a b.spx": "audio/a b.mp3"}
        assert resolve_ref("audio/a%20b.spx", index) == ("audio/a b.spx", "utf-8")

    def test_gbk_percent_decoded(self):
        index = {"audio/\u4e2d.spx": "audio/\u4e2d.mp3"}
        ref = "audio/%D6%D0.spx"
        assert resolve_ref(ref, index) == ("audio/\u4e2d.spx", "gb18030")

    def test_big5_percent_decoded(self):
        index = {"\u4e2d\u6587.ogg": "\u4e2d\u6587.mp3"}
        ref = "%A4%A4%A4%E5.ogg"
        assert resolve_ref(ref, index) == ("\u4e2d\u6587.ogg", "big5")

    def test_big5_ladder_falls_through_from_gb18030(self):
        index = {"\u4e2d\u6587.ogg": "\u4e2d\u6587.mp3"}
        ref = "%D6%D0%CE%C4.ogg"
        assert resolve_ref(ref, index) == ("\u4e2d\u6587.ogg", "gb18030")

    def test_utf8_percent_decoded(self):
        index = {"audio/\u4e2d.spx": "audio/\u4e2d.mp3"}
        assert resolve_ref("audio/%E4%B8%AD.spx", index) == (
            "audio/\u4e2d.spx",
            "utf-8",
        )

    def test_all_misses_return_none(self):
        assert resolve_ref("audio/ghost%20x.spx", {"audio/other.spx": "x"}) == (
            None,
            None,
        )
        assert resolve_ref("plain", set()) == (None, None)

    def test_exact_priority_over_decoded_key(self):
        index = {"a%20b.spx": "one", "a b.spx": "two"}
        assert resolve_ref("a%20b.spx", index) == ("a%20b.spx", None)

    def test_decoded_then_renormalized(self):
        index = {"audio/case.spx": "audio/case.mp3"}
        assert resolve_ref("audio%5Ccase.spx", index) == ("audio/case.spx", "utf-8")

    def test_stray_percent_untouched(self):
        r = resolve_ref("audio/100%.mp3", {"audio/100%.mp3": "x"})
        assert r == ("audio/100%.mp3", None)
        r = resolve_ref("audio/100%.mp3", {"audio/other.mp3": "x"})
        assert r == (None, None)

    def test_double_encoding_decodes_once(self):
        index = {"a%20b.spx": "x"}
        assert resolve_ref("a%2520b.spx", index) == ("a%20b.spx", "utf-8")

    def test_plus_is_literal(self):
        index = {"audio/a+b.spx": "x"}
        assert resolve_ref("audio/a+b.spx", index) == ("audio/a+b.spx", None)
        assert resolve_ref("audio/a+b.spx", {"audio/a b.spx": "x"}) == (None, None)

    def test_mixed_literal_and_encoded(self):
        index = {"audio/M\xfcller x.spx": "x"}
        r = resolve_ref("audio/M\xfcller%20x.spx", index)
        assert r == ("audio/M\xfcller x.spx", "utf-8")


class TestPercentReferenceRewriteStyle:
    def _index(self):
        return build_match_index({"\\audio\\a b.spx": "\\audio\\a b.mp3"})

    def test_decoded_hit_rewrites_percent_encoded(self):
        rec = b'<a href="sound://audio/a%20b.spx">p</a>'
        out = rewrite_sound_refs(rec, self._index())
        assert b"sound://audio/a%20b.mp3" in out
        assert b"spx" not in out

    def test_exact_hit_keeps_path_style(self):
        index = build_match_index({"\\audio\\ab.spx": "\\audio\\ab.mp3"})
        rec = b'<a href="sound://audio/ab.spx">p</a>'
        out = rewrite_sound_refs(rec, index)
        assert b"sound://audio/ab.mp3" in out

    def test_unmatched_ref_unchanged(self):
        rec = b'<a href="sound://audio/ghost%20x.spx">p</a>'
        assert rewrite_sound_refs(rec, self._index()) == rec

    def test_literal_space_ref_cannot_match_by_regex_design(self):
        rec = b'<a href="sound://audio/a b.spx">p</a>'
        out = rewrite_sound_refs(rec, self._index())
        assert out == rec


class TestGbRkencoding:
    def test_gbk_percent_ref_rewrites_in_gbk(self):
        index = build_match_index({"\\audio\\\u4e2d.spx": "\\audio\\\u4e2d.mp3"})
        ref = "audio/%D6%D0.spx"
        rec = ('<a href="sound://%s">p</a>' % ref).encode()
        out = rewrite_sound_refs(rec, index)
        assert b"sound://audio/%D6%D0.mp3" in out
        assert b"%E4%B8%AD" not in out

    def test_utf8_percent_ref_rewrites_in_utf8(self):
        index = build_match_index({"\\audio\\\u4e2d.spx": "\\audio\\\u4e2d.mp3"})
        rec = b'<a href="sound://audio/%E4%B8%AD.spx">p</a>'
        out = rewrite_sound_refs(rec, index)
        assert b"sound://audio/%E4%B8%AD.mp3" in out
        assert b"%D6%D0" not in out

    def test_percent20_identical_in_both_encodings(self):
        index = build_match_index({"\\audio\\a b.spx": "\\audio\\a b.mp3"})
        rec = b'<a href="sound://audio/a%20b.spx">p</a>'
        out = rewrite_sound_refs(rec, index)
        assert b"sound://audio/a%20b.mp3" in out
