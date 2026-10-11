import os
import shutil
import subprocess
import tempfile

TIMEOUT_SECONDS = 120
SPILL_THRESHOLD = 32 * 1024 * 1024
_STDERR_EXCERPT = 500

_FFMPEG_INPUT_FORMATS = {"m4a": "mp4"}


class TranscodeError(Exception):
    pass


_FFMPEG_PATH = None


def find_ffmpeg():
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        path = shutil.which("ffmpeg")
        if path is None:
            raise TranscodeError(
                "ffmpeg not found on PATH; install ffmpeg to convert audio"
            )
        _FFMPEG_PATH = path
    return _FFMPEG_PATH


def _input_format(src_format):
    return _FFMPEG_INPUT_FORMATS.get(src_format, src_format)


def output_args(dst_format, quality_mode, quality_value):
    if dst_format == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", quality_value]
    if quality_mode == "bitrate":
        return ["-c:a", "libvorbis", "-b:a", quality_value]
    return ["-c:a", "libvorbis", "-q:a", quality_value]


def transcode(
    data,
    src_format,
    dst_format,
    quality_mode,
    quality_value,
    spill_dir=None,
    spill_threshold=SPILL_THRESHOLD,
):
    ffmpeg = find_ffmpeg()
    out_args = output_args(dst_format, quality_mode, quality_value)
    if spill_dir is not None and len(data) > spill_threshold:
        return _transcode_via_files(
            ffmpeg, data, src_format, dst_format, out_args, spill_dir
        )
    args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        _input_format(src_format),
        "-i",
        "pipe:0",
        "-vn",
        *out_args,
        "-f",
        dst_format,
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            args, input=data, capture_output=True, timeout=TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as e:
        raise TranscodeError("ffmpeg timed out after %ds" % TIMEOUT_SECONDS) from e
    except OSError as e:
        raise TranscodeError("ffmpeg process error: %s" % e) from e
    if proc.returncode != 0 or not proc.stdout:
        raise TranscodeError(
            "ffmpeg failed: %s"
            % proc.stderr[-_STDERR_EXCERPT:].decode("utf-8", "replace").strip()
        )
    return proc.stdout


def _transcode_via_files(ffmpeg, data, src_format, dst_format, out_args, spill_dir):
    in_fd, in_name = tempfile.mkstemp(dir=str(spill_dir), suffix=".spill-in")
    out_fd, out_name = tempfile.mkstemp(
        dir=str(spill_dir), suffix=".spill-out.%s" % dst_format
    )
    os.close(out_fd)
    try:
        with os.fdopen(in_fd, "wb") as f:
            f.write(data)
        args = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            _input_format(src_format),
            "-i",
            in_name,
            "-vn",
            *out_args,
            "-f",
            dst_format,
            "-y",
            out_name,
        ]
        try:
            proc = subprocess.run(args, capture_output=True, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            raise TranscodeError("ffmpeg timed out after %ds" % TIMEOUT_SECONDS) from e
        except OSError as e:
            raise TranscodeError("ffmpeg process error: %s" % e) from e
        if proc.returncode != 0 or not os.path.exists(out_name):
            raise TranscodeError(
                "ffmpeg failed: %s"
                % proc.stderr[-_STDERR_EXCERPT:].decode("utf-8", "replace").strip()
            )
        with open(out_name, "rb") as f:
            return f.read()
    finally:
        for path in (in_name, out_name):
            try:
                os.unlink(path)
            except OSError:
                pass


def decode_ok(data, src_format=None):
    ffmpeg = find_ffmpeg()
    args = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if src_format:
        args += ["-f", _input_format(src_format)]
    args += ["-i", "pipe:0", "-f", "null", "-"]
    try:
        proc = subprocess.run(
            args, input=data, capture_output=True, timeout=TIMEOUT_SECONDS
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0
