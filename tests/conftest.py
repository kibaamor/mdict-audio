import shutil
import struct
import subprocess
import wave
import zlib

import pytest
from mdict_utils.writer import pack, pack_mdd_file, pack_mdx_txt

from mdict_audio.container.reader import MDictReader

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

MDX_TXT = (
    "hello\n"
    '<div>hello <a href="sound://audio/hello.ogg">play</a></div>\n'
    "</>\n"
    "world\n"
    '<div>world <a href="sound://\\audio\\world.ogg">play</a></div>\n'
    "</>\n"
    "plain\n"
    "<div>no audio</div>\n"
    "</>\n"
    "clash\n"
    '<div>clash <a href="sound://audio/a.ogg">play</a></div>\n'
    "</>\n"
    "voice\n"
    '<div>voice <a href="sound://audio/voice.mp3">play</a></div>\n'
    "</>\n"
)


def make_stub_mdx_bytes(version="2.0", encrypted="No", encoding="UTF-8"):
    text = (
        '<Dictionary GeneratedByEngineVersion="%s" Encrypted="%s" '
        'Encoding="%s"/>\r\n\x00' % (version, encrypted, encoding)
    )
    raw = text.encode("utf-16-le")
    return (
        struct.pack(">I", len(raw))
        + raw
        + struct.pack("<I", zlib.adler32(raw) & 0xFFFFFFFF)
    )


def ffmpeg_audio(out_path, frequency, codec):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required for audio fixture generation")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=%d:duration=0.25" % frequency,
            *codec,
            str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def make_wav(out_path):
    frames = b"".join(
        struct.pack("<h", 12000 if (i // 8) % 2 == 0 else -12000) for i in range(1600)
    )
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(frames)


@pytest.fixture(scope="session")
def supported_family(tmp_path_factory):
    base = tmp_path_factory.mktemp("family")
    res = base / "res"
    audio = res / "audio"
    audio.mkdir(parents=True)
    (res / "img").mkdir()
    (res / "css").mkdir()
    ffmpeg_audio(audio / "hello.ogg", 440, ["-c:a", "libvorbis", "-q:a", "4"])
    ffmpeg_audio(audio / "world.ogg", 550, ["-c:a", "libvorbis", "-q:a", "4"])
    ffmpeg_audio(audio / "a.ogg", 660, ["-c:a", "libvorbis", "-q:a", "4"])
    ffmpeg_audio(audio / "a.mp3", 770, ["-c:a", "libmp3lame", "-b:a", "64k"])
    ffmpeg_audio(audio / "voice.mp3", 880, ["-c:a", "libmp3lame", "-b:a", "64k"])
    ffmpeg_audio(audio / "beep.m4a", 990, ["-c:a", "aac", "-b:a", "32k"])
    make_wav(audio / "wave.wav")
    (res / "img" / "logo.png").write_bytes(MINIMAL_PNG)
    (res / "css" / "style.css").write_bytes(b"body{color:#333}")

    src = base / "src.txt"
    src.write_text(MDX_TXT, encoding="utf-8", newline="\n")

    dicts = base / "dicts"
    dicts.mkdir()
    pack(str(dicts / "testdict.mdx"), pack_mdx_txt(str(src)))
    pack(str(dicts / "testdict.mdd"), pack_mdd_file(str(res)), is_mdd=True)
    return dicts


@pytest.fixture(scope="session")
def mdd_records(supported_family):
    reader = MDictReader(supported_family / "testdict.mdd", is_mdd=True)
    return {k.replace("\\", "/"): v for k, v in reader.iter_records()}


@pytest.fixture(scope="session")
def multi_family_dir(tmp_path_factory, supported_family):
    base = tmp_path_factory.mktemp("multi")
    dicts = base / "dicts"
    shutil.copytree(supported_family, dicts)
    src = base / "collins.txt"
    src.write_text("collins\n<div>collins</div>\n</>\n", encoding="utf-8", newline="\n")
    pack(str(dicts / "collins.mdx"), pack_mdx_txt(str(src)))
    return dicts
