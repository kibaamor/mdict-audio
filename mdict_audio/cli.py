import argparse
import signal
import sys

from . import DEFAULT_WORKERS


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def _install_interrupt_handlers():
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _raise_keyboard_interrupt)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mdict-audio",
        description=(
            "Convert audio inside MDict dictionary families for playback compatibility"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser(
        "inspect", help="List dictionary families and their audio"
    )
    p_inspect.add_argument("dir")
    p_inspect.add_argument("--family", action="append")

    p_convert = sub.add_parser(
        "convert", help="Convert family audio to a target format"
    )
    p_convert.add_argument("dir")
    p_convert.add_argument("--family", action="append")
    p_convert.add_argument(
        "--to", default="mp3", choices=["mp3", "ogg"], help="target audio format"
    )
    p_convert.add_argument(
        "--out-dir",
        default="converted",
        help="output directory (relative paths resolve under the input directory)",
    )
    p_convert.add_argument(
        "--redo",
        action="store_true",
        help=(
            "overwrite existing family outputs directly; "
            "failures may leave partial new outputs"
        ),
    )
    p_convert.add_argument(
        "--force",
        action="store_true",
        help="re-encode clips already in the target format",
    )
    p_convert.add_argument(
        "--on-collision",
        default="rename",
        choices=["rename", "overwrite", "skip"],
        help="collision strategy: rename (default), overwrite, or skip",
    )
    p_convert.add_argument(
        "--inline-verify",
        default="sample",
        choices=["all", "sample", "off"],
        help="inline decode check of transcoded clips (default: sample ~10%%)",
    )
    p_convert.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "ffmpeg", "pyav"],
        help="transcode engine (default: auto=PyAV if available "
        "for mp3); an unavailable explicit engine is an error",
    )
    p_convert.add_argument(
        "--bitrate", default=None, help="target bitrate, e.g. 64k; overrides --quality"
    )
    p_convert.add_argument(
        "--quality",
        default="speech",
        choices=["speech", "standard", "high"],
        help="bitrate preset (default: speech): speech=64k, standard=128k, high=192k",
    )
    p_convert.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="parallel transcode workers (default: CPU count)",
    )

    p_verify = sub.add_parser(
        "verify", help="Check family containers, references, and audio"
    )
    p_verify.add_argument("dir")
    p_verify.add_argument("--family", action="append")
    p_verify.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="parallel decode-check workers (default: CPU count)",
    )
    p_verify.add_argument(
        "--decode",
        action="store_true",
        help=(
            "full decode check of every audio clip "
            "(slow; default: extension/format consistency only)"
        ),
    )
    p_verify.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "ffmpeg", "pyav"],
        help="decode check engine when --decode is used; "
        "an unavailable explicit engine is an error",
    )

    return parser


def main(argv=None):
    _reconfigure_stdio()
    _install_interrupt_handlers()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            from mdict_audio.commands import inspect

            return inspect.run(args)
        if args.command == "convert":
            from mdict_audio.commands import convert

            return convert.run(args)
        from mdict_audio.commands import verify

        return verify.run(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
