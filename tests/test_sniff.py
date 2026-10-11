from mdict_audio.audio.sniff import sniff_format


def test_sniff_classifies_fixture_payloads(mdd_records):
    assert sniff_format(mdd_records["/audio/hello.ogg"]) == "ogg"
    assert sniff_format(mdd_records["/audio/a.mp3"]) == "mp3"
    assert sniff_format(mdd_records["/audio/voice.mp3"]) == "mp3"
    assert sniff_format(mdd_records["/audio/beep.m4a"]) == "m4a"
    assert sniff_format(mdd_records["/audio/wave.wav"]) == "wav"
    assert sniff_format(mdd_records["/img/logo.png"]) == "unknown"
    assert sniff_format(mdd_records["/css/style.css"]) == "unknown"


def test_sniff_ignores_extension_and_handles_magic_bytes():
    assert sniff_format(b"OggS" + b"\x00" * 32) == "ogg"
    assert sniff_format(b"ID3\x04\x00\x00\x00" + b"\x00" * 64) == "mp3"
    assert sniff_format(b"\xff\xfb\x90\x00" + b"\x00" * 100) == "mp3"
    assert sniff_format(b"\xff\xe0\x00\x00" + b"\x00" * 100) == "mp3"
    assert sniff_format(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "wav"
    assert sniff_format(b"\x00\x00\x00\x20ftypM4A mp42" + b"\x00" * 64) == "m4a"
    assert sniff_format(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64) == "m4a"
    assert sniff_format(b"plain text payload") == "unknown"
    assert sniff_format(b"") == "unknown"
