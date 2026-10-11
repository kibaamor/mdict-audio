import io

from mdict_audio.audio.ffmpeg import TranscodeError

_INPUT_FORMATS = {"m4a": "mp4"}


def transcode(data, src_fmt, dst_fmt, quality_mode, quality_value, **kwargs):
    if dst_fmt != "mp3":
        raise TranscodeError("pyav backend only supports mp3 output")
    src = None
    out = None
    try:
        import av

        src = av.open(io.BytesIO(data), format=_INPUT_FORMATS.get(src_fmt, src_fmt))
        rate = src.streams.audio[0].rate
        buf = io.BytesIO()
        out = av.open(buf, "w", format=dst_fmt)
        stream = out.add_stream("libmp3lame", rate=rate)
        s = quality_value.strip().lower()
        if s.endswith("k"):
            stream.bit_rate = int(s[:-1]) * 1000
        else:
            stream.bit_rate = int(s)
        for frame in src.decode(audio=0):  # type: ignore[attr-defined]
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
        out.close()
        out = None
        src.close()
        src = None
        return buf.getvalue()
    except TranscodeError:
        raise
    except Exception as e:
        raise TranscodeError("pyav failed: %s" % str(e)[:200]) from e
    finally:
        if out is not None:
            try:
                out.close()
            except Exception:
                pass
        if src is not None:
            try:
                src.close()
            except Exception:
                pass


def decode_ok(data, fmt=None, **kwargs):
    src = None
    try:
        import av

        src = av.open(
            io.BytesIO(data), format=_INPUT_FORMATS.get(fmt, fmt) if fmt else None
        )
        for _ in src.decode(audio=0):  # type: ignore[attr-defined]
            pass
        src.close()
        src = None
        return True
    except Exception:
        return False
    finally:
        if src is not None:
            try:
                src.close()
            except Exception:
                pass
