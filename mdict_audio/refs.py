import re
from urllib.parse import quote, unquote

_SOUND_RE = re.compile(rb"sound://([^\s\"'<>]+)")
_SOUND_TEXT_RE = re.compile(r"sound://([^ \t\r\n\f\v\"'<>]+)")

_SOUND_EMPTY_RE = re.compile(rb"sound://(?![^\s\"'<>])")
_SOUND_EMPTY_TEXT_RE = re.compile(r"sound://(?![^ \t\r\n\f\v\"'<>])")

_VALID_COLLISION_STRATEGIES = {"rename", "skip", "overwrite"}


def normalize_ref(value):
    return value.replace("\\", "/").lstrip("/")


def _split_key(key):
    cut = max(key.rfind("/"), key.rfind("\\"))
    if cut < 0:
        return "", key
    return key[: cut + 1], key[cut + 1 :]


def _split_ext(key):
    prefix, name = _split_key(key)
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        return prefix + stem, "." + ext
    return prefix + name, ""


def replace_ext(key, new_ext):
    stem, _ = _split_ext(key)
    return stem + new_ext


def plan_renames_by_format(key_formats, target="mp3", force=False):
    rename_map = {}
    transcode_keys = set()
    for key, fmt in key_formats:
        if fmt == "unknown":
            continue
        if fmt == target:
            if force:
                transcode_keys.add(key)
            continue
        rename_map[key] = replace_ext(key, "." + target)
        transcode_keys.add(key)
    return rename_map, transcode_keys


def resolve_collisions(rename_map, all_keys, strategy="rename"):
    if strategy not in _VALID_COLLISION_STRATEGIES:
        raise ValueError("unknown collision strategy: %s" % strategy)
    occupied = set(all_keys)
    resolved = {}
    collisions = []
    dropped = set()
    skipped = set()
    overwrite_wins = set()
    for old in sorted(rename_map):
        desired = rename_map[old]
        if desired not in occupied:
            occupied.add(desired)
            resolved[old] = desired
            continue
        if strategy == "skip":
            resolved[old] = desired
            skipped.add(old)
            collisions.append((old, desired, "skipped", desired))
            continue
        if strategy == "overwrite" and desired not in overwrite_wins:
            resolved[old] = desired
            dropped.add(desired)
            overwrite_wins.add(desired)
            collisions.append((old, desired, "overwritten", desired))
            continue
        stem, ext = _split_ext(desired)
        attempt = 1
        while True:
            attempt += 1
            candidate = "%s.converted-%d%s" % (stem, attempt, ext)
            if candidate not in occupied:
                occupied.add(candidate)
                resolved[old] = candidate
                collisions.append((old, desired, "renamed", candidate))
                break
    return resolved, collisions, dropped, skipped


def build_match_index(rename_map):
    return {normalize_ref(k): v for k, v in rename_map.items()}


def resolve_ref(ref, index):
    if ref in index:
        return ref, None
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            decoded = unquote(ref, encoding=encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        decoded = normalize_ref(decoded)
        if decoded != ref and decoded in index:
            return decoded, encoding
    return None, None


def _rewrite_sound_refs_text(text, match_index):
    def replace(match):
        ref = match.group(1)
        key = normalize_ref(ref)
        new = match_index.get(key)
        if new is not None:
            decoded_hit, encoding = False, None
        else:
            key, encoding = resolve_ref(key, match_index)
            new = match_index.get(key) if key else None
            decoded_hit = key is not None
        if new is None:
            return match.group(0)
        stripped = new.lstrip("/\\")
        if decoded_hit and encoding:
            return "sound://" + quote(
                stripped.replace("\\", "/"), safe="/", encoding=encoding
            )
        if "\\" in ref and "/" not in ref:
            stripped = stripped.replace("/", "\\")
            if ref[:1] == "\\":
                stripped = "\\" + stripped
        else:
            stripped = stripped.replace("\\", "/")
            if ref[:1] == "/":
                stripped = "/" + stripped
        return "sound://" + stripped

    return _SOUND_TEXT_RE.sub(replace, text)


def _rewrite_sound_refs_bytes(record_bytes, match_index):
    def replace(match):
        ref = match.group(1)
        key = normalize_ref(ref.decode("utf-8", "ignore"))
        new = match_index.get(key)
        if new is not None:
            decoded_hit, encoding = False, None
        else:
            key, encoding = resolve_ref(key, match_index)
            new = match_index.get(key) if key else None
            decoded_hit = key is not None
        if new is None:
            return match.group(0)
        stripped = new.lstrip("/\\")
        if decoded_hit and encoding:
            try:
                return b"sound://" + quote(
                    stripped.replace("\\", "/"), safe="/", encoding=encoding
                ).encode(encoding)
            except UnicodeEncodeError:
                pass
        if b"\\" in ref and b"/" not in ref:
            stripped = stripped.replace("/", "\\")
            if ref[:1] == b"\\":
                stripped = "\\" + stripped
        else:
            stripped = stripped.replace("\\", "/")
            if ref[:1] == b"/":
                stripped = "/" + stripped
        return b"sound://" + stripped.encode("utf-8")

    return _SOUND_RE.sub(replace, record_bytes)


def rewrite_sound_refs(record_bytes, match_index, encoding="utf-8"):
    try:
        text = record_bytes.decode(encoding)
    except UnicodeDecodeError:
        return _rewrite_sound_refs_bytes(record_bytes, match_index)
    return _rewrite_sound_refs_text(text, match_index).encode(encoding)


def _extract_sound_refs_bytes(record_bytes):
    return [
        normalize_ref(m.group(1).decode("utf-8", "ignore"))
        for m in _SOUND_RE.finditer(record_bytes)
    ]


def extract_sound_refs(record_bytes, encoding="utf-8"):
    try:
        text = record_bytes.decode(encoding)
    except UnicodeDecodeError:
        return _extract_sound_refs_bytes(record_bytes)
    return [normalize_ref(m.group(1)) for m in _SOUND_TEXT_RE.finditer(text)]


def count_empty_sound_refs(record_bytes, encoding="utf-8"):
    try:
        text = record_bytes.decode(encoding)
    except UnicodeDecodeError:
        return len(_SOUND_EMPTY_RE.findall(record_bytes))
    return len(_SOUND_EMPTY_TEXT_RE.findall(text))


def classify_refs(orig_data, rewritten_data, orig_index, final_index, encoding="utf-8"):
    """Return (pre_existing, introduced) broken-ref counts for one entry."""
    pre_count = 0
    pre_refs = set()
    for ref in extract_sound_refs(orig_data, encoding):
        if resolve_ref(ref, orig_index)[0] is None:
            pre_count += 1
            pre_refs.add(ref)
    introduced = 0
    for ref in extract_sound_refs(rewritten_data, encoding):
        if ref in pre_refs:
            continue
        if resolve_ref(ref, final_index)[0] is None:
            introduced += 1
    return pre_count, introduced
