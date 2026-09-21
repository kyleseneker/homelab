"""Exercise embedded app scripts without a cluster or application credentials."""
import json
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


class OpenClawRuntimeTests(unittest.TestCase):
    def test_hook_modules_resolve_to_the_bootstrapped_transform_directory(self):
        config = json.loads(configmap_data(
            APPS / "openclaw/openclaw-config.yml"
        )["config.json5"])
        values = yaml.safe_load((APPS / "openclaw/values.yml").read_text())
        runtime_path = Path(values["controllers"]["main"]["containers"]["main"]
                            ["env"]["OPENCLAW_CONFIG_PATH"])
        root = runtime_path.parent / "hooks/transforms"
        # OpenClaw resolves this option relative to its transform root, not a shell.
        configured = root / config["hooks"].get("transformsDir", ".")
        transforms = configmap_data(APPS / "openclaw/hooks-transforms-configmap.yml")
        for mapping in config["hooks"]["mappings"]:
            module = mapping["transform"]["module"]
            self.assertEqual(configured / module, root / module)
            self.assertIn(module, transforms)

    def run_node(self, script):
        result = subprocess.run(
            ["node", "-"], input=script, text=True, capture_output=True, cwd=REPO
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_webhooks_read_context_payload(self):
        transforms = configmap_data(APPS / "openclaw/hooks-transforms-configmap.yml")
        self.run_node(
            "const sources = " + json.dumps(transforms) + ";\n" + r"""
const assert = require('node:assert/strict');
(async () => {
  const load = async name => (await import('data:text/javascript;base64,' +
    Buffer.from(sources[name]).toString('base64'))).default;
  const arr = await load('arr-webhook.js');
  const alerts = await load('alertmanager-webhook.js');
  assert.equal(arr({payload:{eventType:'Download',instanceName:'Sonarr',
    series:{title:'Example'}}}).message, '[Sonarr] Download: Example');
  assert.equal(arr({payload:{eventType:'Grab',instanceName:'Radarr',
    movie:{title:'A Movie'}}}).message, '[Radarr] Grab: A Movie');
  assert.match(alerts({payload:{status:'firing',alerts:[{
    labels:{severity:'critical',alertname:'AppDown',namespace:'arr'},
    annotations:{description:'unavailable'}}]}}).message,
    /FIRING:\n\[CRITICAL\] AppDown \(arr\): unavailable/);
  assert.match(alerts({payload:{status:'resolved',alerts:[{
    labels:{alertname:'Test'}}]}}).message, /RESOLVED/);
  assert.equal(alerts({payload:{}}).message,
    'Alertmanager webhook received with no alerts.');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

    def test_config_migration_preserves_token_and_reconciles_policy(self):
        values = yaml.safe_load((APPS / "openclaw/values.yml").read_text())
        script = values["controllers"]["main"]["initContainers"]["config"]["args"][0]
        config = configmap_data(APPS / "openclaw/openclaw-config.yml")["config.json5"]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            (fixture / "state").mkdir()
            (fixture / "config").mkdir()
            (fixture / "config/config.json5").write_text(config)
            script = script.replace("/state/", f"{fixture}/state/")
            script = script.replace("/config/", f"{fixture}/config/")
            self.run_node(
                "const fixture = " + json.dumps(str(fixture)) + ";\n"
                + "const script = " + json.dumps(script) + ";\n" + r"""
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const configPath = path.join(fixture, 'state/openclaw.json');
const run = () => vm.runInNewContext(script, {require});
run();
let actual = JSON.parse(fs.readFileSync(configPath));
assert.match(actual.gateway.auth.token, /^[a-f0-9]{64}$/);
assert.equal(fs.statSync(configPath).mode & 0o777, 0o600);
actual.gateway.auth.token = 'existing-ui-token';
actual.channels.slack.dmPolicy = 'open';
actual.channels.slack.allowFrom = ['*'];
fs.writeFileSync(configPath, JSON.stringify(actual));
run();
actual = JSON.parse(fs.readFileSync(configPath));
assert.equal(actual.gateway.auth.token, 'existing-ui-token');
assert.equal(actual.channels.slack.dmPolicy, 'pairing');
assert.equal(actual.channels.slack.allowFrom, undefined);
assert.equal(fs.statSync(configPath + '.pre-gitops').mode & 0o777, 0o600);
const migrationBackup = fs.readFileSync(configPath + '.pre-gitops', 'utf8');
run();
assert.equal(JSON.parse(fs.readFileSync(configPath)).gateway.auth.token, 'existing-ui-token');
assert.equal(fs.readFileSync(configPath + '.pre-gitops', 'utf8'), migrationBackup);
fs.writeFileSync(configPath, 'invalid-json');
assert.throws(run);
assert.equal(fs.readFileSync(configPath, 'utf8'), 'invalid-json');
"""
            )


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
