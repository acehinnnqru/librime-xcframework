#!/usr/bin/env python3
"""Check source-snapshot metadata and refusal of mismatched build refs."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMIT = "a" * 40


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="librime-source-test-")
        self.addCleanup(self.work.cleanup)
        self.source = Path(self.work.name) / "source"
        self.source.mkdir()
        (self.source / "CMakeLists.txt").write_text("set(rime_version 1.17.0)\n")
        self.marker = self.source / ".librime-source.json"
        self.marker.write_text(json.dumps({"repo": "rime/librime", "ref": "1.17.0", "commit": COMMIT}))
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("UPSTREAM_")}
        self.env.update(UPSTREAM_SOURCE_DIR=str(self.source), WORK_DIR=str(Path(self.work.name) / "work"), OUT_DIR=str(Path(self.work.name) / "out"))

    def resolve(self, **env):
        return subprocess.run([str(ROOT / "scripts/resolve-version.sh"), "--env"],
                              env=self.env | env, capture_output=True, text=True)

    def test_pinned_tag_version_and_commit(self):
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines())
        self.assertEqual(values["UPSTREAM_REF"], "1.17.0")
        self.assertEqual(values["UPSTREAM_VERSION"], "1.17.0")
        self.assertEqual(values["UPSTREAM_COMMIT"], COMMIT)

    def test_explicit_commit_is_reported(self):
        result = self.resolve(UPSTREAM_REF=COMMIT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPSTREAM_REF=" + COMMIT, result.stdout)

    def test_invalid_snapshot_commit_is_rejected(self):
        self.marker.write_text(json.dumps({"repo": "rime/librime", "ref": "1.17.0", "commit": "invalid"}))
        self.assertNotEqual(self.resolve().returncode, 0)

    def test_metadata_cannot_inject_environment_lines(self):
        self.marker.write_text(json.dumps({"repo": "rime/librime", "ref": "bad\nvalue", "commit": COMMIT}))
        self.assertNotEqual(self.resolve().returncode, 0)

    def test_non_snapshot_source_remains_a_worktree(self):
        self.marker.unlink()
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UPSTREAM_REF=worktree", result.stdout)
        self.assertIn("UPSTREAM_COMMIT=unknown", result.stdout)

    def test_build_rejects_nonmatching_ref_before_staging(self):
        result = subprocess.run([str(ROOT / "scripts/build-one-arch.sh"), "macos-arm64"],
                                env=self.env | {"UPSTREAM_REF": "wrong-ref"}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match source snapshot", result.stderr)
        self.assertFalse((Path(self.work.name) / "work/src-macos-arm64").exists())


if __name__ == "__main__":
    unittest.main()
