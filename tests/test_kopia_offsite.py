import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kopia_restore', Path(__file__).parents[1] / 'scripts/restore-kopia-offsite.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class ReadOnlyRecovery(unittest.TestCase):
    def prepare(self, root):
        credentials = root / 'credentials'
        credentials.mkdir(mode=0o700)
        (credentials / 'metadata.json').write_text(json.dumps({'credential_source': 'HCP Terraform homelab-aws', 'bucket': 'test', 'region': 'us-east-1'}))
        (credentials / 'velero-offsite.credentials').write_text('[default]\naws_access_key_id=test\naws_secret_access_key=test\n')
        password = root / 'password'
        password.write_text('test-only-password')
        password.chmod(0o600)
        return credentials, password

    def test_readonly_connection_and_temporary_credentials_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials, password = self.prepare(root)
            output = root / 'restore'
            with patch.object(restore.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'')) as run:
                restore.restore(credentials, password, 'arr', 'a' * 32, output, Path('/kopia'))
            connection = run.call_args_list[0]
            self.assertIn('--readonly', connection.args[0])
            self.assertIn('--no-persist-credentials', connection.args[0])
            self.assertNotIn('test-only-password', ' '.join(connection.args[0]))
            self.assertEqual(connection.kwargs['env']['KOPIA_PASSWORD'], 'test-only-password')
            self.assertEqual([p.name for p in output.iterdir()], ['retrieval.json'])
            with self.assertRaises(FileExistsError):
                restore.restore(credentials, password, 'arr', 'a' * 32, output, Path('/kopia'))

    def test_failed_reader_removes_connection_state_and_withholds_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials, password = self.prepare(root)
            with patch.object(restore.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'sensitive', stderr=b'sensitive')):
                with self.assertRaisesRegex(RuntimeError, 'output withheld'):
                    restore.restore(credentials, password, 'arr', 'a' * 32, root / 'restore', Path('/kopia'))
            self.assertEqual(list((root / 'restore').iterdir()), [])

    def test_rejects_parent_traversal_before_reading_credentials(self):
        with self.assertRaises(ValueError):
            restore.restore(Path('/unused'), Path('/unused'), 'arr', 'a' * 32 + '/../other', Path('/unused'), Path('/kopia'))
