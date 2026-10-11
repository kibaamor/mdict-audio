import os
import shutil

import pytest

from mdict_audio.cli import main
from mdict_audio.container.collation import check_key_order
from mdict_audio.container.reader import MDictReader
from mdict_audio.container.writer import write_mdict
from mdict_audio.pipeline.stores import RecordStore, RecordStoreWriter


class TestStreamingWriter:
    def test_list_and_generator_inputs_produce_identical_files(self, tmp_path):
        entries = []
        for i in range(60):
            size = [1, 100, 30000, 70000][(i // 15) % 4]
            entries.append(("\\audio\\k%03d.bin" % i, os.urandom(size)))
        with (tmp_path / "a.mdd").open("wb") as f:
            write_mdict(f, entries, is_mdd=True)
        with (tmp_path / "b.mdd").open("wb") as f:
            write_mdict(f, iter(entries), is_mdd=True, sort_entries=False)
        assert (tmp_path / "a.mdd").read_bytes() == (tmp_path / "b.mdd").read_bytes()

        reader = MDictReader(tmp_path / "b.mdd", is_mdd=True)
        records = dict(reader.iter_records())
        assert len(records) == 60
        for key, payload in entries:
            assert records[key] == payload

    def test_spool_dir_used_and_cleaned(self, tmp_path):
        spool = tmp_path / "spool"
        spool.mkdir()
        entries = [("\\a.bin", b"x" * 10), ("\\b.bin", b"y" * 200000)]
        with (tmp_path / "c.mdd").open("wb") as f:
            write_mdict(f, entries, is_mdd=True, spool_dir=spool)
        assert list(spool.iterdir()) == []


class TestRecordStores:
    def test_store_roundtrip(self, tmp_path):
        path = tmp_path / "store"
        writer = RecordStoreWriter(path)
        blobs = [os.urandom(n) for n in (0, 1, 512, 70000)]
        offsets = [writer.append(b) for b in blobs]
        writer.close()
        store = RecordStore(path)
        for (offset, length), blob in zip(offsets, blobs, strict=True):
            assert store.read(offset, length) == blob

    def test_store_reuses_open_file(self, tmp_path):
        path = tmp_path / "store"
        writer = RecordStoreWriter(path)
        first = writer.append(b"abc")
        second = writer.append(b"defgh")
        writer.close()

        with RecordStore(path) as store:
            assert store.read(*first) == b"abc"
            assert store.read(*second) == b"defgh"

        assert RecordStore(path).read(*first) == b"abc"

    def test_store_writer_context_and_idempotent_close(self, tmp_path):
        path = tmp_path / "store"
        with RecordStoreWriter(path) as writer:
            first = writer.append(b"abc")
        writer.close()

        assert RecordStore(path).read(*first) == b"abc"

        with pytest.raises(RuntimeError):
            writer.append(b"closed")

    def test_store_readback_matches_iter_records(self, supported_family, tmp_path):
        from mdict_audio.audio.sniff import sniff_format
        from mdict_audio.pipeline.stores import RecordStoreWriter

        reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
        writer = RecordStoreWriter(tmp_path / "origins.store")
        rows = []
        for key, data in reader.iter_records():
            offset, length = writer.append(data)
            rows.append((key, offset, length, sniff_format(data)))
        writer.close()
        store = RecordStore(tmp_path / "origins.store")
        original = dict(reader.iter_records())
        for key, offset, length, _fmt in rows:
            assert store.read(offset, length) == original[key]


class TestStreamingConvert:
    def test_two_volume_family_converts(self, supported_family, tmp_path, mdd_records):
        dicts = tmp_path / "dicts"
        shutil.copytree(supported_family, dicts)
        with (dicts / "testdict.1.mdd").open("wb") as f:
            write_mdict(
                f,
                [("\\audio\\zeta.ogg", mdd_records["/audio/world.ogg"])],
                is_mdd=True,
            )
        out = tmp_path / "converted"
        assert main(["convert", str(dicts), "--out-dir", str(out)]) == 0
        vol0 = MDictReader(out / "testdict.mdd", is_mdd=True)
        vol1 = MDictReader(out / "testdict.1.mdd", is_mdd=True)
        assert "\\audio\\hello.mp3" in dict(vol0.iter_records())
        zeta = dict(vol1.iter_records())
        assert "\\audio\\zeta.mp3" in zeta
        from mdict_audio.audio.sniff import sniff_format as sniff

        assert sniff(zeta["\\audio\\zeta.mp3"]) == "mp3"
        assert check_key_order(vol1.keys(), is_mdd=True)
        assert main(["verify", str(out)]) == 0

    def test_many_records_convert_streaming(self, tmp_path):
        dicts = tmp_path / "dicts"
        dicts.mkdir()
        entries = [("\\img\\blob_%05d.png" % i, os.urandom(64)) for i in range(3000)]
        with (dicts / "many.mdd").open("wb") as f:
            write_mdict(f, entries, is_mdd=True)
        with (dicts / "many.mdx").open("wb") as f:
            write_mdict(f, [("k", b"<div>x</div>")], is_mdd=False)
        out = tmp_path / "converted"
        assert main(["convert", str(dicts), "--out-dir", str(out)]) == 0
        reader = MDictReader(out / "many.mdd", is_mdd=True)
        records = dict(reader.iter_records())
        assert len(records) == 3000
        for key, payload in entries:
            assert records[key] == payload
