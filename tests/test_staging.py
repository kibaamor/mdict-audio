import os
from pathlib import Path

import pytest

from mdict_audio.staging import StagingArea


def test_commit_installs_outputs_and_manifest(tmp_path):
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")

    staging.commit({"a.mdd": tmp_path / "a.mdd"}, b'{"ok": true}')

    assert (tmp_path / "a.mdd").read_bytes() == b"new"
    assert (tmp_path / "fam.manifest.json").read_bytes() == b'{"ok": true}'
    assert staging.committed is True
    assert not staging.path.exists()


def test_commit_fails_when_target_exists_without_replace(tmp_path):
    (tmp_path / "a.mdd").write_bytes(b"old")
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")

    with pytest.raises(FileExistsError):
        staging.commit({"a.mdd": tmp_path / "a.mdd"}, b"{}")

    assert (tmp_path / "a.mdd").read_bytes() == b"old"


def test_commit_failure_removes_new_outputs_without_replace(tmp_path):
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")

    with pytest.raises(FileNotFoundError):
        staging.commit(
            {
                "a.mdd": tmp_path / "a.mdd",
                "missing.mdx": tmp_path / "missing.mdx",
            },
            b"{}",
        )

    assert not (tmp_path / "a.mdd").exists()
    assert not (tmp_path / "missing.mdx").exists()


def test_commit_replace_overwrites_existing_target(tmp_path):
    (tmp_path / "a.mdd").write_bytes(b"old")
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")

    staging.commit({"a.mdd": tmp_path / "a.mdd"}, b"{}", replace=True)

    assert (tmp_path / "a.mdd").read_bytes() == b"new"


def test_commit_replace_failure_does_not_restore_old_outputs(tmp_path):
    (tmp_path / "a.mdd").write_bytes(b"old")
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")

    with pytest.raises(FileNotFoundError):
        staging.commit(
            {
                "a.mdd": tmp_path / "a.mdd",
                "missing.mdx": tmp_path / "missing.mdx",
            },
            b"{}",
            replace=True,
        )

    assert (tmp_path / "a.mdd").read_bytes() == b"new"


def test_commit_keyboard_interrupt_rolls_back_without_replace(tmp_path, monkeypatch):
    staging = StagingArea(tmp_path, "fam")
    (staging.path / "a.mdd").write_bytes(b"new")
    (staging.path / "b.mdx").write_bytes(b"new")
    real_replace = os.replace

    def interrupt_on_second(src, dst):
        if Path(dst).name == "b.mdx":
            raise KeyboardInterrupt()
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", interrupt_on_second)

    with pytest.raises(KeyboardInterrupt):
        staging.commit(
            {"a.mdd": tmp_path / "a.mdd", "b.mdx": tmp_path / "b.mdx"},
            b"{}",
        )

    assert not (tmp_path / "a.mdd").exists()
    assert not (tmp_path / "b.mdx").exists()
