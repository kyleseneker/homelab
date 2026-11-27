import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

import yaml

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'k8s/clusters/homelabk8s01/infrastructure/restore-test/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('restore_test_etcd', SCRIPTS / 'restore_test_etcd.py')
etcd_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(etcd_check)


def pod_spec(path):
    for doc in yaml.safe_load_all(path.read_text()):
        if doc and doc.get('kind') == 'CronJob':
            return doc['spec']['jobTemplate']['spec']['template']['spec']


def write_set(root, stamp='20261127-020000', skip=None, corrupt=None):
    files = []
    for name in (f'snapshot-{stamp}.db', f'pki-{stamp}.tar.gz', f'control-plane-{stamp}.tar.gz'):
        if name.startswith('snapshot'):
            (root / name).write_bytes(b'snapshot')
        else:
            with tarfile.open(root / name, 'w:gz') as archive:
                info = tarfile.TarInfo('pki/ca.crt')
                info.size = 7
                archive.addfile(info, io.BytesIO(b'fixture'))
        data = (root / name).read_bytes()
        files.append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    if corrupt:
        next(root.glob(f'{corrupt}-{stamp}*')).write_bytes(b'tampered')
    if skip:
        files = [f for f in files if not f['name'].startswith(skip)]
    record = root / f'recovery-{stamp}.json'
    record.write_text(json.dumps({'schema': 1, 'timestamp': stamp, 'files': files}))
    return record


class Manifest(unittest.TestCase):
    def test_uses_the_etcd_image_the_backup_job_snapshots_with(self):
        backup = pod_spec(ROOT / 'k8s/clusters/homelabk8s01/infrastructure/etcd-backup/cronjob.yml')
        snapshot = next(c for c in backup['initContainers'] if c['name'] == 'snapshot')
        test = pod_spec(ROOT / 'k8s/clusters/homelabk8s01/infrastructure/restore-test/cronjob-etcd.yml')
        volume = next(v for v in test['volumes'] if v['name'] == 'etcd')
        self.assertEqual(volume['image']['reference'], snapshot['image'])

    def test_reads_the_snapshot_volume_on_the_backup_job_s_node(self):
        backup = pod_spec(ROOT / 'k8s/clusters/homelabk8s01/infrastructure/etcd-backup/cronjob.yml')
        test = pod_spec(ROOT / 'k8s/clusters/homelabk8s01/infrastructure/restore-test/cronjob-etcd.yml')
        claim = next(v for v in test['volumes'] if v['name'] == 'snapshots')['persistentVolumeClaim']
        self.assertEqual(claim, {'claimName': 'etcd-snapshots', 'readOnly': True})
        self.assertEqual(test['nodeSelector'], backup['nodeSelector'])
        self.assertEqual(test['securityContext']['runAsGroup'], 1000)

    def test_a_missing_result_alerts(self):
        rules = yaml.safe_load((SCRIPTS.parent / 'prometheusrule.yml').read_text())
        rule = next(r for g in rules['spec']['groups'] for r in g['rules'] if r.get('alert') == 'RestoreTestMissing')
        self.assertIn('target="etcd"', rule['expr'])


class RecoverySet(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_a_complete_matching_set_has_no_problems(self):
        snapshot, problems = etcd_check.verify_set(write_set(self.root))
        self.assertEqual(problems, [])
        self.assertEqual(snapshot.name, 'snapshot-20261127-020000.db')

    def test_a_changed_file_is_caught(self):
        snapshot, problems = etcd_check.verify_set(write_set(self.root, corrupt='pki'))
        self.assertEqual(problems, ['pki-20261127-020000.tar.gz does not match its checksum'])

    def test_a_set_without_its_control_plane_archive_is_incomplete(self):
        snapshot, problems = etcd_check.verify_set(write_set(self.root, skip='control-plane'))
        self.assertIn('no control-plane file', problems)

    def test_the_newest_set_is_chosen_by_its_timestamp(self):
        write_set(self.root, '20261126-020000')
        write_set(self.root, '20261127-020000')
        self.assertEqual(etcd_check.newest_record(self.root).name, 'recovery-20261127-020000.json')

    def test_set_time_is_utc(self):
        record = write_set(self.root, '19700101-000100')
        self.assertEqual(etcd_check.set_time(record), 60.0)


class Check(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        write_set(self.root)
        self.now = etcd_check.set_time(self.root / 'recovery-20261127-020000.json') + 1800
        self.saved = {name: getattr(etcd_check, name) for name in ('restore', 'serve', 'count')}
        self.addCleanup(lambda: [setattr(etcd_check, k, v) for k, v in self.saved.items()])

    def run_check(self, restored=True, served=True, keys=1234, known=True):
        class Process:
            def terminate(self):
                pass

            def wait(self, timeout=None):
                pass

        etcd_check.restore = lambda binaries, snapshot, data: restored
        etcd_check.serve = lambda binaries, data: Process() if served else None
        etcd_check.count = lambda key, end=None: keys if end else (1 if known else 0)
        return etcd_check.check(self.root, Path('/bin'), self.root, self.now)

    def test_a_restorable_snapshot_with_its_keys_passes(self):
        result = self.run_check()
        self.assertEqual(result['tiers'], {'restored': True, 'intact': True, 'fresh': True, 'usable': True, 'answers': True})
        self.assertEqual(result['rows'], {'keys': 1234})

    def test_a_snapshot_etcd_cannot_restore_fails(self):
        result = self.run_check(restored=False)
        self.assertEqual((result['tiers']['usable'], result['tiers']['answers']), (False, False))

    def test_a_missing_namespace_fails_the_answers_tier(self):
        self.assertFalse(self.run_check(known=False)['tiers']['answers'])

    def test_an_old_set_is_stale(self):
        self.now += 26 * 3600
        self.assertFalse(self.run_check()['tiers']['fresh'])

    def test_no_set_fails_the_first_tier(self):
        result = etcd_check.check(self.root / 'empty', Path('/bin'), self.root, self.now)
        self.assertEqual(result['tiers'], {'restored': False})

    def test_a_crash_is_still_reported(self):
        pushed = []
        saved = etcd_check.check, etcd_check.push
        self.addCleanup(lambda: (setattr(etcd_check, 'check', saved[0]), setattr(etcd_check, 'push', saved[1])))
        etcd_check.check = lambda *args: 1 / 0
        etcd_check.push = lambda gateway, source, result, now: pushed.append(result)
        code = etcd_check.main({'SNAPSHOTS': '/s', 'ETCD_BIN': '/b', 'WORK': '/w', 'PUSHGATEWAY_URL': 'http://p', 'SOURCE': 'local'})
        self.assertEqual(code, 1)
        self.assertEqual(pushed[0]['tiers'], {'restored': False})


if __name__ == '__main__':
    unittest.main()
