from collections import namedtuple

from mdict_audio.audio.ffmpeg import TranscodeError, find_ffmpeg

Backend = namedtuple("Backend", "name reason transcode decode_ok use_process_pool")


class EngineError(Exception):
    pass


# reason strings appear in stderr output and manifests; reword with care
def resolve_engine(engine, dst_fmt):
    """Return (name, reason); raise EngineError when an explicitly
    requested engine cannot be used."""
    if dst_fmt == "ogg":
        if engine == "pyav":
            raise EngineError(
                "pyav cannot encode ogg (no libvorbis in wheels); "
                "use --to mp3 or --engine auto/ffmpeg"
            )
        _require_ffmpeg()
        return "ffmpeg", "ogg target requires ffmpeg"
    if engine == "ffmpeg":
        _require_ffmpeg()
        return "ffmpeg", "requested"
    try:
        import av  # noqa: F401
    except ImportError as e:
        if engine == "pyav":
            raise EngineError(
                "pyav requested but not installed (pip install mdict-audio[pyav])"
            ) from e
        _require_ffmpeg()
        return "ffmpeg", "auto; pyav not installed"
    return "pyav", "auto" if engine == "auto" else "requested"


def get_backend(engine, dst_fmt):
    name, reason = resolve_engine(engine, dst_fmt)
    if name == "pyav":
        from mdict_audio.audio import pyav as m

        use_process_pool = True
    else:
        from mdict_audio.audio import ffmpeg as m

        use_process_pool = False
    return Backend(name, reason, m.transcode, m.decode_ok, use_process_pool)


def get_decode_backend(engine):
    """Resolve backend for decode-only; no output-format dependency."""
    if engine == "auto" or engine == "pyav":
        try:
            import av  # noqa: F401  availability check
        except ImportError as e:
            if engine == "pyav":
                raise EngineError(
                    "pyav requested but not installed (pip install mdict-audio[pyav])"
                ) from e
        else:
            from mdict_audio.audio import pyav as m

            return Backend(
                "pyav",
                "auto" if engine == "auto" else "requested",
                m.transcode,
                m.decode_ok,
                True,
            )
    _require_ffmpeg()
    from mdict_audio.audio import ffmpeg as m

    return Backend(
        "ffmpeg",
        "auto" if engine == "auto" else "requested",
        m.transcode,
        m.decode_ok,
        False,
    )


def _require_ffmpeg():
    try:
        find_ffmpeg()
    except TranscodeError as e:
        raise EngineError(str(e)) from e
