import struct
import zlib

import pytest
from conftest import make_stub_mdx_bytes

from mdict_audio.container.collation import check_key_order
from mdict_audio.container.reader import (
    CorruptContainerError,
    MDictReader,
    UnsupportedContainerError,
    _decode_block,
)
from mdict_audio.container.writer import write_mdict


def _stub_mdx(path, version="2.0", encrypted="No", encoding="UTF-8"):
    path.write_bytes(make_stub_mdx_bytes(version, encrypted, encoding))


def _patched_copy(src, field_index, value):
    data = bytearray(src.read_bytes())
    header_len = struct.unpack(">I", data[:4])[0]
    key_start = 4 + header_len + 4
    offset = key_start + field_index * 8
    data[offset : offset + 8] = struct.pack(">Q", value)
    adler = zlib.adler32(bytes(data[key_start : key_start + 40])) & 0xFFFFFFFF
    data[key_start + 40 : key_start + 44] = struct.pack(">I", adler)
    return bytes(data)


class TestScopeAndBounds:
    def test_rejects_mdict_3_0(self, tmp_path):
        p = tmp_path / "v3.mdx"
        _stub_mdx(p, version="3.0")
        with pytest.raises(UnsupportedContainerError, match="2.0"):
            MDictReader(p)

    def test_rejects_mdict_1_2(self, tmp_path):
        p = tmp_path / "v12.mdx"
        _stub_mdx(p, version="1.2")
        with pytest.raises(UnsupportedContainerError, match="2.0"):
            MDictReader(p)

    def test_encrypted_flag_2_passes_scope(self, tmp_path):
        p = tmp_path / "enc.mdx"
        _stub_mdx(p, encrypted="2")
        with pytest.raises(CorruptContainerError) as exc:
            MDictReader(p)
        assert "user-encrypted" not in str(exc.value)

    def test_utf16_le_encoding_alias_passes_scope(self, tmp_path):
        p = tmp_path / "utf16le.mdx"
        _stub_mdx(p, encoding="UTF-16-LE")
        with pytest.raises(CorruptContainerError) as exc:
            MDictReader(p)
        assert "unsupported key encoding" not in str(exc.value)

    def test_rejects_encrypted_yes(self, tmp_path):
        p = tmp_path / "enc.mdx"
        _stub_mdx(p, encrypted="Yes")
        with pytest.raises(UnsupportedContainerError, match="encrypted"):
            MDictReader(p)

    def test_lzo_block_rejected(self):
        with pytest.raises(UnsupportedContainerError, match="compression"):
            _decode_block(struct.pack("<L", 1) + b"\x00" * 4 + b"payload", 7)

    def test_oversized_declaration_fails_as_family_error(
        self, supported_family, tmp_path
    ):
        src = supported_family / "testdict.mdx"
        patched = tmp_path / "oversize.mdx"
        patched.write_bytes(_patched_copy(src, 3, 1 << 40))
        with pytest.raises(CorruptContainerError, match="exceeds"):
            MDictReader(patched)

    def test_oversized_key_count_declaration(self, supported_family, tmp_path):
        src = supported_family / "testdict.mdx"
        patched = tmp_path / "bigcount.mdx"
        patched.write_bytes(_patched_copy(src, 0, 1 << 40))
        with pytest.raises(CorruptContainerError):
            MDictReader(patched)


class TestRecordIteration:
    def test_reader_enumerates_mdx_records(self, supported_family):
        reader = MDictReader(supported_family / "testdict.mdx")
        keys = reader.keys()
        assert sorted(keys) == ["clash", "hello", "plain", "voice", "world"]
        records = dict(reader.iter_records())
        assert b"sound://audio/hello.ogg" in records["hello"]
        assert records["plain"].rstrip(b"\n") == b"<div>no audio</div>"
        assert dict(reader.iter_records()) == records

    def test_reader_enumerates_mdd_records(self, supported_family):
        reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        records = dict(reader.iter_records())
        normalized = {k.replace("\\", "/"): v for k, v in records.items()}
        assert normalized["/audio/hello.ogg"].startswith(b"OggS")
        assert (
            normalized["/audio/voice.mp3"].startswith(b"ID3")
            or normalized["/audio/voice.mp3"][:2] == b"\xff\xfb"
        )
        assert normalized["/img/logo.png"].startswith(b"\x89PNG")
        assert normalized["/css/style.css"] == b"body{color:#333}"

    def test_reader_matches_reference_mdx(self, supported_family):
        from mdict_utils.base.readmdict import MDX

        ours = dict(MDictReader(supported_family / "testdict.mdx").iter_records())
        ref = {
            k.decode(): v
            for k, v in MDX(str(supported_family / "testdict.mdx")).items()
        }
        assert ours == ref

    def test_reader_matches_reference_mdd(self, supported_family):
        from mdict_utils.base.readmdict import MDD

        ours = dict(
            MDictReader(supported_family / "testdict.mdd", is_mdd=True).iter_records()
        )
        ref = {
            k.decode(): v
            for k, v in MDD(str(supported_family / "testdict.mdd")).items()
        }
        assert ours == ref


class TestWriterRoundtrip:
    def test_mdx_roundtrip_via_reference_readback(self, supported_family, tmp_path):
        from mdict_utils.base.readmdict import MDX

        src = MDictReader(supported_family / "testdict.mdx")
        entries = list(src.iter_records())
        out = tmp_path / "rt.mdx"
        with out.open("wb") as f:
            write_mdict(f, entries, is_mdd=False, title="roundtrip", description="test")
        ref = {k.decode(): v for k, v in MDX(str(out)).items()}
        assert ref == dict(entries)
        assert dict(MDictReader(out).iter_records()) == dict(entries)

    def test_mdd_roundtrip_via_reference_readback(self, supported_family, tmp_path):
        from mdict_utils.base.readmdict import MDD

        src = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        entries = list(src.iter_records())
        out = tmp_path / "rt.mdd"
        with out.open("wb") as f:
            write_mdict(f, entries, is_mdd=True)
        ref = {k.decode(): v for k, v in MDD(str(out)).items()}
        assert ref == dict(entries)
        assert dict(MDictReader(out, is_mdd=True).iter_records()) == dict(entries)

    def test_write_mdict_preserves_header_attributes(self, tmp_path):
        """write_mdict(header=...) preserves source MDX attributes."""
        path = tmp_path / "styled.mdx"
        with path.open("wb") as f:
            write_mdict(
                f,
                [("key", b"<div>x</div>")],
                is_mdd=False,
                header={
                    "StyleSheet": "/css/app.css",
                    "Stripkey": "No",
                    "KeyCaseSensitive": "Yes",
                },
            )
        reader = MDictReader(path, is_mdd=False)
        assert reader.header["StyleSheet"] == "/css/app.css"
        assert reader.header["Stripkey"] == "No"
        assert reader.header["KeyCaseSensitive"] == "Yes"

    def test_write_mdict_without_header_uses_defaults(self, tmp_path):
        """Without header param, defaults match previous hardcoded values."""
        path = tmp_path / "default.mdx"
        with path.open("wb") as f:
            write_mdict(f, [("key", b"<div>x</div>")], is_mdd=False)
        reader = MDictReader(path, is_mdd=False)
        assert reader.header["StyleSheet"] == ""
        assert reader.header["Stripkey"] == "Yes"
        assert reader.header["KeyCaseSensitive"] == "No"


class TestKeyRename:
    def test_renamed_mdd_key_stays_readable_and_sorted(
        self, supported_family, tmp_path
    ):
        from mdict_utils.base.readmdict import MDD

        src = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        entries = []
        for key, data in src.iter_records():
            if key == "\\audio\\world.ogg":
                key = "\\audio\\world.mp3"
            entries.append((key, data))
        out = tmp_path / "renamed.mdd"
        with out.open("wb") as f:
            write_mdict(f, entries, is_mdd=True)
        reader = MDictReader(out, is_mdd=True)
        keys = reader.keys()
        assert "\\audio\\world.mp3" in keys
        assert "\\audio\\world.ogg" not in keys
        assert check_key_order(keys, is_mdd=True)
        ref_keys = {k.decode() for k in MDD(str(out)).keys()}
        assert ref_keys == set(keys)
        ref_items = {k.decode(): v for k, v in MDD(str(out)).items()}
        assert ref_items == dict(reader.iter_records())


class TestContainerChecks:
    def test_check_key_order_detects_unsorted_mdd(self):
        assert check_key_order(["a.ogg", "b.ogg", "c.mp3"], is_mdd=True)
        assert not check_key_order(["B.ogg", "a.ogg"], is_mdd=True)

    def test_check_key_order_detects_unsorted_mdx(self):
        assert not check_key_order(["Word", "apple"], is_mdd=False)

    def test_fixture_keys_are_sorted(self, supported_family):
        mdx = MDictReader(supported_family / "testdict.mdx")
        assert check_key_order(mdx.keys(), is_mdd=False)
        mdd = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        assert check_key_order(mdd.keys(), is_mdd=True)

    def test_unsorted_written_file_detected(self, tmp_path):
        entries = [("\\B.ogg", b"x"), ("\\a.ogg", b"y")]
        out = tmp_path / "unsorted.mdd"
        with out.open("wb") as f:
            write_mdict(f, entries, is_mdd=True, sort_entries=False)
        reader = MDictReader(out, is_mdd=True)
        assert reader.keys() == ["\\B.ogg", "\\a.ogg"]
        assert not check_key_order(reader.keys(), is_mdd=True)

    def test_corrupted_key_block_fails(self, supported_family, tmp_path):
        data = bytearray((supported_family / "testdict.mdx").read_bytes())
        header_len = struct.unpack(">I", data[:4])[0]
        key_info_frame = 4 + header_len + 4 + 44
        data[key_info_frame + 9] ^= 0xFF
        out = tmp_path / "corrupt.mdx"
        out.write_bytes(bytes(data))
        with pytest.raises(CorruptContainerError):
            MDictReader(out)

    def test_record_entry_count_mismatch_detected(self, supported_family, tmp_path):
        src = MDictReader(supported_family / "testdict.mdx")
        entries = list(src.iter_records())
        out = tmp_path / "rt.mdx"
        with out.open("wb") as f:
            write_mdict(f, entries, is_mdd=False)
        data = bytearray(out.read_bytes())
        record_start = src._record_start
        data[record_start + 8 : record_start + 16] = struct.pack(">Q", 999)
        out2 = tmp_path / "badcount.mdx"
        out2.write_bytes(bytes(data))
        with pytest.raises(CorruptContainerError, match="count"):
            list(MDictReader(out2).iter_records())
