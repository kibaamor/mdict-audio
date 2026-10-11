from mdict_audio.container.writer import write_mdict
from mdict_audio.pipeline.progress import ProgressReporter, counted
from mdict_audio.refs import build_match_index, classify_refs, rewrite_sound_refs


def convert_mdx(
    reader,
    family_map,
    out_path,
    spool_dir=None,
    orig_index=None,
    final_index=None,
):
    match_index = build_match_index(family_map)
    counts = [0, 0]

    def entries():
        for key, data in reader.iter_records():
            orig = data
            if match_index:
                data = rewrite_sound_refs(data, match_index, reader.encoding)
            if orig_index is not None and final_index is not None:
                pre, intro = classify_refs(
                    orig, data, orig_index, final_index, reader.encoding
                )
                counts[0] += pre
                counts[1] += intro
            yield key, data

    progress = ProgressReporter(len(reader.keys()), "Rewriting %s" % out_path.name)
    try:
        with open(out_path, "wb") as f:
            write_mdict(
                f,
                counted(entries(), progress),
                is_mdd=False,
                encoding=reader.encoding,
                title=reader.header.get("Title", ""),
                description=reader.header.get("Description", ""),
                header=reader.header,
                sort_entries=False,
                spool_dir=spool_dir,
            )
    finally:
        progress.finish()
    return counts[0], counts[1]
