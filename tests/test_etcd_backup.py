import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).parents[1] / 'k8s/clusters/homelabk8s01/infrastructure/etcd-backup/scripts/backup.py'
spec = importlib.util.spec_from_file_location('etcd_backup', PATH)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class FakeS3:
    def __init__(self, corrupt=None):
        self.objects = {}
        self.calls = []
        self.corrupt = corrupt

    def put(self, name, path):
        self.calls.append(('put', name))
        value = path.read_bytes()
        if name in self.objects and self.objects[name] != value:
            raise ValueError('Conflicting object')
        self.objects[name] = value

    def verify(self, name, path):
        self.calls.append(('verify', name))
        if self.corrupt and name.startswith(self.corrupt):
            raise ValueError('Read-back mismatch')
        assert self.objects[name] == path.read_bytes()

    def names(self):
        return list(self.objects)

    def delete(self, name):
        self.calls.append(('delete', name))
        del self.objects[name]


class EtcdBackup(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.work, self.archive = [self.root / x for x in ('source', 'work', 'archive')]
        for directory in (self.source, self.work, self.archive):
            directory.mkdir()
        for name in backup.CONFIG_FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        pki = self.source / 'kubernetes/pki'
        pki.mkdir(); (pki / 'ca.crt').write_text('fixture CA')
        (self.work / 'snapshot.db').write_bytes(b'fixture snapshot')

    def prepare(self):
        backup.prepare(self.source, self.work, self.archive)
        return (self.work / 'current').read_text().strip()

    def test_completion_is_published_only_after_all_readbacks(self):
        timestamp = self.prepare()
        client = FakeS3()
        backup.upload(self.work, client)
        manifest = 'recovery-' + timestamp + '.json'
        self.assertEqual(client.calls[-2:], [('put', manifest), ('verify', manifest)])
        self.assertEqual(len(client.objects), 4)
        self.assertEqual((self.work / timestamp).stat().st_mode & 0o777, 0o750)

    def test_failed_readback_never_publishes_completion(self):
        self.prepare(); client = FakeS3(corrupt='pki-')
        with self.assertRaisesRegex(ValueError, 'Read-back'):
            backup.upload(self.work, client)
        self.assertFalse(any(name.startswith('recovery-') for name in client.objects))
        self.assertFalse(any(action == 'delete' for action, _ in client.calls))

    def test_retry_reuses_identical_objects(self):
        self.prepare(); client = FakeS3()
        backup.upload(self.work, client)
        before = dict(client.objects)
        backup.upload(self.work, client)
        self.assertEqual(client.objects, before)

    def test_corrupt_local_file_is_rejected_before_upload(self):
        timestamp = self.prepare(); client = FakeS3()
        (self.work / timestamp / ('snapshot-' + timestamp + '.db')).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Local recovery checksum'):
            backup.upload(self.work, client)
        self.assertEqual(client.calls, [])

    def test_current_job_cannot_mix_with_newer_archived_artifacts(self):
        timestamp = self.prepare(); client = FakeS3()
        (self.archive / 'snapshot-29990101-000000.db').write_bytes(b'unrelated')
        backup.upload(self.work, client)
        self.assertTrue(all(timestamp in name for name in client.objects))

    def test_missing_host_configuration_fails_before_publication(self):
        (self.source / 'kubelet-config.yaml').unlink()
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.prepare()
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_archive_rejects_symlinked_configuration(self):
        path = self.source / 'kubelet-config.yaml'
        path.unlink(); path.symlink_to(self.work / 'snapshot.db')
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.prepare()

    def test_legacy_pairs_survive_until_seven_complete_sets_exist(self):
        legacy = ['snapshot-20260101-000000.db', 'pki-20260101-000000.tar.gz']
        completed = ['recovery-2026020' + str(i) + '-000000.json' for i in range(1, 7)]
        self.assertEqual(backup.expired(legacy + completed), [])
        completed.append('recovery-20260207-000000.json')
        self.assertEqual(set(backup.expired(legacy + completed)), set(legacy))

    def test_retention_removes_old_manifest_before_its_files(self):
        names = ['recovery-2026020' + str(i) + '-000000.json' for i in range(1, 9)]
        names += ['snapshot-20260201-000000.db', 'pki-20260201-000000.tar.gz',
                  'control-plane-20260201-000000.tar.gz', 'unrelated.txt']
        removed = backup.expired(names)
        self.assertEqual(removed[0], 'recovery-20260201-000000.json')
        self.assertEqual(len(removed), 4)
        self.assertNotIn('unrelated.txt', removed)

    def test_offline_preparation_needs_no_live_cluster(self):
        for component in ('etcd', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler'):
            pod = {'kind': 'Pod', 'spec': {'containers': [{'name': component, 'image': 'fixture/' + component,
                                                         'command': [component, '--fixture=true']}]}}
            (self.source / 'kubernetes/manifests' / (component + '.yaml')).write_text(json.dumps(pod))
        timestamp = self.prepare()
        helper_spec = importlib.util.spec_from_file_location('prepare_recovery', Path(__file__).parents[1] / 'scripts/prepare-etcd-recovery.py')
        helper = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helper)
        output = self.root / 'offline'
        helper.prepare(self.archive / ('recovery-' + timestamp + '.json'), output)
        self.assertEqual((output / 'snapshot.db').read_bytes(), b'fixture snapshot')
        self.assertEqual(json.loads((output / 'etcd-source.json').read_text())['command'], ['etcd', '--fixture=true'])
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        with self.assertRaisesRegex(ValueError, 'existing'):
            helper.prepare(self.archive / ('recovery-' + timestamp + '.json'), output)

    def test_retention_ignores_wrong_artifact_extensions(self):
        names = ['recovery-2026020' + str(i) + '-000000.json' for i in range(1, 9)]
        names += ['snapshot-20260101-000000.json', 'pki-20260101-000000.db']
        self.assertEqual(backup.expired(names), ['recovery-20260201-000000.json'])

    def test_offline_reader_rejects_traversal_and_links(self):
        import tarfile
        from types import SimpleNamespace
        helper_spec = importlib.util.spec_from_file_location('prepare_recovery_guards', Path(__file__).parents[1] / 'scripts/prepare-etcd-recovery.py')
        helper = importlib.util.module_from_spec(helper_spec)
        helper_spec.loader.exec_module(helper)
        for name, kind in [('etc/kubernetes/../../outside', tarfile.REGTYPE),
                           ('etc/kubernetes/manifests/etcd.yaml', tarfile.SYMTYPE)]:
            member = tarfile.TarInfo(name); member.type = kind
            archive = SimpleNamespace(getmembers=lambda: [member])
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                helper.validate_archive(archive)

    def test_rendered_job_resolves_generated_script_configmap(self):
        import shutil
        import subprocess
        import yaml
        if shutil.which('kustomize'):
            command = ['kustomize', 'build']
        elif shutil.which('kubectl'):
            command = ['kubectl', 'kustomize']
        else:
            self.skipTest('requires a Kustomize binary')
        objects = list(yaml.safe_load_all(subprocess.check_output(command + [str(PATH.parents[1])], text=True)))
        config = next(obj for obj in objects if obj['kind'] == 'ConfigMap')
        job = next(obj for obj in objects if obj['kind'] == 'CronJob')
        volume = next(v for v in job['spec']['jobTemplate']['spec']['template']['spec']['volumes'] if v['name'] == 'scripts')
        self.assertEqual(config['metadata']['namespace'], job['metadata']['namespace'])
        self.assertEqual(volume['configMap']['name'], config['metadata']['name'])
