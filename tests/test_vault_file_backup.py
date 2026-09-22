"""Exercise maintenance cleanup without touching a cluster."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('vault_file_backup', Path(__file__).parents[1] / 'scripts/vault-file-backup.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VaultFileBackupTests(unittest.TestCase):
    def exercise(self, failure=None):
        calls = []
        replicas = 1
        paused = False
        copied = False

        def run(command, **kwargs):
            nonlocal replicas, paused, copied
            args = command[4:]
            calls.append(args)
            result = b''
            code = 0
            if args[:4] == ['-n', 'argocd', 'get', 'application']:
                result = json.dumps({'metadata': {'resourceVersion': '1', 'annotations': {'argocd.argoproj.io/skip-reconcile': 'true'} if paused else {}}, 'status': {}}).encode()
            elif args[:4] == ['-n', 'argocd', 'get', 'applicationset']:
                result = json.dumps({'spec': {'preservedFields': {'annotations': [] if failure == 'prerequisite' else ['argocd.argoproj.io/skip-reconcile']}}}).encode()
            elif 'patch' in args:
                paused = True
            elif args[:4] == ['-n', 'vault', 'get', 'statefulset']:
                result = json.dumps({'spec': {'replicas': 1 if copied and failure == 'writer' else replicas}}).encode()
            elif args[:4] == ['-n', 'vault', 'get', 'pod']:
                result = json.dumps({'spec': {'nodeName': 'node', 'containers': [{'name': 'vault', 'image': 'hashicorp/vault:1.21.2'}]}}).encode()
            elif args[-3:] == ['vault', 'status', '-format=json']:
                result = json.dumps({'storage_type': 'file', 'sealed': False, 'initialized': True, 'cluster_id': 'original'}).encode()
            elif 'scale' in args:
                replicas = int(args[-1].split('=')[1])
            elif 'tar' in args:
                copied = True
                if failure == 'copy':
                    code = 1
                else:
                    with tarfile.open(fileobj=kwargs['stdout'], mode='w:gz') as archive:
                        data = b'encrypted fixture'
                        entry = tarfile.TarInfo('./core/keyring')
                        entry.size = len(data)
                        archive.addfile(entry, io.BytesIO(data))
            elif failure == 'restart' and '--for=create' in args:
                code = 1
            return subprocess.CompletedProcess(command, code, result, b'')

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'backup.tar.gz'
            with patch.object(MODULE.subprocess, 'run', side_effect=run), patch('sys.argv', ['backup', '--kubeconfig', 'fixture', '--output', str(output)]):
                if failure:
                    with self.assertRaises(RuntimeError):
                        MODULE.main()
                else:
                    MODULE.main()
                    self.assertTrue(output.is_file())
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            if failure in ('copy', 'writer', 'prerequisite'):
                self.assertFalse(output.exists())
        return calls, replicas

    def test_success_restarts_before_resuming_reconciliation(self):
        calls, replicas = self.exercise()
        self.assertEqual(replicas, 1)
        restart = next(i for i, c in enumerate(calls) if '--for=create' in c)
        resume = next(i for i, c in enumerate(calls) if 'annotate' in c)
        self.assertLess(restart, resume)

    def test_copy_failure_still_recovers_production(self):
        calls, replicas = self.exercise('copy')
        self.assertEqual(replicas, 1)
        self.assertTrue(any('annotate' in c for c in calls))
        self.assertTrue(any('delete' in c for c in calls))

    def test_writer_restart_discards_archive_and_recovers(self):
        calls, replicas = self.exercise('writer')
        self.assertEqual(replicas, 1)
        self.assertTrue(any('annotate' in c for c in calls))

    def test_missing_pause_preservation_prevents_mutations(self):
        calls, replicas = self.exercise('prerequisite')
        self.assertEqual(replicas, 1)
        self.assertFalse(any('create' in c or 'scale' in c or 'patch' in c for c in calls))

    def test_restart_failure_keeps_reconciliation_paused(self):
        calls, _ = self.exercise('restart')
        self.assertFalse(any('annotate' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
