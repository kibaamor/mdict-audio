import datetime
import os
import shutil
import struct
import tempfile
import zlib
from html import escape

from .collation import key_sort_key


def _frame_compress(data):
    return (
        struct.pack("<L", 2)
        + struct.pack(">L", zlib.adler32(data) & 0xFFFFFFFF)
        + zlib.compress(data)
    )


def _normalize_mdx_encoding(encoding):
    upper = (encoding or "utf-8").strip().upper()
    if upper in ("UTF-8", "UTF8", ""):
        return "utf-8", "UTF-8", 1
    if upper in ("UTF-16", "UTF16", "UTF-16-LE", "UTF16-LE"):
        return "utf-16-le", "UTF-16", 2
    if upper in ("GBK", "GB2312", "GB18030"):
        return "gb18030", "GBK", 1
    if upper == "BIG5":
        return "big5", "BIG5", 1
    raise ValueError("unsupported mdx encoding: %s" % encoding)


def _split_key_blocks(table, size):
    this_start = 0
    cur = 0
    blocks = []
    for ind in range(len(table) + 1):
        t = table[ind] if ind != len(table) else None
        if ind == 0:
            flush = False
        elif ind == len(table):
            flush = True
        elif cur + (8 + len(t[0])) > size:
            flush = True
        else:
            flush = False
        if flush:
            blocks.append(table[this_start:ind])
            cur = 0
            this_start = ind
        if t is not None:
            cur += 8 + len(t[0])
    return blocks


def _write_header(f, is_mdd, encoding_label, title, description, header=None):
    date = datetime.date.today()
    if is_mdd:
        header_text = (
            "<Library_Data "
            'GeneratedByEngineVersion="2.0" '
            'RequiredEngineVersion="2.0" '
            'Encrypted="No" '
            'Encoding="" '
            'Format="" '
            'CreationDate="%d-%d-%d" '
            'KeyCaseSensitive="No" '
            'Stripkey="No" '
            'Description="%s" '
            'Title="%s" '
            'RegisterBy=""/>\r\n\x00'
        ) % (
            date.year,
            date.month,
            date.day,
            escape(description, quote=True),
            escape(title, quote=True),
        )
    else:
        src = header or {}
        header_text = (
            "<Dictionary "
            'GeneratedByEngineVersion="2.0" '
            'RequiredEngineVersion="2.0" '
            'Encrypted="No" '
            'Encoding="%s" '
            'Format="%s" '
            'Stripkey="%s" '
            'CreationDate="%d-%d-%d" '
            'Compact="%s" '
            'Compat="%s" '
            'KeyCaseSensitive="%s" '
            'Description="%s" '
            'Title="%s" '
            'DataSourceFormat="%s" '
            'StyleSheet="%s" '
            'Left2Right="%s" '
            'RegisterBy="%s"/>\r\n\x00'
        ) % (
            encoding_label,
            escape(src.get("Format", "Html"), quote=True),
            escape(src.get("Stripkey") or src.get("StripKey") or "Yes", quote=True),
            date.year,
            date.month,
            date.day,
            escape(src.get("Compact", "Yes"), quote=True),
            escape(src.get("Compat", "Yes"), quote=True),
            escape(src.get("KeyCaseSensitive", "No"), quote=True),
            escape(description, quote=True),
            escape(title, quote=True),
            escape(src.get("DataSourceFormat", "106"), quote=True),
            escape(src.get("StyleSheet", ""), quote=True),
            escape(src.get("Left2Right", "Yes"), quote=True),
            escape(src.get("RegisterBy", ""), quote=True),
        )
    header_bytes = header_text.encode("utf-16-le")
    f.write(struct.pack(">L", len(header_bytes)))
    f.write(header_bytes)
    f.write(struct.pack("<L", zlib.adler32(header_bytes) & 0xFFFFFFFF))


def write_mdict(
    outfile,
    entries,
    is_mdd,
    encoding="utf-8",
    title="",
    description="",
    key_block_size=32768,
    record_block_size=65536,
    sort_entries=True,
    spool_dir=None,
    header=None,
):
    if sort_entries:
        sk = key_sort_key(is_mdd)
        entries = sorted(entries, key=lambda e: sk(e[0]))

    if is_mdd:
        key_codec, encoding_label, units = "utf-16-le", "", 2
    else:
        key_codec, encoding_label, units = _normalize_mdx_encoding(encoding)

    key_table = []
    record_index = []
    num_entries = 0
    spool_path = None

    if spool_dir is not None:
        os.makedirs(spool_dir, exist_ok=True)
        fd, spool_path = tempfile.mkstemp(dir=spool_dir, prefix=".recspool-")
        spool = os.fdopen(fd, "w+b")
    else:
        spool = tempfile.TemporaryFile()

    try:
        buf = []
        buf_bytes = 0
        offset = 0

        def flush_block():
            nonlocal buf, buf_bytes
            data = b"".join(buf)
            frame = _frame_compress(data)
            spool.write(frame)
            record_index.append((len(frame), len(data)))
            buf = []
            buf_bytes = 0

        for key, record in entries:
            if not isinstance(key, str):
                raise TypeError("key must be str, got %s" % type(key).__name__)
            key_enc = key.encode(key_codec)
            key_null = key_enc + b"\x00" * units
            key_len = len(key_enc) // units
            if is_mdd:
                if isinstance(record, str):
                    raise TypeError("mdd records must be bytes, got str")
                record_null = bytes(record)
            elif isinstance(record, str):
                record_null = record.encode(key_codec) + b"\x00" * units
            else:
                record_null = bytes(record) + b"\x00" * units
            if buf and buf_bytes + len(record_null) > record_block_size:
                flush_block()
            buf.append(record_null)
            buf_bytes += len(record_null)
            key_table.append((key_null, key_len, offset))
            offset += len(record_null)
            num_entries += 1
        if buf:
            flush_block()

        key_blocks = _split_key_blocks(key_table, key_block_size)
        key_block_frames = []
        index_parts = []
        for blk in key_blocks:
            data = b"".join(struct.pack(">Q", t[2]) + t[0] for t in blk)
            frame = _frame_compress(data)
            first, last = blk[0], blk[-1]
            index_parts.append(
                struct.pack(">Q", len(blk))
                + struct.pack(">H", first[1])
                + first[0]
                + struct.pack(">H", last[1])
                + last[0]
                + struct.pack(">QQ", len(frame), len(data))
            )
            key_block_frames.append(frame)
        index_plain = b"".join(index_parts)
        key_index = _frame_compress(index_plain)

        _write_header(outfile, is_mdd, encoding_label, title, description, header)

        key_total = sum(len(frame) for frame in key_block_frames)
        preamble = struct.pack(
            ">QQQQQ",
            len(key_blocks),
            num_entries,
            len(index_plain),
            len(key_index),
            key_total,
        )
        outfile.write(preamble)
        outfile.write(struct.pack(">I", zlib.adler32(preamble) & 0xFFFFFFFF))
        outfile.write(key_index)
        for frame in key_block_frames:
            outfile.write(frame)

        record_index_bytes = b"".join(
            struct.pack(">QQ", comp, decomp) for comp, decomp in record_index
        )
        record_total = sum(comp for comp, _ in record_index)
        outfile.write(
            struct.pack(
                ">QQQQ",
                len(record_index),
                num_entries,
                len(record_index_bytes),
                record_total,
            )
        )
        outfile.write(record_index_bytes)
        spool.seek(0)
        shutil.copyfileobj(spool, outfile, 1024 * 1024)
    finally:
        spool.close()
        if spool_path is not None:
            try:
                os.unlink(spool_path)
            except OSError:
                pass
