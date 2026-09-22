"""Ensure lab auth configuration refuses unsafe starting states."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('restore_vault_auth', Path(__file__).parents[1] / 'scripts/restore-vault-auth.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestoreVaultAuthTests(unittest.TestCase):
    def test_non_lab_context_refuses_before_reading_admin_credential(self):
        with patch.object(MODULE, 'run', return_value=b'production\n') as run, patch.object(Path, 'read_text') as read:
            with self.assertRaisesRegex(RuntimeError, 'Expected the homelabrestore01'):
                MODULE.main()
            self.assertEqual(run.call_count, 1)
            read.assert_not_called()

    def test_sealed_vault_refuses_before_auth_mutations(self):
        responses = [b'homelabrestore01\n', json.dumps({'initialized': True, 'sealed': True}).encode()]
        with patch.object(MODULE, 'run', side_effect=responses) as run, patch.dict('os.environ', {'VAULT_TOKEN': 'test-fixture'}):
            with self.assertRaisesRegex(RuntimeError, 'Restore and auto-unseal'):
                MODULE.main()
            self.assertEqual(run.call_count, 2)
            self.assertNotIn('vault write', run.call_args.args[0][-1])

    def test_snapshot_auth_requires_raft_before_mutations(self):
        responses = [b'homelabrestore01\n', json.dumps({'initialized': True, 'sealed': False, 'storage_type': 'file'}).encode()]
        with patch.object(MODULE, 'run', side_effect=responses) as run, patch.dict('os.environ', {'VAULT_TOKEN': 'test-fixture'}):
            with self.assertRaisesRegex(RuntimeError, 'requires a migrated Raft'):
                MODULE.main(configure_snapshots=True)
            self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
