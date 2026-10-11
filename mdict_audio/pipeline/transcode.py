import hashlib
import shutil
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple

from mdict_audio import DEFAULT_WORKERS
from mdict_audio.audio import EngineError, get_backend
from mdict_audio.audio.ffmpeg import TranscodeError
from mdict_audio.audio.sniff import sniff_format
from mdict_audio.container.collation import key_sort_key
from mdict_audio.container.writer import write_mdict
from mdict_audio.pipeline.pool import interruptible_pool
from mdict_audio.pipeline.progress import ProgressReporter, counted
from mdict_audio.pipeline.stores import RecordStore, RecordStoreWriter
from mdict_audio.refs import plan_renames_by_format, resolve_collisions

BATCH_SIZE = 512


class RecordSource(NamedTuple):
    kind: str
    store_path: Path | None
    offset: int
    length: int


def _converted_source(offset, length):
    return RecordSource("c", None, offset, length)


def _original_source(store_path, offset, length):
    return RecordSource("o", store_path, offset, length)


def _should_verify(key, inline_verify):
    if inline_verify == "all":
        return True
    if inline_verify == "off":
        return False
    return int(hashlib.sha1(key.encode()).hexdigest()[:2], 16) < 26


def _transcode_clip(
    key,
    data,
    src_format,
    dst_format,
    quality_mode,
    quality_value,
    spill_dir,
    backend,
    inline_verify="sample",
):
    try:
        out = backend.transcode(
            data,
            src_format,
            dst_format,
            quality_mode,
            quality_value,
            spill_dir=spill_dir,
        )
    except TranscodeError as e:
        return (
            key,
            None,
            "transcode failed for %s: %s; kept original resource" % (key, e),
        )
    if _should_verify(key, inline_verify) and not backend.decode_ok(out, dst_format):
        return key, None, "decode check failed for %s; kept original resource" % key
    return key, out, None


def _store_transcode(
    store_path,
    offset,
    length,
    key,
    fmt,
    dst_format,
    quality_mode,
    quality_value,
    spill_dir,
    inline_verify="sample",
    engine="auto",
):
    data = RecordStore(store_path).read(offset, length)
    try:
        backend = get_backend(engine, dst_format)
    except EngineError as e:
        return key, None, "engine unavailable: %s; kept original resource" % e
    return _transcode_clip(
        key,
        data,
        fmt,
        dst_format,
        quality_mode,
        quality_value,
        spill_dir,
        backend,
        inline_verify,
    )


def _spill_volume_records(path, reader, spill_dir):
    store_path = spill_dir / ("origins-%s.store" % path.name)
    writer = RecordStoreWriter(store_path)
    rows = []
    progress = ProgressReporter(len(reader.keys()), "Unpacking %s" % path.name)
    try:
        for key, data in reader.iter_records():
            offset, length = writer.append(data)
            rows.append((key, offset, length, sniff_format(data)))
            progress.update()
    finally:
        progress.finish()
        writer.close()
    return store_path, rows


def _assemble_volume(path, out_path, final, conv_store_path, spill_dir):
    sk = key_sort_key(True)
    final.sort(key=lambda e: sk(e[0]))

    progress = ProgressReporter(len(final), "Assembling %s" % path.name)
    try:
        source_paths = {src.store_path for _, src in final if src.kind == "o"}
        with ExitStack() as stack:
            converted = stack.enter_context(RecordStore(conv_store_path))
            origin_stores = {
                store_path: stack.enter_context(RecordStore(store_path))
                for store_path in source_paths
            }

            def entries():
                for fkey, src in final:
                    if src.kind == "c":
                        yield fkey, converted.read(src.offset, src.length)
                    else:
                        yield (
                            fkey,
                            origin_stores[src.store_path].read(src.offset, src.length),
                        )

            with open(out_path, "wb") as f:
                write_mdict(
                    f,
                    counted(entries(), progress),
                    is_mdd=True,
                    sort_entries=False,
                    spool_dir=spill_dir,
                )
    finally:
        progress.finish()


def _plan_family_transcodes(volume_rows, target, force, collision_strategy):
    all_keys = [row[0] for rows in volume_rows for row in rows]
    family_map = {}
    transcode_keys = set()
    for rows in volume_rows:
        renames, keys_to_transcode = plan_renames_by_format(
            ((row[0], row[3]) for row in rows), target, force
        )
        family_map.update(renames)
        transcode_keys.update(keys_to_transcode)
    family_map, collisions, dropped, skipped = resolve_collisions(
        family_map, all_keys, collision_strategy
    )
    transcode_keys -= skipped
    transcode_keys -= dropped
    return family_map, transcode_keys, collisions, dropped, skipped


def _build_transcode_jobs(volume_rows, stores, transcode_keys):
    job_index = {}
    for vi, rows in enumerate(volume_rows):
        store_path = stores[vi]
        for key, offset, length, fmt in rows:
            if key in transcode_keys and key not in job_index:
                job_index[key] = (store_path, offset, length, fmt)
    return sorted(job_index.items())


def _build_warnings(job_list, failures, collisions):
    warnings = [failures[key] for key, _ in job_list if key in failures]
    for old, desired, action, outcome in collisions:
        if action == "renamed":
            warnings.append(
                "collision: %s -> %s already exists; renamed to %s"
                % (old, desired, outcome)
            )
        elif action == "overwritten":
            warnings.append(
                "collision: %s -> %s already exists; overwrote existing key"
                % (old, desired)
            )
        else:
            warnings.append(
                "collision: %s -> %s already exists; kept existing key and "
                "skipped conversion" % (old, desired)
            )
    return warnings


def _initial_stats(collisions, skipped):
    return {
        "transcoded": 0,
        "passed_through": 0,
        "failed": 0,
        "collisions": len(collisions),
        "overwritten": sum(1 for c in collisions if c[2] == "overwritten"),
        "skipped": len(skipped),
    }


def _build_volume_sources(
    rows,
    store_path,
    family_map,
    converted_index,
    failures,
    skipped,
    dropped,
    stats,
):
    final = []
    for key, offset, length, _fmt in rows:
        if key in skipped or key in dropped:
            continue
        if key in converted_index:
            final.append(
                (family_map.get(key, key), _converted_source(*converted_index[key]))
            )
            stats["transcoded"] += 1
        elif key in failures:
            final.append((key, _original_source(store_path, offset, length)))
            stats["failed"] += 1
        else:
            final.append((key, _original_source(store_path, offset, length)))
            stats["passed_through"] += 1
    return final


def convert_mdd_volumes(
    volumes,
    out_paths,
    target="mp3",
    quality_mode="bitrate",
    quality_value="128k",
    spill_dir=None,
    workers=DEFAULT_WORKERS,
    force=False,
    collision_strategy="rename",
    inline_verify="sample",
    engine="auto",
    label="Transcoding",
):
    own_tmp = None
    if spill_dir is None:
        own_tmp = tempfile.mkdtemp(prefix="mdict-stream-")
        spill_dir = own_tmp
    spill_dir = Path(spill_dir)
    try:
        stores = []
        volume_rows = []
        for path, reader in volumes:
            store_path, rows = _spill_volume_records(path, reader, spill_dir)
            stores.append(store_path)
            volume_rows.append(rows)

        family_map, transcode_keys, collisions, dropped, skipped = (
            _plan_family_transcodes(volume_rows, target, force, collision_strategy)
        )
        job_list = _build_transcode_jobs(volume_rows, stores, transcode_keys)
        converted_index = {}
        failures = {}
        conv_store_path = spill_dir / "converted.store"
        conv_writer = RecordStoreWriter(conv_store_path)
        backend = get_backend(engine, target)
        use_process = backend.use_process_pool
        progress = None
        try:
            progress = ProgressReporter(len(job_list), label)
            with interruptible_pool(workers, process=use_process) as pool:
                for start in range(0, len(job_list), BATCH_SIZE):
                    batch = job_list[start : start + BATCH_SIZE]
                    futures = [
                        pool.submit(
                            _store_transcode,
                            store_path,
                            offset,
                            length,
                            key,
                            fmt,
                            target,
                            quality_mode,
                            quality_value,
                            spill_dir,
                            inline_verify,
                            engine,
                        )
                        for key, (store_path, offset, length, fmt) in batch
                    ]
                    for future in futures:
                        key, out, reason = future.result()
                        progress.update()
                        if out is None:
                            failures[key] = reason
                        else:
                            converted_index[key] = conv_writer.append(out)
        finally:
            if progress is not None:
                progress.finish()
            conv_writer.close()
        for key in failures:
            family_map.pop(key, None)
        warnings = _build_warnings(job_list, failures, collisions)
        stats = _initial_stats(collisions, skipped)

        for vi, (path, _reader) in enumerate(volumes):
            final = _build_volume_sources(
                volume_rows[vi],
                stores[vi],
                family_map,
                converted_index,
                failures,
                skipped,
                dropped,
                stats,
            )
            _assemble_volume(path, out_paths[path], final, conv_store_path, spill_dir)
        return family_map, warnings, stats
    finally:
        if own_tmp is not None:
            shutil.rmtree(own_tmp, ignore_errors=True)
