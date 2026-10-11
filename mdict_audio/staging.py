import os
import shutil
import uuid
from pathlib import Path


class StagingArea:
    def __init__(self, out_dir, family):
        self.out_dir = Path(out_dir)
        self.family = family
        self.path = self.out_dir / (".tmp-%s-%s" % (family, uuid.uuid4().hex[:12]))
        self.path.mkdir(parents=True)
        self.committed = False

    def clean(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def commit(self, final_paths, manifest_bytes, replace=False):
        tmp_manifest = self.path / "manifest.json.tmp"
        tmp_manifest.write_bytes(manifest_bytes)
        final_manifest = self.out_dir / ("%s.manifest.json" % self.family)
        installs = [
            (self.path / staging_name, final)
            for staging_name, final in final_paths.items()
        ]
        installs.append((tmp_manifest, final_manifest))

        installed = []
        try:
            for src, final in installs:
                final.parent.mkdir(parents=True, exist_ok=True)
                if final.exists() and not replace:
                    raise FileExistsError("target already exists: %s" % final)
                os.replace(src, final)
                installed.append(final)
            self.committed = True
            self.clean()
        except BaseException:
            if not replace:
                self._rollback_new_files(installed)
            raise

    def _rollback_new_files(self, installed):
        for final in reversed(installed):
            try:
                if final.exists():
                    final.unlink()
            except OSError:
                pass
