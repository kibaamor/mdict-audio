import re
import struct
import zlib
from pathlib import Path

from .crypto import decrypt_key_block_info

_HEADER_ATTR_RE = re.compile(r'(\w+)="(.*?)"', re.DOTALL)

_MAX_HEADER_BYTES = 1 << 20
_MAX_BLOCK_COUNT = 1 << 22
_MAX_SECTION_BYTES = 1 << 29
_MAX_ENTRY_COUNT = 1 << 28


class ContainerError(Exception):
    pass


class UnsupportedContainerError(ContainerError):
    pass


class CorruptContainerError(ContainerError):
    pass


def _unescape(value):
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")
    value = value.replace("&quot;", '"')
    return value.replace("&amp;", "&")


def _inflate_bounded(data, expected_size):
    if expected_size < 0 or expected_size > _MAX_SECTION_BYTES:
        raise CorruptContainerError("invalid declared size: %d" % expected_size)
    try:
        d = zlib.decompressobj()
        out = d.decompress(data, expected_size + 1)
        if len(out) > expected_size or d.unconsumed_tail:
            raise CorruptContainerError("decompressed data exceeds declared size")
        out += d.flush()
    except zlib.error as e:
        raise CorruptContainerError("broken compressed stream: %s" % e) from e
    if len(out) != expected_size:
        raise CorruptContainerError(
            "decompressed size %d does not match declaration %d"
            % (len(out), expected_size)
        )
    return out


def _decode_block(block, expected_size):
    if len(block) < 8:
        raise CorruptContainerError("truncated block header")
    info_word = struct.unpack("<L", block[:4])[0]
    compression = info_word & 0xF
    encryption = (info_word >> 4) & 0xF
    if encryption != 0:
        raise UnsupportedContainerError("encrypted blocks are not supported")
    if compression not in (0, 2):
        raise UnsupportedContainerError(
            "unsupported compression method %d" % compression
        )
    if compression == 0 and len(block) - 8 != expected_size:
        raise CorruptContainerError("uncompressed block size mismatch")
    adler = struct.unpack(">I", block[4:8])[0]
    if compression == 0:
        out = block[8:]
    else:
        out = _inflate_bounded(block[8:], expected_size)
    if adler != (zlib.adler32(out) & 0xFFFFFFFF):
        raise CorruptContainerError("block checksum mismatch")
    return out


class MDictReader:
    def __init__(self, path, is_mdd=False):
        self.path = Path(path)
        self.is_mdd = bool(is_mdd)
        self._file_size = self.path.stat().st_size
        with self.path.open("rb") as f:
            tag = self._read_header(f)
            self._validate_scope(tag)
            self._utf16 = self.is_mdd or self._key_codec == "utf-16-le"
            self._key_start = f.tell()
            self._keys = self._read_key_section(f)
            self._record_start = f.tell()

    @property
    def header(self):
        return self._header_tag

    @property
    def encoding(self):
        return self._key_codec

    @property
    def version_text(self):
        return self._header_tag.get("GeneratedByEngineVersion", "")

    @property
    def is_encrypted(self):
        return self._encrypt != 0

    def keys(self):
        return [key for _, key in self._keys]

    def iter_records(self):
        with self.path.open("rb") as f:
            f.seek(self._record_start)
            remaining = self._file_size - self._record_start
            head = f.read(32)
            if len(head) < 32:
                raise CorruptContainerError("truncated record section")
            num_blocks, num_entries, info_size, block_size = struct.unpack(
                ">QQQQ", head
            )
            if num_entries != len(self._keys):
                raise CorruptContainerError("record entry count mismatch")
            if num_blocks > _MAX_BLOCK_COUNT:
                raise CorruptContainerError("record block count exceeds limit")
            if info_size != num_blocks * 16:
                raise CorruptContainerError("record block info size mismatch")
            if info_size > remaining or block_size > remaining:
                raise CorruptContainerError("declared record section exceeds file size")
            entries = []
            for _ in range(num_blocks):
                pair = f.read(16)
                if len(pair) != 16:
                    raise CorruptContainerError("truncated record block info")
                comp, decomp = struct.unpack(">QQ", pair)
                if comp > _MAX_SECTION_BYTES or decomp > _MAX_SECTION_BYTES:
                    raise CorruptContainerError(
                        "declared record block size exceeds limit"
                    )
                entries.append((comp, decomp))
            pos = 0
            idx = 0
            keys = self._keys
            total_comp = 0
            for comp, decomp_size in entries:
                raw = f.read(comp)
                if len(raw) != comp:
                    raise CorruptContainerError("truncated record block")
                block = _decode_block(raw, decomp_size)
                total_comp += comp
                while idx < len(keys):
                    off = keys[idx][0]
                    if off - pos >= len(block):
                        break
                    nxt = keys[idx + 1][0] if idx + 1 < len(keys) else len(block) + pos
                    if off < pos or nxt < off:
                        raise CorruptContainerError("invalid record offsets")
                    data = block[off - pos : nxt - pos]
                    if not self.is_mdd:
                        width = 2 if self._utf16 else 1
                        if data.endswith(b"\x00" * width):
                            data = data[:-width]
                    yield keys[idx][1], data
                    idx += 1
                pos += len(block)
            if total_comp != block_size:
                raise CorruptContainerError("record block size mismatch")
            if idx != len(keys):
                raise CorruptContainerError("record section does not cover all keys")

    def _read_header(self, f):
        raw_len = f.read(4)
        if len(raw_len) != 4:
            raise CorruptContainerError("truncated header length")
        header_len = struct.unpack(">I", raw_len)[0]
        if header_len == 0 or header_len > _MAX_HEADER_BYTES:
            raise CorruptContainerError("invalid header length: %d" % header_len)
        raw = f.read(header_len)
        if len(raw) != header_len:
            raise CorruptContainerError("truncated header")
        raw_checksum = f.read(4)
        if len(raw_checksum) != 4:
            raise CorruptContainerError("truncated header checksum")
        checksum = struct.unpack("<I", raw_checksum)[0]
        if checksum != (zlib.adler32(raw) & 0xFFFFFFFF):
            raise CorruptContainerError("header checksum mismatch")
        text = raw
        if text.endswith(b"\x00\x00"):
            text = text[:-2]
        elif text.endswith(b"\x00"):
            text = text[:-1]
        try:
            decoded = text.decode("utf-16-le")
        except UnicodeDecodeError as e:
            raise CorruptContainerError("header is not valid UTF-16: %s" % e) from e
        return {
            name: _unescape(value) for name, value in _HEADER_ATTR_RE.findall(decoded)
        }

    def _validate_scope(self, tag):
        self._header_tag = tag
        self._encrypt = 0
        version_text = tag.get("GeneratedByEngineVersion", "")
        try:
            version = float(version_text)
        except ValueError as e:
            raise CorruptContainerError(
                "invalid engine version: %r" % version_text
            ) from e
        if not (2.0 <= version < 3.0):
            raise UnsupportedContainerError(
                "only MDict 2.0 containers are supported, got %s" % version_text
            )
        encrypted = tag.get("Encrypted", "No")
        if encrypted in ("No", "0", ""):
            flag = 0
        elif encrypted == "Yes":
            flag = 1
        else:
            try:
                flag = int(encrypted)
            except ValueError as e:
                raise CorruptContainerError(
                    "invalid Encrypted flag: %r" % encrypted
                ) from e
        if flag & 0x01:
            raise UnsupportedContainerError(
                "user-encrypted dictionaries (Encrypted=1) are not supported; "
                "fixed-key encrypted (Encrypted=2) is supported (engine v%s)"
                % version_text
            )
        self._encrypt = flag
        if self.is_mdd:
            self._key_codec = "utf-16-le"
            return
        raw = (tag.get("Encoding") or "utf-8").strip() or "utf-8"
        upper = raw.upper()
        if upper in ("UTF-8", "UTF8"):
            self._key_codec = "utf-8"
        elif upper in ("UTF-16", "UTF16", "UTF-16-LE", "UTF16-LE"):
            self._key_codec = "utf-16-le"
        elif upper in ("GBK", "GB2312", "GB18030"):
            self._key_codec = "gb18030"
        elif upper == "BIG5":
            self._key_codec = "big5"
        else:
            raise UnsupportedContainerError("unsupported key encoding: %s" % raw)

    def _read_key_section(self, f):
        remaining = self._file_size - f.tell()
        preamble = f.read(44)
        if len(preamble) < 44:
            raise CorruptContainerError("truncated key section")
        num_blocks, num_entries, info_decomp, info_comp, key_block_size = struct.unpack(
            ">QQQQQ", preamble[:40]
        )
        adler = struct.unpack(">I", preamble[40:44])[0]
        if adler != (zlib.adler32(preamble[:40]) & 0xFFFFFFFF):
            raise CorruptContainerError("key section checksum mismatch")
        if num_blocks > _MAX_BLOCK_COUNT:
            raise CorruptContainerError("key block count exceeds limit")
        if num_entries > _MAX_ENTRY_COUNT:
            raise CorruptContainerError("key entry count exceeds limit")
        for size in (info_decomp, info_comp, key_block_size):
            if size > _MAX_SECTION_BYTES or size > remaining:
                raise CorruptContainerError("declared key section size exceeds file")
        info_raw = f.read(info_comp)
        if len(info_raw) != info_comp:
            raise CorruptContainerError("truncated key block info")
        block_list = self._decode_key_block_info(info_raw, info_decomp, num_blocks)
        key_raw = f.read(key_block_size)
        if len(key_raw) != key_block_size:
            raise CorruptContainerError("truncated key blocks")
        keys = self._decode_key_blocks(key_raw, block_list)
        if len(keys) != num_entries:
            raise CorruptContainerError("key count does not match declaration")
        return keys

    def _decode_key_block_info(self, raw, expected_decomp, num_blocks):
        if len(raw) < 8:
            raise CorruptContainerError("truncated key block info header")
        if raw[:4] != b"\x02\x00\x00\x00":
            word = struct.unpack("<L", raw[:4])[0]
            if (word >> 4) & 0xF:
                raise UnsupportedContainerError(
                    "encrypted key block info is not supported"
                )
            if (word & 0xF) != 2:
                raise UnsupportedContainerError(
                    "unsupported key block info compression %d" % (word & 0xF)
                )
        adler = struct.unpack(">I", raw[4:8])[0]
        if self._encrypt & 0x02:
            raw = decrypt_key_block_info(raw)
        decomp = _inflate_bounded(raw[8:], expected_decomp)
        if adler != (zlib.adler32(decomp) & 0xFFFFFFFF):
            raise CorruptContainerError("key block info checksum mismatch")
        width = 2 if self._utf16 else 1
        entries = []
        i = 0
        while i < len(decomp):
            if i + 10 > len(decomp):
                raise CorruptContainerError("truncated key block info entry")
            (first_len,) = struct.unpack(">H", decomp[i + 8 : i + 10])
            i += 10 + (first_len + 1) * width
            if i + 2 > len(decomp):
                raise CorruptContainerError("truncated key block info entry")
            (last_len,) = struct.unpack(">H", decomp[i : i + 2])
            i += 2 + (last_len + 1) * width
            if i + 16 > len(decomp):
                raise CorruptContainerError("truncated key block info entry")
            comp, decomp_size = struct.unpack(">QQ", decomp[i : i + 16])
            i += 16
            if comp > _MAX_SECTION_BYTES or decomp_size > _MAX_SECTION_BYTES:
                raise CorruptContainerError("declared key block size exceeds limit")
            entries.append((comp, decomp_size))
        if len(entries) != num_blocks:
            raise CorruptContainerError("key block count mismatch")
        return entries

    def _decode_key_blocks(self, raw, entries):
        keys = []
        pos = 0
        for comp, decomp_size in entries:
            if pos + comp > len(raw):
                raise CorruptContainerError("truncated key block")
            block = _decode_block(raw[pos : pos + comp], decomp_size)
            keys.extend(self._split_key_block(block))
            pos += comp
        if pos != len(raw):
            raise CorruptContainerError("key block size mismatch")
        return keys

    def _split_key_block(self, block):
        width = 2 if self._utf16 else 1
        null = b"\x00" * width
        keys = []
        i = 0
        while i < len(block):
            if i + 8 > len(block):
                raise CorruptContainerError("truncated key entry")
            (offset,) = struct.unpack(">Q", block[i : i + 8])
            end = None
            j = i + 8
            while j + width <= len(block):
                if block[j : j + width] == null:
                    end = j
                    break
                j += width
            if end is None:
                raise CorruptContainerError("unterminated key")
            key_bytes = block[i + 8 : end]
            if len(key_bytes) % width:
                raise CorruptContainerError("key length is not aligned")
            keys.append((offset, key_bytes.decode(self._key_codec, "ignore")))
            i = end + width
        return keys
