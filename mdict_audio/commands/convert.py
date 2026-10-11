import os
import sys
from pathlib import Path

from mdict_audio import DEFAULT_WORKERS, family
from mdict_audio.audio import EngineError, resolve_engine
from mdict_audio.commands.formatting import reader_suffix
from mdict_audio.container.reader import ContainerError, MDictReader
from mdict_audio.manifest import build_manifest, dump_manifest, input_fingerprint
from mdict_audio.pipeline.mdx import convert_mdx
from mdict_audio.pipeline.transcode import convert_mdd_volumes
from mdict_audio.refs import normalize_ref
from mdict_audio.staging import StagingArea

QUALITY_PRESETS = {
    "mp3": {
        "speech": ("bitrate", "64k"),
        "standard": ("bitrate", "128k"),
        "high": ("bitrate", "192k"),
    },
    "ogg": {
        "speech": ("quality", "2"),
        "standard": ("quality", "4"),
        "high": ("quality", "6"),
    },
}


def resolve_quality(args):
    if args.bitrate:
        return "bitrate", args.bitrate
    return QUALITY_PRESETS[args.to][args.quality]


def run(args):
    engine = getattr(args, "engine", "auto")
    try:
        engine_name, engine_reason = resolve_engine(engine, args.to)
    except EngineError as e:
        print(e, file=sys.stderr)
        return 2
    quality_mode, quality_value = resolve_quality(args)
    workers = max(1, args.workers)
    print(
        "engine: %s (%s), target: %s, quality: %s %s, workers: %d"
        % (engine_name, engine_reason, args.to, quality_mode, quality_value, workers),
        file=sys.stderr,
    )
    directory = Path(args.dir)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = directory / out_dir
    try:
        families = family.discover(directory)
        selected = family.select(families, args.family)
    except family.FamilyError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        for name in sorted(selected):
            rc = _convert_family(
                selected[name],
                out_dir,
                redo=args.redo,
                target=args.to,
                quality_mode=quality_mode,
                quality_value=quality_value,
                workers=workers,
                quality=args.quality,
                force=args.force,
                collision=args.on_collision,
                inline_verify=args.inline_verify,
                engine=engine,
                engine_name=engine_name,
                engine_reason=engine_reason,
            )
            if rc != 0:
                return rc
    except KeyboardInterrupt:
        print("interrupted; staging cleaned", file=sys.stderr)
        return 130
    return 0


def _convert_family(
    fam,
    out_dir,
    redo=False,
    target="mp3",
    quality_mode="bitrate",
    quality_value="64k",
    workers=DEFAULT_WORKERS,
    quality="speech",
    force=False,
    collision="rename",
    inline_verify="sample",
    engine="auto",
    engine_name=None,
    engine_reason=None,
):
    family_name = fam.name
    finals = {p.name: out_dir / p.name for p in fam.files}
    final_manifest = out_dir / ("%s.manifest.json" % family_name)
    existing = [str(p) for p in list(finals.values()) + [final_manifest] if p.exists()]
    if existing and not redo:
        print(
            "output for family %s already exists: %s\nremove it or rerun with --redo"
            % (family_name, ", ".join(existing)),
            file=sys.stderr,
        )
        return 2

    readers = {}
    try:
        for p in fam.mdx:
            readers[p] = MDictReader(p, is_mdd=False)
        for p in fam.mdd:
            readers[p] = MDictReader(p, is_mdd=True)
    except ContainerError as e:
        print("family %s rejected: %s" % (family_name, e), file=sys.stderr)
        return 2

    staging = StagingArea(out_dir, family_name)
    try:
        mdd_volumes = [(p, readers[p]) for p in fam.mdd]
        mdd_out_paths = {p: staging.path / p.name for p in fam.mdd}
        rename_map, warnings, stats = convert_mdd_volumes(
            mdd_volumes,
            mdd_out_paths,
            target=target,
            quality_mode=quality_mode,
            quality_value=quality_value,
            spill_dir=staging.path,
            workers=workers,
            force=force,
            collision_strategy=collision,
            inline_verify=inline_verify,
            engine=engine,
            label="Transcoding %s" % family_name,
        )
        staging_files = {}
        for p in fam.mdd:
            staging_files[(staging.path / p.name).name] = finals[p.name]
        orig_keys = [k for p in fam.mdd for k in readers[p].keys()]
        orig_index = {normalize_ref(k) for k in orig_keys}
        final_index = {normalize_ref(rename_map.get(k, k)) for k in orig_keys}
        stats["broken_refs_pre_existing"] = 0
        stats["broken_refs_introduced"] = 0
        for p in fam.mdx:
            out_path = staging.path / p.name
            pre, intro = convert_mdx(
                readers[p],
                rename_map,
                out_path,
                spool_dir=staging.path,
                orig_index=orig_index,
                final_index=final_index,
            )
            stats["broken_refs_pre_existing"] += pre
            stats["broken_refs_introduced"] += intro
            staging_files[out_path.name] = finals[p.name]
        if stats["broken_refs_introduced"]:
            warnings.append(
                "introduced %d broken reference(s) during rewrite (tool defect)"
                % stats["broken_refs_introduced"]
            )
        inputs = [input_fingerprint(p) for p in fam.files]
        params = {
            "to": target,
            "quality": quality,
            "quality_mode": quality_mode,
            "quality_value": quality_value,
            "workers": workers,
            "collision": collision,
            "engine": engine_name,
            "engine_reason": engine_reason,
            "force": force,
            "inline_verify": inline_verify,
        }
        manifest = build_manifest(
            family_name, inputs, params, rename_map, warnings, stats
        )
        staging.commit(staging_files, dump_manifest(manifest), replace=redo)
        version_suffix = reader_suffix(readers[fam.files[0]])
        print(
            "family %s%s: %d transcoded, %d passed through, "
            "%d failed, %d collision(s), %d warning(s)"
            % (
                family_name,
                version_suffix,
                stats["transcoded"],
                stats["passed_through"],
                stats["failed"],
                stats["collisions"],
                len(warnings),
            )
        )
        for w in warnings:
            print("  warning: %s" % w)
        return 0
    except Exception as e:
        if os.environ.get("MDICT_AUDIO_DEBUG"):
            raise
        print("family %s failed: %s" % (family_name, e), file=sys.stderr)
        return 2
    finally:
        if not staging.committed:
            staging.clean()
