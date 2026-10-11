import sys
import time
from pathlib import Path

from mdict_audio import DEFAULT_WORKERS, family
from mdict_audio.audio import EngineError, get_decode_backend
from mdict_audio.audio.sniff import sniff_format
from mdict_audio.commands.formatting import key_extension, reader_suffix
from mdict_audio.container.collation import check_key_order
from mdict_audio.container.reader import ContainerError, MDictReader
from mdict_audio.pipeline.pool import interruptible_pool
from mdict_audio.pipeline.progress import ProgressReporter
from mdict_audio.refs import (
    count_empty_sound_refs,
    extract_sound_refs,
    normalize_ref,
    resolve_ref,
)

_EXT_FORMAT_MAP = {
    "mp3": "mp3",
    "ogg": "ogg",
    "oga": "ogg",
    "opus": "ogg",
    "wav": "wav",
    "m4a": "m4a",
    "mp4": "m4a",
    "spx": "ogg",
}


def _family_version(fam):
    p = (fam.mdx + fam.mdd)[0]
    try:
        reader = MDictReader(p, is_mdd=p.suffix.lower() == ".mdd")
    except ContainerError:
        return ""
    return reader_suffix(reader)


def _decode_clip(job):
    key, data, fmt, engine = job
    backend = get_decode_backend(engine)
    return key, fmt, backend.decode_ok(data, fmt)


def _open_readers(fam, problems):
    """Open MDX/MDD readers; check MDD key order."""
    readers = {}
    for p in fam.mdx + fam.mdd:
        is_mdd = p.suffix.lower() == ".mdd"
        try:
            readers[p] = MDictReader(p, is_mdd=is_mdd)
        except ContainerError as e:
            problems.append("%s: %s" % (p.name, e))
        else:
            if is_mdd and not check_key_order(readers[p].keys(), is_mdd=True):
                problems.append("%s: keys are not sorted" % p.name)
    return readers


def _check_mdx_refs(readers, key_set, problems):
    """Check MDX records for sound reference closure."""
    for p in sorted(readers):
        if p.suffix.lower() == ".mdd":
            continue
        total = len(readers[p].keys())
        progress = ProgressReporter(total, "Scanning %s" % p.name) if total else None
        try:
            for key, data in readers[p].iter_records():
                if progress is not None:
                    progress.update()
                empty = count_empty_sound_refs(data, readers[p].encoding)
                if empty:
                    problems.append(
                        "%s: empty sound reference "
                        "(from entry %r, %d occurrence(s))" % (p.name, key, empty)
                    )
                for ref in extract_sound_refs(data, readers[p].encoding):
                    matched, _ = resolve_ref(ref, key_set)
                    if matched is None:
                        problems.append(
                            "%s: broken sound reference %r (from entry %r)"
                            % (p.name, ref, key)
                        )
        except ContainerError as e:
            problems.append("%s: %s" % (p.name, e))
        finally:
            if progress is not None:
                progress.finish()


def _run_decode_batch(pool, items, problems):
    """Decode a batch; return (count, elapsed)."""
    if not items or pool is None:
        return 0, 0.0
    t0 = time.monotonic()
    results = list(pool.map(_decode_clip, items))
    elapsed = time.monotonic() - t0
    for key, fmt, ok in results:
        if not ok:
            problems.append("audio not decodable: %s (%s)" % (key, fmt))
    return len(results), elapsed


def _check_mdd_formats(readers, problems, decode=False, engine="auto", pool=None):
    """Check MDD records for format/extension consistency; optionally decode."""
    for p in sorted(readers):
        if p.suffix.lower() != ".mdd":
            continue
        total = len(readers[p].keys())
        scan_progress = (
            ProgressReporter(total, "Scanning %s" % p.name) if total else None
        )
        decode_count = 0
        decode_elapsed = 0.0
        batch = []
        try:
            for key, data in readers[p].iter_records():
                if scan_progress is not None:
                    scan_progress.update()
                fmt = sniff_format(data)
                ext = key_extension(key)
                expected = _EXT_FORMAT_MAP.get(ext)
                if fmt == "unknown":
                    if decode and expected is not None:
                        fmt = expected
                    else:
                        continue
                if expected is not None and expected != fmt:
                    problems.append(
                        "extension mismatch: %s (key .%s, content is %s)"
                        % (key, ext, fmt)
                    )
                if decode:
                    batch.append((key, data, fmt, engine))
                    if len(batch) >= 512:
                        count, elapsed = _run_decode_batch(pool, batch, problems)
                        decode_count += count
                        decode_elapsed += elapsed
                        batch = []
            if batch:
                count, elapsed = _run_decode_batch(pool, batch, problems)
                decode_count += count
                decode_elapsed += elapsed
        except ContainerError as e:
            problems.append("%s: %s" % (p.name, e))
        finally:
            if scan_progress is not None:
                scan_progress.finish()

        if decode and decode_count > 0:
            dp = ProgressReporter(decode_count, "Decoding %s" % p.name)
            dp.start = time.monotonic() - decode_elapsed
            dp.finish()


def verify_family(fam, workers=DEFAULT_WORKERS, decode=False, engine="auto"):
    problems = []
    readers = _open_readers(fam, problems)

    key_set = {
        normalize_ref(key)
        for p in sorted(readers)
        if p.suffix.lower() == ".mdd"
        for key in readers[p].keys()
    }
    _check_mdx_refs(readers, key_set, problems)

    if not decode:
        _check_mdd_formats(readers, problems)
        return problems

    backend = get_decode_backend(engine)
    with interruptible_pool(workers, process=backend.use_process_pool) as pool:
        _check_mdd_formats(readers, problems, decode=True, engine=engine, pool=pool)
    return problems


def run(args):
    decode = getattr(args, "decode", False)
    engine = getattr(args, "engine", "auto")
    if decode:
        try:
            backend = get_decode_backend(engine)
        except EngineError as e:
            print(e, file=sys.stderr)
            return 2
        print("engine: %s (%s)" % (backend.name, backend.reason), file=sys.stderr)
    try:
        families = family.discover(Path(args.dir))
        selected = family.select(families, args.family)
    except family.FamilyError as e:
        print(e, file=sys.stderr)
        return 2
    failed_families = 0
    workers = max(1, getattr(args, "workers", DEFAULT_WORKERS))
    for name in sorted(selected):
        problems = verify_family(
            selected[name], workers=workers, decode=decode, engine=engine
        )
        version = _family_version(selected[name])
        if problems:
            failed_families += 1
            print(
                "family %s%s: FAILED with %d problem(s)"
                % (name, version, len(problems))
            )
            for problem in problems:
                print("  - %s" % problem)
        else:
            print("family %s%s: OK" % (name, version))
    return 1 if failed_families else 0
