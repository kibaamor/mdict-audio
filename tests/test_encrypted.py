import os

import pytest

from mdict_audio.container.crypto import (
    decrypt_key_block_info,
    fast_decrypt,
    ripemd128,
)
from mdict_audio.container.reader import (
    CorruptContainerError,
    MDictReader,
    UnsupportedContainerError,
)


def _oracle():
    from mdict_utils.base.ripemd128 import ripemd128 as oracle

    return oracle


class TestCrypto:
    def test_ripemd128_matches_oracle_random_vectors(self):
        for i in range(200):
            data = os.urandom(i * 7 % 256)
            assert ripemd128(data) == _oracle()(data)

    def test_ripemd128_known_vector(self):
        assert ripemd128(b"The quick brown fox jumps over the lazy dog") == (
            b"\x3f\xa9\xb5\x7f\x05\x3c\x05\x3f\xbe\x27\x35\xb2\x38\x0d\xb5\x96"
        )

    def test_fast_decrypt_roundtrip_with_mdict_utils_encrypt(self):
        from mdict_utils.base.writemdict import _fast_encrypt

        for size in (1, 17, 100, 1000):
            data = os.urandom(size)
            key = os.urandom(16)
            assert fast_decrypt(_fast_encrypt(data, key), key) == data

    def test_key_block_info_frame_roundtrip(self):
        from mdict_utils.base.writemdict import _mdx_encrypt

        frame = b"\x02\x00\x00\x00" + os.urandom(4) + os.urandom(300)
        encrypted = _mdx_encrypt(frame)
        assert decrypt_key_block_info(encrypted) == frame


class TestScopeMatrix:
    def _stub(self, tmp_path, encrypted):
        from conftest import make_stub_mdx_bytes

        p = tmp_path / ("enc-%s.mdx" % encrypted.replace("/", "_"))
        p.write_bytes(make_stub_mdx_bytes(encrypted=encrypted))
        return p

    def test_user_encrypted_yes_rejected(self, tmp_path):
        with pytest.raises(UnsupportedContainerError, match="user-encrypted"):
            MDictReader(self._stub(tmp_path, "Yes"))

    def test_user_encrypted_one_rejected(self, tmp_path):
        with pytest.raises(UnsupportedContainerError, match="Encrypted=1"):
            MDictReader(self._stub(tmp_path, "1"))

    def test_fixed_key_two_passes_scope(self, tmp_path):
        p = self._stub(tmp_path, "2")
        with pytest.raises(CorruptContainerError) as exc:
            MDictReader(p)
        assert "user-encrypted" not in str(exc.value)

    def test_unencrypted_still_supported(self, tmp_path):
        from conftest import make_stub_mdx_bytes

        (tmp_path / "plain.mdx").write_bytes(make_stub_mdx_bytes())
        with pytest.raises((CorruptContainerError,)) as exc:
            MDictReader(tmp_path / "plain.mdx")
        assert "encrypted" not in str(exc.value)


class TestEncryptedFixture:
    def _build_encrypted_fixture(self, tmp_path):
        from mdict_utils.base.writemdict import MDictWriter

        entries = [
            ("hello", '<div><a href="sound://audio/hello.ogg">p</a></div>'),
            ("world", "<div>world</div>"),
        ]
        path = tmp_path / "enc.mdx"
        with path.open("wb") as f:
            writer = MDictWriter(
                dict(entries),
                "enc",
                "test",
                encrypt_index=True,
                encoding="utf8",
                compression_type=2,
            )
            writer.write(f)
        return path, {k: v.encode() for k, v in entries}

    def test_encrypted_fixture_reads_back_both_readers(self, tmp_path):
        from mdict_utils.base.readmdict import MDX

        path, entries = self._build_encrypted_fixture(tmp_path)
        ours = dict(MDictReader(path).iter_records())
        ref = {k.decode(): v for k, v in MDX(str(path)).items()}
        assert set(ours) == set(ref)
        assert ours == ref

    def test_encrypted_fixture_header(self, tmp_path):
        path, _ = self._build_encrypted_fixture(tmp_path)
        reader = MDictReader(path)
        assert reader.header.get("Encrypted") == "2"
        assert reader.version_text == "2.0"
