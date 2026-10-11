def sniff_format(data):
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"ID3"):
        return "mp3"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data[4:8] == b"ftyp":
        return "m4a"
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"
    return "unknown"
