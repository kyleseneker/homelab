import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('vault_offsite', Path(__file__).parents[1] / 'scripts/vault-offsite-copy.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VaultOffsiteTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'fixture.tar.gz'
        source.write_bytes(b'encrypted archive fixture')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        (root / 'metadata.json').write_text(json.dumps({'bucket': 'fixture', 'region': 'us-east-1'}))
        return source, digest, root / 'download.tar.gz'

    def test_mismatch_or_existing_download_prevents_upload(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(MODULE.subprocess, 'run') as run:
            root = Path(directory)
            source, digest, target = self.fixture(root)
            with self.assertRaises(ValueError):
                MODULE.copy(source, root, 'wrong', target)
            target.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                MODULE.copy(source, root, digest, target)
            run.assert_not_called()
            self.assertEqual(target.read_bytes(), b'keep')

    def exercise_download(self, changed_version=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, digest, target = self.fixture(root)

            def run(args, **kwargs):
                self.assertNotIn('AWS_ACCESS_KEY_ID', kwargs['env'])
                if 'put-object' in args:
                    self.assertIn('--if-none-match', args)
                    response = {'VersionId': 'original'}
                else:
                    Path(args[-1]).write_bytes(source.read_bytes())
                    response = {'VersionId': 'changed' if changed_version else 'original', 'Metadata': {'sha256': digest}}
                return subprocess.CompletedProcess(args, 0, json.dumps(response).encode(), b'')

            with patch.object(MODULE.subprocess, 'run', side_effect=run), patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'ambient-fixture'}):
                if changed_version:
                    with self.assertRaisesRegex(RuntimeError, 'current version changed'):
                        MODULE.copy(source, root, digest, target)
                    self.assertFalse(target.exists())
                else:
                    MODULE.copy(source, root, digest, target)
                    self.assertEqual(target.read_bytes(), source.read_bytes())
                    self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_verified_private_download_ignores_ambient_credentials(self):
        self.exercise_download()

    def test_concurrent_version_change_rejects_download(self):
        self.exercise_download(changed_version=True)


if __name__ == '__main__':
    unittest.main()
