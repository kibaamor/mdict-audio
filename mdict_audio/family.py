import re
from dataclasses import dataclass, field
from pathlib import Path

_VOLUME_RE = re.compile(r"(.+)\.(\d+)")


@dataclass
class Family:
    name: str
    mdx: list = field(default_factory=list)
    mdd: list = field(default_factory=list)

    @property
    def files(self):
        return self.mdx + self.mdd


class FamilyError(Exception):
    pass


def _volume_key(family_name):
    def key(p):
        if p.stem == family_name:
            return (0, 0, "")
        m = _VOLUME_RE.fullmatch(p.stem)
        if m and m.group(1) == family_name:
            return (1, int(m.group(2)), "")
        return (2, 0, p.name)
    return key


def discover(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise FamilyError("not a readable directory: %s" % directory)
    files = sorted(
        (p for p in directory.iterdir()
         if p.is_file() and p.suffix.lower() in {".mdx", ".mdd"}),
        key=lambda p: p.name.lower(),
    )
    bare_stems = {p.stem for p in files}
    families = {}
    for p in files:
        m = _VOLUME_RE.fullmatch(p.stem)
        base = m.group(1) if m and m.group(1) in bare_stems else p.stem
        fam = families.setdefault(base, Family(base))
        if p.suffix.lower() == ".mdx":
            fam.mdx.append(p)
        else:
            fam.mdd.append(p)
    for fam in families.values():
        key = _volume_key(fam.name)
        fam.mdx.sort(key=key)
        fam.mdd.sort(key=key)
    return families


def select(families, requested=None):
    if not families:
        raise FamilyError("no .mdx/.mdd files found in the input directory")
    if requested:
        missing = [name for name in requested if name not in families]
        if missing:
            raise FamilyError(
                "family not found: %s (available: %s)"
                % (", ".join(missing), ", ".join(sorted(families)))
            )
        return {name: families[name] for name in requested}
    if len(families) > 1:
        lines = ["multiple dictionary families found; select with --family <stem>:"]
        for name in sorted(families):
            fam = families[name]
            size = sum(p.stat().st_size for p in fam.files)
            lines.append(
                "  %-24s %d file(s), %d bytes: %s"
                % (name, len(fam.files), size, ", ".join(p.name for p in fam.files))
            )
        raise FamilyError("\n".join(lines))
    return dict(families)
