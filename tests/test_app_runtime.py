"""Exercise embedded app scripts without a cluster or application credentials."""
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
import zipfile

import yaml

REPO = Path(__file__).resolve().parents[1]
APPS = REPO / "k8s/clusters/homelabk8s01/apps"


def configmap_data(path):
    for document in yaml.safe_load_all(path.read_text()):
        if document and document.get("kind") == "ConfigMap":
            return document["data"]
    raise AssertionError(f"No ConfigMap found in {path}")


class RecyclarrRuntimeTests(unittest.TestCase):
    def test_process_identity_matches_nfs_media_identity(self):
        media = configmap_data(APPS / "arr/prereqs/env.yml")
        values = yaml.safe_load((APPS / "arr/recyclarr/values.yml").read_text())
        holder = yaml.safe_load((APPS / "arr/recyclarr/state-holder.yml").read_text())
        for security in (values["defaultPodOptions"]["securityContext"],
                         holder["spec"]["template"]["spec"]["securityContext"]):
            self.assertEqual(security["runAsUser"], int(media["PUID"]))
            self.assertEqual(security["runAsGroup"], int(media["PGID"]))
            self.assertEqual(security["fsGroup"], int(media["PGID"]))


class BackupRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.target = self.root / "backup"
        self.source.mkdir()
        self.target.mkdir()
        self.scripts = configmap_data(APPS / "arr/config-backup/script.yml")

    def run_script(self, script, **environment):
        script = script.replace('Path("/data")', f"Path({str(self.source)!r})")
        script = script.replace('Path("/backup")', f"Path({str(self.target)!r})")
        return subprocess.run(
            [os.sys.executable, "-c", script],
            env={**os.environ, **environment}, capture_output=True, text=True,
        )

    def test_both_sqlite_dumps_capture_committed_live_wal(self):
        writer = sqlite3.connect(self.source / "test.db")
        self.addCleanup(writer.close)
        writer.execute("pragma journal_mode=wal")
        writer.execute("create table records (value text)")
        writer.execute("insert into records values ('committed')")
        writer.commit()
        # Keep the writer open: the committed data is still in its WAL.
        cases = [
            (self.scripts["dump.py"], self.target / "fixture/test.db"),
            (configmap_data(APPS / "uptime-kuma/backup.yml")["dump.py"], self.target / "test.db"),
        ]
        for script, destination in cases:
            with self.subTest(destination=destination):
                result = self.run_script(script, APP_NAME="fixture")
                self.assertEqual(result.returncode, 0, result.stderr)
                with sqlite3.connect(destination) as restored:
                    self.assertEqual(restored.execute("pragma integrity_check").fetchone(), ("ok",))
                    self.assertEqual(restored.execute("select value from records").fetchone(), ("committed",))

    def test_stale_or_corrupt_native_archive_cannot_replace_last_good_copy(self):
        archive = self.source / "native.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("data.json", "{}")
        run = lambda: self.run_script(
            self.scripts["copy-latest.py"], APP_NAME="tdarr", SOURCE_DIR=str(self.source)
        )
        self.assertEqual(run().returncode, 0)
        destination = self.target / "tdarr/latest.zip"
        original = destination.read_bytes()
        stale = time.time() - 49 * 60 * 60
        os.utime(archive, (stale, stale))
        self.assertNotEqual(run().returncode, 0)
        self.assertEqual(destination.read_bytes(), original)
        archive.write_text("not a ZIP archive")
        self.assertNotEqual(run().returncode, 0)
        self.assertEqual(destination.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
