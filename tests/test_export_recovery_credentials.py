import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('export_recovery', Path(__file__).parents[1] / 'scripts/export-recovery-credentials.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExportRecoveryTests(unittest.TestCase):
    def outputs(self):
        values = {'kms_key_arn': 'arn:aws:kms:us-east-1:123456789012:key/fixture',
                  'kms_key_id': 'fixture', 'aws_access_key_id': 'kms-fixture',
                  'aws_secret_access_key': 'kms-secret-fixture',
                  'velero_offsite_access_key_id': 's3-fixture',
                  'velero_offsite_secret_access_key': 's3-secret-fixture',
                  'velero_offsite_bucket_name': 'fixture-bucket'}
        return {k: {'value': v} for k, v in values.items()}

    def test_private_complete_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / 'credentials'
            MODULE.export(self.outputs(), target)
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            for path in target.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((target / 'metadata.json').read_text())['region'], 'us-east-1')
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            with self.assertRaises(FileExistsError):
                MODULE.export(self.outputs(), target)
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_invalid_output_creates_no_partial_export(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / 'credentials'
            outputs = self.outputs()
            outputs['aws_secret_access_key']['value'] = 'bad\ninjected=value'
            with self.assertRaises(ValueError):
                MODULE.export(outputs, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
