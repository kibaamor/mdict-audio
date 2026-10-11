import sys
from pathlib import Path

from mdict_audio import family
from mdict_audio.audio.sniff import sniff_format
from mdict_audio.commands.formatting import key_extension, reader_suffix
from mdict_audio.container.reader import (
    ContainerError,
    MDictReader,
    UnsupportedContainerError,
)

AUDIO_FORMATS = ("mp3", "ogg", "wav", "m4a")


def _try_open(path, is_mdd):
    try:
        reader = MDictReader(path, is_mdd=is_mdd)
    except UnsupportedContainerError as e:
        return None, "unsupported", str(e)
    except ContainerError as e:
        return None, "corrupt", str(e)
    return reader, "supported" + reader_suffix(reader), ""


def _mdx_status(path):
    _, status, reason = _try_open(path, is_mdd=False)
    return status, reason


def _mdd_status(path):
    reader, status, reason = _try_open(path, is_mdd=True)
    if reader is None:
        return status, reason, {}, {}
    audio_counts = {}
    other_counts = {}
    try:
        for key, data in reader.iter_records():
            fmt = sniff_format(data)
            if fmt in AUDIO_FORMATS:
                audio_counts[fmt] = audio_counts.get(fmt, 0) + 1
            else:
                ext = key_extension(key, missing="(none)")
                other_counts[ext] = other_counts.get(ext, 0) + 1
    except ContainerError as e:
        return "corrupt", str(e), {}, {}
    return status, reason, audio_counts, other_counts


def run(args):
    try:
        families = family.discover(Path(args.dir))
    except family.FamilyError as e:
        print(e, file=sys.stderr)
        return 2
    if not families:
        print("no .mdx/.mdd files found in: %s" % args.dir, file=sys.stderr)
        return 1
    if args.family:
        try:
            families = family.select(families, args.family)
        except family.FamilyError as e:
            print(e, file=sys.stderr)
            return 2
    for name in sorted(families):
        fam = families[name]
        print("family %s" % name)
        for p in fam.mdx:
            status, reason = _mdx_status(p)
            line = "  mdx  %-32s %s" % (p.name, status)
            if reason:
                line += "  " + reason
            print(line)
        for p in fam.mdd:
            status, reason, audio_counts, other_counts = _mdd_status(p)
            line = "  mdd  %-32s %s" % (p.name, status)
            if reason:
                line += "  " + reason
            if audio_counts:
                audio = ", ".join(
                    "%s=%d" % (f, audio_counts[f]) for f in sorted(audio_counts)
                )
                line += "  audio: " + audio
            if other_counts:
                other = ", ".join(
                    "%s=%d" % (f, other_counts[f]) for f in sorted(other_counts)
                )
                line += "  other: " + other
            print(line)
    return 0
