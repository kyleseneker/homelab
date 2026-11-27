import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

import yaml

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'k8s/clusters/homelabk8s01/infrastructure/restore-test/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load('restore_test')
check_sqlite = load('check_sqlite')
SONARR = harness.TARGETS[0]
DEPLOYMENT = {'spec': {'template': {'spec': {'containers': [{
    'image': 'lscr.io/linuxserver/sonarr:4.0.20',
    'env': [{'name': 'SONARR__AUTH__METHOD', 'value': 'External'},
            {'name': 'SONARR__AUTH__APIKEY', 'value': 'production'},
            {'name': 'FROM_SECRET', 'valueFrom': {'secretKeyRef': {'name': 's', 'key': 'k'}}}],
    'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'add': ['CHOWN'], 'drop': ['ALL']}},
    'resources': {'limits': {'cpu': '500m', 'memory': '1Gi'}},
}]}}}}
ENVIRON = {'SOURCE': 'local', 'SCHEDULE': 'velero-daily-stateful', 'MAX_BACKUP_AGE_SECONDS': '100800',
           'PUSHGATEWAY_URL': 'http://pushgateway:9091', 'CHECK_IMAGE': 'python:3.15-alpine'}


class Restore(unittest.TestCase):
    def test_matches_the_restore_the_admission_policy_test_allows(self):
        fixtures = yaml.safe_load_all((ROOT / 'tests/kyverno/restore-test/resources.yaml').read_text())
        allowed = next(f for f in fixtures if f['kind'] == 'Restore' and f['metadata']['name'] == 'valid')
        built = harness.restore_body('restore-test-local-1', 'velero-daily-stateful', {'media'})
        self.assertEqual(built['spec'], allowed['spec'])
        self.assertEqual(built['metadata']['namespace'], allowed['metadata']['namespace'])

    def test_maps_every_target_namespace_into_the_sandbox(self):
        built = harness.restore_body('r', 'velero-daily-stateful', {'media', 'auth'})
        self.assertEqual(built['spec']['includedNamespaces'], ['auth', 'media'])
        self.assertEqual(set(built['spec']['namespaceMapping'].values()), {'restore-sandbox'})


class Pods(unittest.TestCase):
    def containers(self, pod):
        spec = pod['spec']
        return spec.get('initContainers', []) + spec['containers']

    def test_integrity_check_reads_the_restored_claim_as_the_holder_user(self):
        pod = harness.integrity_pod(SONARR, 'python:3.15-alpine', 'print()')
        (check,) = pod['spec']['containers']
        self.assertEqual(pod['metadata']['namespace'], 'restore-sandbox')
        self.assertFalse(pod['spec']['automountServiceAccountToken'])
        self.assertEqual(check['command'][3:], ['/backup/sonarr/sonarr.db', 'Series', 'Episodes', 'EpisodeFiles'])
        self.assertEqual(check['securityContext']['runAsUser'], 977)
        claim = next(v for v in pod['spec']['volumes'] if v['name'] == 'backup')
        self.assertEqual(claim['persistentVolumeClaim'], {'claimName': 'config-backups', 'readOnly': True})

    def test_app_runs_the_production_image_with_a_throwaway_key(self):
        pod = harness.app_pod(SONARR, DEPLOYMENT, 'python:3.15-alpine', 'key', 'print()')
        app = next(c for c in pod['spec']['containers'] if c['name'] == 'app')
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        (copy,) = pod['spec']['initContainers']
        self.assertEqual(app['image'], 'lscr.io/linuxserver/sonarr:4.0.20')
        self.assertEqual(app['securityContext']['capabilities']['add'], ['CHOWN'])
        self.assertEqual(app['env'], [{'name': 'SONARR__AUTH__METHOD', 'value': 'External'},
                                      {'name': 'SONARR__AUTH__APIKEY', 'value': 'key'}])
        self.assertIn({'name': 'API_KEY', 'value': 'key'}, check['env'])
        self.assertEqual(copy['command'][-2:], ['/backup/sonarr/sonarr.db', '/config/sonarr.db'])
        self.assertFalse(pod['spec']['automountServiceAccountToken'])

    def test_every_container_has_limits(self):
        pods = [harness.integrity_pod(SONARR, 'python:3.15-alpine', ''),
                harness.app_pod(SONARR, DEPLOYMENT, 'python:3.15-alpine', 'key', '')]
        for pod in pods:
            for container in self.containers(pod):
                self.assertIn('limits', container['resources'], container['name'])


class Results(unittest.TestCase):
    def result(self, **tiers):
        return {'tiers': tiers, 'fences': {'watch_namespace': True}, 'rows': {'Series': 3},
                'duration': 61.4, 'data_age': 3600.2, 'bytes': 1024}

    def test_success_records_its_time(self):
        result = self.result(restored=True, intact=True)
        result['passed'] = harness.passed(result)
        text = harness.metrics(result, 1000.0)
        self.assertIn('restore_test_last_success_timestamp_seconds 1000\n', text)
        self.assertIn('restore_test_tier_passed{tier="intact"} 1\n', text)
        self.assertIn('restore_test_rows{table="Series"} 3\n', text)

    def test_failure_keeps_the_previous_success(self):
        result = self.result(restored=True, intact=False)
        result['passed'] = harness.passed(result)
        text = harness.metrics(result, 1000.0)
        self.assertNotIn('last_success', text)
        self.assertIn('restore_test_last_attempt_timestamp_seconds 1000\n', text)

    def test_nothing_checked_is_not_a_pass(self):
        self.assertFalse(harness.passed({'tiers': {}, 'fences': {}}))

    def test_a_broken_fence_fails_the_target(self):
        result = self.result(restored=True)
        result['fences']['arrchitect_refused'] = False
        self.assertFalse(harness.passed(result))


class FakeApi:
    def __init__(self, sandbox_exists):
        self.sandbox_exists = sandbox_exists
        self.calls = []

    def call(self, method, path, body=None, query=None):
        self.calls.append((method, path))
        if path == '/api/v1/namespaces/restore-sandbox':
            return (200 if self.sandbox_exists else 404), ''
        return 404, ''


class Execution(unittest.TestCase):
    def run_harness(self, api, **overrides):
        run = harness.Run(api, ENVIRON)
        run.push = lambda *args: None
        for name, value in overrides.items():
            setattr(run, name, value)
        return run, run.execute()

    def test_a_leftover_sandbox_fails_the_run_and_is_left_alone(self):
        api = FakeApi(sandbox_exists=True)
        run, code = self.run_harness(api)
        self.assertEqual(code, 1)
        self.assertNotIn(('DELETE', '/api/v1/namespaces/restore-sandbox'), api.calls)
        self.assertEqual(run.results['sonarr']['tiers'], {'restored': False})

    def test_an_error_after_the_integrity_check_fails_the_remaining_tiers(self):
        def check(target, backup_age):
            run.results[target['name']]['tiers'].update(intact=True)
            raise RuntimeError('app pod rejected')

        run = harness.Run(FakeApi(sandbox_exists=False), ENVIRON)
        run.push = lambda *args: None
        run.cleanup = lambda: None
        run.latest_finished = lambda: True
        run.create_sandbox = lambda: setattr(run, 'created', True)
        run.fences = lambda: {'watch_namespace': True, 'arrchitect_refused': True}
        run.arrchitect_absent = lambda: True
        run.newest_completed = lambda: 'backup'
        run.restore_started = 0.0
        run.run_restore = lambda: {'spec': {'backupName': 'backup'}, 'status': {'phase': 'Completed'}}
        run.volume_restores = lambda: []
        run.restored_volume = lambda target, pods, restores: ('Completed', 10)
        run.check = check
        run.api.json = lambda method, path, *a, **k: (
            {'status': {'startTimestamp': '2026-11-27T03:00:00Z'}} if '/backups/' in path else {'items': []})
        self.assertEqual(run.execute(), 1)
        tiers = run.results['sonarr']['tiers']
        self.assertTrue(tiers['intact'])
        self.assertFalse(tiers['usable'])
        self.assertFalse(tiers['answers'])


class Sqlite(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'sonarr.db'
        connection = sqlite3.connect(self.path)
        connection.executescript('CREATE TABLE "Series" (Id INTEGER PRIMARY KEY); '
                                 'CREATE TABLE "Episodes" (Id INTEGER PRIMARY KEY); '
                                 'INSERT INTO "Series" VALUES (1), (2); INSERT INTO "Episodes" VALUES (1);')
        connection.close()

    def test_a_sound_database_passes_with_its_counts(self):
        report, passed = check_sqlite.check(self.path, ['Series', 'Episodes'])
        self.assertTrue(passed)
        self.assertEqual(report['rows'], {'Series': 2, 'Episodes': 1})

    def test_an_empty_table_fails(self):
        sqlite3.connect(self.path).executescript('DELETE FROM "Episodes";')
        report, passed = check_sqlite.check(self.path, ['Series', 'Episodes'])
        self.assertFalse(passed)

    def test_a_missing_table_fails(self):
        report, passed = check_sqlite.check(self.path, ['Series', 'History'])
        self.assertFalse(passed)
        self.assertEqual(report, {'error': 'OperationalError'})

    def test_a_file_that_is_not_a_database_fails(self):
        self.path.write_bytes(b'not a database' * 100)
        report, passed = check_sqlite.check(self.path, ['Series'])
        self.assertFalse(passed)


if __name__ == '__main__':
    unittest.main()
