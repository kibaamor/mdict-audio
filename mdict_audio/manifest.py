import hashlib
import json
import time
from pathlib import Path

import mdict_audio


def input_fingerprint(path):
    path = Path(path)
    st = path.stat()
    with path.open("rb") as f:
        header_hash = hashlib.sha256(f.read(65536)).hexdigest()
    return {
        "path": str(path),
        "size": st.st_size,
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        "header_hash": header_hash,
    }


def build_manifest(family, inputs, params, rename_map, warnings, stats):
    return {
        "tool_version": mdict_audio.__version__,
        "family": family,
        "inputs": inputs,
        "params": params,
        "rename_map": rename_map,
        "warnings": warnings,
        "stats": stats,
    }


def dump_manifest(manifest):
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )
