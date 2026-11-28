import datetime
import http.server
import importlib.util
import io
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import zipfile

import yaml

ROOT = Path(__file__).parents[1]
APP = ROOT / 'k8s/clusters/homelabk8s01/infrastructure/restore-test'


def load(name):
    spec = importlib.util.spec_from_file_location(name, APP / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load('restore_test')
check_sqlite = load('check_sqlite')
check_zip = load('check_zip')
check_ha = load('check_ha')
check_api = load('check_api')
TARGETS = {t['name']: t for t in harness.TARGETS}
SCRIPTS = {'check_sqlite': 'S', 'check_zip': 'Z', 'check_ha': 'H', 'check_pgdump': 'P', 'check_api': 'A',
           'check_postgres': 'Q'}
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
        namespaces = {t['namespace'] for t in harness.TARGETS}
        self.assertEqual(namespaces, {'media', 'monitoring', 'auth', 'home-automation'})
        built = harness.restore_body('r', 'velero-daily-stateful', namespaces)
        self.assertEqual(set(built['spec']['namespaceMapping'].values()), {'restore-sandbox'})

    def test_every_target_claim_is_labelled_as_a_backup_volume(self):
        manifests = [p for p in (ROOT / 'k8s/clusters/homelabk8s01').rglob('*.yml')]
        labelled = set()
        for path in manifests:
            for doc in yaml.safe_load_all(path.read_text()):
                if isinstance(doc, dict) and doc.get('kind') == 'PersistentVolumeClaim':
                    labels = doc['metadata'].get('labels', {})
                    if labels.get('app.kubernetes.io/component') == 'backup-volume':
                        labelled.add((doc['metadata']['namespace'], doc['metadata']['name']))
        for target in harness.TARGETS:
            self.assertIn((target['namespace'], target['claim']), labelled, target['name'])


class Pods(unittest.TestCase):
    def command(self, name):
        pod = harness.integrity_pod(TARGETS[name], 'image', (1, 2), SCRIPTS)
        return pod['spec']['containers'][0]['command']

    def test_each_kind_runs_its_own_check(self):
        self.assertEqual(self.command('sonarr'), ['python3', '-c', 'S', '/backup/sonarr/sonarr.db',
                                                  'Series', 'Episodes,EpisodeFiles', '1', '{}'])
        self.assertEqual(self.command('jellyfin'), ['python3', '-c', 'S', '/backup/jellyfin/data/data/jellyfin.db',
                                                    '', '', '0', '{}'])
        self.assertEqual(self.command('uptime-kuma')[-1], '{}')
        self.assertEqual(self.command('tdarr'), ['python3', '-c', 'Z', '/backup/tdarr/latest.zip',
                                                 'DB2/SQL/database.db', '/work',
                                                 'librarysettingsjsondb,flowsjsondb,variablesjsondb,filejsondb'])
        self.assertEqual(self.command('home-assistant'), ['python3', '-c', 'H', '/backup'])
        self.assertEqual(self.command('authentik'), ['sh', '-c', 'P', 'check', '/backup/authentik.dump',
                                                     '/backup/completed-at'])

    def test_checks_read_the_claim_as_the_holder_user(self):
        pod = harness.integrity_pod(TARGETS['uptime-kuma'], 'image', (1000, 1000), SCRIPTS)
        (check,) = pod['spec']['containers']
        self.assertEqual((check['securityContext']['runAsUser'], check['securityContext']['runAsGroup']), (1000, 1000))
        self.assertFalse(pod['spec']['automountServiceAccountToken'])
        claim = next(v for v in pod['spec']['volumes'] if v['name'] == 'backup')
        self.assertEqual(claim['persistentVolumeClaim'], {'claimName': 'uptime-kuma-backups', 'readOnly': True})

    def test_app_runs_the_production_image_with_a_throwaway_key(self):
        pod = harness.app_pod(TARGETS['sonarr'], DEPLOYMENT, 'python:3.15-alpine', (977, 988), 'key', 'A')
        app = next(c for c in pod['spec']['containers'] if c['name'] == 'app')
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        (copy,) = pod['spec']['initContainers']
        self.assertEqual(app['image'], 'lscr.io/linuxserver/sonarr:4.0.20')
        self.assertEqual(app['resources'], {'requests': {'cpu': '50m', 'memory': '256Mi'},
                                            'limits': {'cpu': '500m', 'memory': '1Gi'}})
        self.assertEqual(app['env'], [{'name': 'SONARR__AUTH__METHOD', 'value': 'External'},
                                      {'name': 'SONARR__AUTH__APIKEY', 'value': 'key'}])
        self.assertIn({'name': 'API_KEY', 'value': 'key'}, check['env'])
        spec = json.loads(copy['command'][-1])
        self.assertEqual((spec['source'], spec['mount']), ('/backup/sonarr', '/config'))
        self.assertEqual(json.loads(check['command'][-1]),
                         {'port': 8989, 'status': '/api/v3/system/status',
                          'probe': {'path': '/api/v3/series', 'count_table': 'Series'}})

    def test_tdarr_runs_only_its_server_on_its_extracted_archive(self):
        deployment = json.loads(json.dumps(DEPLOYMENT))
        live = deployment['spec']['template']['spec']['containers'][0]
        live['env'] = [{'name': 'internalNode', 'value': 'true'}, {'name': 'auth', 'value': 'false'}]
        live['resources']['limits']['gpu.intel.com/i915'] = 1
        pod = harness.app_pod(TARGETS['tdarr'], deployment, 'python:3.15-alpine', (977, 988), 'key', 'A')
        app = next(c for c in pod['spec']['containers'] if c['name'] == 'app')
        (copy,) = pod['spec']['initContainers']
        self.assertEqual(app['env'], [{'name': 'auth', 'value': 'false'}, {'name': 'internalNode', 'value': 'false'},
                                      {'name': 'cronPluginUpdate', 'value': ''}])
        self.assertEqual(app['resources']['limits'], {'cpu': '500m', 'memory': '1Gi'})
        self.assertEqual(json.loads(copy['command'][-1]),
                         {'source': '/backup/tdarr/latest.zip', 'extract_to': '/app/server/Tdarr',
                          'mount': '/app/server', 'files': {}})

    def test_an_archive_is_unpacked_into_the_app_and_unsafe_members_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, mount = root / 'latest.zip', root / 'server'
            with zipfile.ZipFile(archive, 'w') as handle:
                handle.writestr('DB2/SQL/database.db', 'db')
                handle.writestr('Plugins/x.js', 'plugin')
            mount.mkdir()
            spec = {'source': str(archive), 'extract_to': str(mount / 'Tdarr'), 'mount': str(mount), 'files': {}}
            subprocess.run([sys.executable, '-c', harness.COPY, json.dumps(spec)], check=True)
            self.assertEqual((mount / 'Tdarr/DB2/SQL/database.db').read_text(), 'db')
            self.assertEqual((mount / 'Tdarr/Plugins/x.js').stat().st_mode & 0o777, 0o666)
            with zipfile.ZipFile(archive, 'w') as handle:
                handle.writestr('../escape', 'x')
            refused = subprocess.run([sys.executable, '-c', harness.COPY, json.dumps(spec)], capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((root / 'escape').exists())

    def test_the_app_root_is_rebuilt_from_its_dump_tree(self):
        self.assertEqual(harness.dump_root(TARGETS['jellyfin']), '/backup/jellyfin')
        self.assertEqual(harness.dump_root(TARGETS['uptime-kuma']), '/backup')

    def test_the_copied_files_are_writable_by_whatever_user_the_app_runs_as(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, mount = root / 'source', root / 'config'
            (source / 'db').mkdir(parents=True)
            (source / 'db/app.db').write_bytes(b'data')
            (source / 'db/app.db').chmod(0o600)
            (source / 'settings.json').write_text('{}')
            mount.mkdir()
            mount.chmod(0o770)
            spec = {'source': str(source), 'mount': str(mount),
                    'files': {str(mount / 'config/config.yaml'): 'auth:\n  apikey: key\n'}}
            subprocess.run([sys.executable, '-c', harness.COPY, json.dumps(spec)], check=True)
            self.assertEqual((mount / 'db/app.db').read_bytes(), b'data')
            self.assertEqual((mount / 'settings.json').read_text(), '{}')
            self.assertEqual(mount.stat().st_mode & 0o777, 0o770)
            self.assertEqual((mount / 'db/app.db').stat().st_mode & 0o777, 0o666)
            self.assertEqual((mount / 'config/config.yaml').read_text(), 'auth:\n  apikey: key\n')
            self.assertEqual((mount / 'db').stat().st_mode & 0o777, 0o777)

    def test_pvr_apps_take_their_key_from_the_environment(self):
        self.assertEqual(TARGETS['radarr']['app']['api_key_env'], 'RADARR__AUTH__APIKEY')
        self.assertEqual(TARGETS['prowlarr']['app']['probe']['path'], '/api/v1/applications')

    def test_uptime_kuma_runs_as_in_production_and_stops_at_startup(self):
        workload = {'spec': {'template': {'spec': {
            'securityContext': {'runAsUser': 1000, 'runAsGroup': 1000, 'fsGroup': 1000, 'runAsNonRoot': True},
            'containers': [{'image': 'louislam/uptime-kuma:2.5.8', 'env': [], 'resources': {'limits': {'cpu': '1'}},
                            'securityContext': {'readOnlyRootFilesystem': True}}]}}}}
        pod = harness.app_pod(TARGETS['uptime-kuma'], workload, 'image', (1000, 1000), 'key', 'A')
        app = next(c for c in pod['spec']['containers'] if c['name'] == 'app')
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        self.assertEqual(pod['spec']['securityContext']['runAsUser'], 1000)
        self.assertEqual(pod['spec']['securityContext']['seccompProfile'], {'type': 'RuntimeDefault'})
        self.assertIn({'name': 'scratch-0', 'mountPath': '/tmp'}, app['volumeMounts'])
        self.assertIn({'name': 'scratch-0', 'emptyDir': {}}, pod['spec']['volumes'])
        self.assertEqual(json.loads(check['command'][-1]), {'port': 3001, 'status': '/api/entry-page', 'probe': None})
        self.assertNotIn('API_KEY', [e['name'] for e in check['env']])

    def test_each_app_gets_its_own_startup_window(self):
        pod = harness.app_pod(TARGETS['bazarr'], DEPLOYMENT, 'image', (977, 988), 'k3y', 'A')
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        self.assertIn({'name': 'STARTUP_TIMEOUT', 'value': '900'}, check['env'])
        self.assertEqual(TARGETS['sonarr']['app']['startup_timeout'], 600)

    def test_bazarr_gets_its_throwaway_key_through_a_seeded_config(self):
        pod = harness.app_pod(TARGETS['bazarr'], DEPLOYMENT, 'image', (977, 988), 'k3y', 'A')
        spec = json.loads(pod['spec']['initContainers'][0]['command'][-1])
        self.assertEqual(spec['files'], {'/config/config/config.yaml': 'auth:\n  apikey: k3y\n'})
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        self.assertIn({'name': 'API_KEY', 'value': 'k3y'}, check['env'])

    def test_a_probe_value_the_database_lacks_stays_unresolved(self):
        self.assertIsNone(harness.resolve('/api/status-page/{status_page}', {'status_page': None}))
        self.assertIsNone(harness.resolve('/api/status-page/{status_page}', {}))
        self.assertEqual(harness.resolve(True, {}), True)

    def test_every_container_has_limits(self):
        for target in harness.TARGETS:
            pods = [harness.integrity_pod(target, 'image', (1, 2), SCRIPTS)]
            if 'app' in target:
                pods.append(harness.app_pod(target, DEPLOYMENT, 'image', (1, 2), 'key', 'A'))
            if 'database' in target:
                pods.append(harness.postgres_pod(target, 'server', 'client', (1, 2), 'Q'))
            for pod in pods:
                for container in pod['spec'].get('initContainers', []) + pod['spec']['containers']:
                    self.assertIn('limits', container['resources'], (target['name'], container['name']))


class Database(unittest.TestCase):
    def test_the_dump_restores_into_a_scratch_server_running_production_s_image(self):
        pod = harness.postgres_pod(TARGETS['authentik'], 'postgres:17.11-bookworm', 'postgres:17.11-bookworm',
                                   (977, 988), 'Q')
        server = next(c for c in pod['spec']['containers'] if c['name'] == 'server')
        check = next(c for c in pod['spec']['containers'] if c['name'] == 'check')
        self.assertEqual(server['image'], 'postgres:17.11-bookworm')
        self.assertEqual(server['securityContext']['runAsUser'], 999)
        self.assertIn({'name': 'POSTGRES_HOST_AUTH_METHOD', 'value': 'trust'}, server['env'])
        self.assertEqual(check['securityContext']['runAsUser'], 977)
        self.assertEqual(check['command'], ['sh', '-c', 'Q', 'check', '/backup/authentik.dump',
                                            'authentik_core_user', 'authentik_core_group',
                                            'authentik_core_application', 'authentik_flows_flow'])
        volumes = {v['name'] for v in pod['spec']['volumes']}
        self.assertEqual(volumes, {'backup', 'data', 'run', 'server-tmp', 'work'})

    def run_check(self, ran, report):
        run = harness.Run(None, ENVIRON)
        run.server_image = lambda target: 'server'
        run.run_pod = lambda pod, container, timeout: (ran, report)
        run.check_database(TARGETS['authentik'], (977, 988), 'client')
        return run.results['authentik']

    def test_a_restored_database_with_rows_in_every_table_passes(self):
        rows = {t: 3 for t in TARGETS['authentik']['database']['tables']}
        result = self.run_check(True, {'started': True, 'restored': True, 'rows': rows})
        self.assertEqual(result['tiers'], {'usable': True, 'answers': True})
        self.assertEqual(result['rows'], rows)

    def test_an_empty_table_fails_the_answers_tier(self):
        rows = {t: 3 for t in TARGETS['authentik']['database']['tables']}
        rows['authentik_core_application'] = 0
        result = self.run_check(True, {'started': True, 'restored': True, 'rows': rows})
        self.assertEqual(result['tiers'], {'usable': True, 'answers': False})

    def test_a_failed_restore_fails_both_tiers(self):
        result = self.run_check(False, {'started': True, 'restored': False})
        self.assertEqual(result['tiers'], {'usable': False, 'answers': False})


class Freshness(unittest.TestCase):
    def test_a_dump_written_before_a_recent_backup_is_fresh(self):
        self.assertTrue(harness.fresh(1000.0, 1000.0 - 3600, 1000.0 + 600, 100800, 26 * 3600))

    def test_a_dump_older_than_its_limit_is_stale(self):
        self.assertFalse(harness.fresh(1000.0, 1000.0 - 27 * 3600, 1000.0, 100800, 26 * 3600))

    def test_an_old_backup_is_stale(self):
        self.assertFalse(harness.fresh(1000.0, 999.0, 1000.0 + 100801, 100800, 26 * 3600))

    def test_a_dump_newer_than_the_backup_fails_closed(self):
        self.assertFalse(harness.fresh(1000.0, 1001.0, 1000.0, 100800, 26 * 3600))

    def test_an_unknown_dump_time_fails_closed(self):
        self.assertFalse(harness.fresh(1000.0, None, 1000.0, 100800, 26 * 3600))

    def test_dump_time_comes_from_mtime_or_timestamp(self):
        self.assertEqual(harness.dump_time({'mtime': 12.5}), 12.5)
        self.assertEqual(harness.dump_time({'timestamp': '1970-01-01T00:01:00Z'}), 60.0)
        self.assertIsNone(harness.dump_time({'timestamp': 'yesterday'}))
        self.assertIsNone(harness.dump_time({}))


class Results(unittest.TestCase):
    def result(self, **tiers):
        return {'tiers': tiers, 'fences': {'watch_namespace': True}, 'rows': {'Series': 3},
                'duration': 61.4, 'data_age': 3600.2, 'dump_age': 5400.0, 'bytes': 1024, 'total_rows': 171}

    def test_success_records_its_time(self):
        result = self.result(restored=True, intact=True)
        result['passed'] = harness.passed(result)
        text = harness.metrics(result, 1000.0)
        self.assertIn('restore_test_last_success_timestamp_seconds 1000\n', text)
        self.assertIn('restore_test_dump_age_seconds 5400\n', text)
        self.assertIn('restore_test_rows{table="Series"} 3\n', text)
        self.assertIn('restore_test_total_rows 171\n', text)

    def test_failure_keeps_the_previous_success(self):
        result = self.result(restored=True, intact=False)
        result['passed'] = harness.passed(result)
        self.assertNotIn('last_success', harness.metrics(result, 1000.0))

    def test_nothing_checked_is_not_a_pass(self):
        self.assertFalse(harness.passed({'tiers': {}, 'fences': {}}))

    def test_a_broken_fence_fails_the_target(self):
        result = self.result(restored=True)
        result['fences']['arrchitect_refused'] = False
        self.assertFalse(harness.passed(result))


class Register(unittest.TestCase):
    entries = [{'target': 'jellyfin', 'tier': 'answers', 'reason': 'r', 'expires': '2027-02-27'}]

    def result(self, answers):
        return {'tiers': {'restored': True, 'intact': True, 'usable': True, 'answers': answers},
                'fences': {'watch_namespace': True}, 'rows': {}, 'duration': 1}

    def test_a_listed_failure_does_not_fail_the_target(self):
        result = self.result(False)
        harness.apply_register('jellyfin', result, self.entries, datetime.date(2026, 11, 27))
        self.assertEqual(result['expected'], {'answers': True})
        self.assertTrue(harness.passed(result))
        result['passed'] = True
        text = harness.metrics(result, 1.0)
        self.assertIn('restore_test_expected_failure{tier="answers"} 1\n', text)
        self.assertIn('restore_test_expected_failure_resolved{tier="none"} 0\n', text)

    def test_a_listed_tier_that_passes_is_flagged_for_removal(self):
        result = self.result(True)
        harness.apply_register('jellyfin', result, self.entries, datetime.date(2026, 11, 27))
        result['passed'] = harness.passed(result)
        self.assertIn('restore_test_expected_failure_resolved{tier="answers"} 1\n', harness.metrics(result, 1.0))

    def test_an_expired_entry_fails_again(self):
        result = self.result(False)
        harness.apply_register('jellyfin', result, self.entries, datetime.date(2027, 3, 1))
        self.assertFalse(harness.passed(result))

    def test_an_entry_only_covers_its_own_target(self):
        result = self.result(False)
        harness.apply_register('seerr-not-listed', result, self.entries, datetime.date(2026, 11, 27))
        self.assertFalse(harness.passed(result))

    def test_the_shipped_register_names_real_targets_and_tiers(self):
        register = json.loads((APP / 'scripts/expected_failures.json').read_text())
        for entry in register:
            self.assertIn(entry['target'], TARGETS)
            self.assertIn(entry['tier'], ('restored', 'intact', 'fresh', 'usable', 'answers'))
            self.assertTrue(entry['reason'])
            datetime.date.fromisoformat(entry['expires'])


class Alerts(unittest.TestCase):
    def test_every_target_has_a_missing_result_guard_for_each_source(self):
        rules = yaml.safe_load((APP / 'prometheusrule.yml').read_text())
        exprs = ' '.join(r['expr'] for g in rules['spec']['groups'] for r in g['rules']
                         if r.get('alert') == 'RestoreTestMissing')
        for target in harness.TARGETS:
            for source in ('local', 'offsite'):
                self.assertIn(f'target="{target["name"]}", source="{source}"', exprs, (target['name'], source))


class Schedules(unittest.TestCase):
    def cronjob(self, name):
        return yaml.safe_load((APP / name).read_text())

    def env(self, cronjob):
        container = cronjob['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]
        return {item['name']: item['value'] for item in container['env']}

    def test_the_offsite_run_is_the_nightly_run_pointed_at_the_aws_copy(self):
        nightly, offsite = self.cronjob('cronjob.yml'), self.cronjob('cronjob-offsite.yml')
        self.assertEqual(offsite['spec']['schedule'], '30 5 * * 0')
        self.assertEqual({k: v for k, v in self.env(offsite).items() if self.env(nightly)[k] != v},
                         {'SOURCE': 'offsite', 'SCHEDULE': 'velero-weekly-offsite', 'MAX_BACKUP_AGE_SECONDS': '691200'})
        for cronjob in (nightly, offsite):
            cronjob['metadata']['name'] = cronjob['spec']['schedule'] = None
            cronjob['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['env'] = None
        self.assertEqual(nightly, offsite)


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
    def test_a_leftover_sandbox_fails_the_run_and_is_left_alone(self):
        api = FakeApi(sandbox_exists=True)
        run = harness.Run(api, ENVIRON)
        run.push = lambda *args: None
        self.assertEqual(run.execute(), 1)
        self.assertNotIn(('DELETE', '/api/v1/namespaces/restore-sandbox'), api.calls)
        self.assertEqual(run.results['sonarr']['tiers'], {'restored': False})

    def test_an_error_after_the_integrity_check_fails_the_remaining_tiers(self):
        def check(target, user, backup_started):
            run.results[target['name']]['tiers'].update(intact=True)
            raise RuntimeError('app pod rejected')

        run = harness.Run(FakeApi(sandbox_exists=False), ENVIRON)
        run.push = lambda *args: None
        run.cleanup = lambda: None
        run.latest_finished = lambda: True
        run.create_sandbox = lambda: setattr(run, 'created', True)
        run.fences = lambda: {'watch_namespace': True, 'arrchitect_refused': True}
        run.arrchitect_absent = lambda: True
        run.release_volumes = lambda: 0
        run.restore_started = 0.0
        run.run_restore = lambda: {'spec': {'backupName': 'backup'}, 'status': {'phase': 'Completed'}}
        run.volume_restores = lambda: []
        run.restored_volume = lambda target, pods, restores: ('Completed', 10, (1, 2))
        run.check = check
        run.api.json = lambda method, path, *a, **k: (
            {'status': {'startTimestamp': '2026-11-27T03:00:00Z'}} if '/backups/' in path else {'items': []})
        self.assertEqual(run.execute(), 1)
        sonarr, home = run.results['sonarr']['tiers'], run.results['home-assistant']['tiers']
        self.assertTrue(sonarr['intact'])
        self.assertFalse(sonarr['fresh'])
        self.assertFalse(sonarr['usable'])
        self.assertFalse(sonarr['answers'])
        self.assertNotIn('usable', home)


class RunPod(unittest.TestCase):
    def run_pod(self, keep):
        calls = []

        class Api:
            def json(self, method, path, body=None, *args, **kwargs):
                calls.append((method, path))
                if method == 'POST':
                    return {}
                return {'status': {'phase': 'Running', 'containerStatuses': [
                    {'name': 'check', 'state': {'terminated': {'exitCode': 0}}}]}}

            def call(self, method, path, *args, **kwargs):
                calls.append((method, path))
                return 200, '{"count": 3}\n'

        run = harness.Run(Api(), {**ENVIRON, 'KEEP_SANDBOX': 'true' if keep else 'false'})
        pod = {'metadata': {'name': 'check-sonarr'}}
        return run.run_pod(pod, 'check', 5), calls

    def test_a_finished_pod_is_deleted_so_tests_do_not_stack_up(self):
        result, calls = self.run_pod(keep=False)
        self.assertEqual(result, (True, {'count': 3}))
        self.assertIn(('DELETE', '/api/v1/namespaces/restore-sandbox/pods/check-sonarr'), calls)

    def test_a_kept_sandbox_keeps_its_pods(self):
        result, calls = self.run_pod(keep=True)
        self.assertNotIn('DELETE', [method for method, _ in calls])


class AppCheck(unittest.TestCase):
    def run_check(self, name, app_report):
        workload = {'spec': {'template': {'spec': {'containers': [{'image': 'app:1', 'env': []}]}}}}
        reports = iter([(True, {'integrity': 'ok', 'rows': {}, 'total_rows': 5, 'mtime': 1000.0}),
                        (True, app_report)])

        class Api:
            def json(self, method, path, *args, **kwargs):
                return workload

        run = harness.Run(Api(), ENVIRON)
        run.check_image = lambda target: 'python:3.15-alpine'
        run.run_pod = lambda pod, container, timeout: next(reports)
        run.check(TARGETS[name], (1000, 1000), 1000.0 + 3600)
        return run.results[name]['tiers']

    def test_an_app_without_a_data_probe_records_only_that_it_started(self):
        tiers = self.run_check('uptime-kuma', {'started': True})
        self.assertEqual(tiers['usable'], True)
        self.assertNotIn('answers', tiers)

    def test_a_field_probe_that_misses_fails_the_answers_tier(self):
        tiers = self.run_check('seerr', {'started': True, 'value': False, 'matches': False})
        self.assertEqual((tiers['usable'], tiers['answers']), (True, False))


class ArrchitectAbsent(unittest.TestCase):
    def run_with(self, listings):
        class Api:
            def json(self, method, path, *args, **kwargs):
                return {'resources': [{'name': 'sonarrs'}, {'name': 'sonarrs/status'}, {'name': 'lidarrs'}]}

            def call(self, method, path, *args, **kwargs):
                return listings[path.rsplit('/', 1)[-1]]

        return harness.Run(Api(), ENVIRON).arrchitect_absent()

    def test_an_empty_sandbox_passes_and_kinds_without_a_controller_are_skipped(self):
        self.assertTrue(self.run_with({'sonarrs': (200, '{"items": []}'), 'lidarrs': (403, '')}))

    def test_a_restored_resource_fails(self):
        self.assertFalse(self.run_with({'sonarrs': (200, '{"items": [{}]}'), 'lidarrs': (403, '')}))

    def test_an_unreadable_listing_fails(self):
        self.assertFalse(self.run_with({'sonarrs': (500, ''), 'lidarrs': (403, '')}))


class ReleaseVolumes(unittest.TestCase):
    def test_only_the_sandbox_volumes_are_set_to_be_deleted(self):
        volume = lambda name, sc, ns, policy: {'metadata': {'name': name}, 'spec': {
            'storageClassName': sc, 'claimRef': {'namespace': ns}, 'persistentVolumeReclaimPolicy': policy}}
        patched = []

        class Api:
            def json(self, method, path, body=None, *args, **kwargs):
                if method == 'PATCH':
                    patched.append((path.rsplit('/', 1)[-1], body))
                    return {}
                return {'items': [
                    volume('copied-retain', 'nfs-restore-test', 'restore-sandbox', 'Retain'),
                    volume('already-delete', 'nfs-restore-test', 'restore-sandbox', 'Delete'),
                    volume('production', 'nfs-client', 'media', 'Retain'),
                    volume('other-namespace', 'nfs-restore-test', 'media', 'Retain'),
                ]}

        self.assertEqual(harness.Run(Api(), ENVIRON).release_volumes(), 1)
        self.assertEqual(patched, [('copied-retain', {'spec': {'persistentVolumeReclaimPolicy': 'Delete'}})])


class Api(unittest.TestCase):
    def serve(self, count_delay=0.0, count_status=200):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('X-Api-Key') != 'key':
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path == '/status':
                    body, status = {'version': '2.7.0'}, 200
                else:
                    time.sleep(count_delay)
                    body, status = [{}, {}, {}], count_status
                data = json.dumps(body).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(data)
                except BrokenPipeError:
                    pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                data = json.dumps([request] * 2).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def spec(self, port, probe=None):
        return {'port': port, 'status': '/status', 'probe': probe or {'path': '/items', 'count_table': 'T'}}

    def test_a_running_app_reports_its_version_and_count(self):
        port = self.serve()
        self.assertEqual(check_api.check(self.spec(port), 'key', 5, interval=0.1),
                         ({'started': True, 'version': '2.7.0', 'count': 3}, True))

    def test_a_probe_with_a_body_is_posted_as_json(self):
        port = self.serve()
        probe = {'path': '/api/v2/cruddb', 'count_table': 'T', 'body': {'data': {'mode': 'getAll'}}}
        self.assertEqual(check_api.get(f'http://127.0.0.1:{port}', probe['path'], 'key', 5, probe['body']),
                         [probe['body']] * 2)
        self.assertEqual(check_api.check(self.spec(port, probe), 'key', 5, interval=0.1)[0]['count'], 2)

    def test_a_field_probe_reports_whether_the_value_matches(self):
        port = self.serve()
        report, passed = check_api.check(self.spec(port, {'path': '/status', 'field': 'version', 'equals': '2.7.0'}),
                                         'key', 5, interval=0.1)
        self.assertTrue(passed)
        self.assertEqual((report['value'], report['matches']), ('2.7.0', True))

    def test_an_app_without_a_data_probe_passes_once_it_answers(self):
        port = self.serve()
        self.assertEqual(check_api.check(self.spec(port, None) | {'probe': None}, 'key', 5, interval=0.1),
                         ({'started': True, 'version': '2.7.0'}, True))

    def test_a_probe_without_a_path_is_unresolved(self):
        port = self.serve()
        report, passed = check_api.check(self.spec(port, {'path': None, 'field': 'x', 'equals': 1}), 'key', 5, interval=0.1)
        self.assertEqual((report['probe_error'], passed), ('unresolved', False))

    def test_a_count_that_never_answers_is_reported_not_raised(self):
        port = self.serve(count_status=500)
        report, passed = check_api.check(self.spec(port), 'key', 1, interval=0.1, request_timeout=1)
        self.assertFalse(passed)
        self.assertEqual(report['probe_error'], 'HTTPError')

    def test_a_slow_count_times_out_cleanly(self):
        port = self.serve(count_delay=2)
        report, passed = check_api.check(self.spec(port), 'key', 1, interval=0.1, request_timeout=0.5)
        self.assertFalse(passed)
        self.assertTrue(report['started'])
        self.assertIn('probe_error', report)

    def test_an_app_that_never_starts_fails(self):
        port = self.serve()
        report, passed = check_api.check(self.spec(port), 'wrong', 0.3, interval=0.1, request_timeout=1)
        self.assertEqual(report, {'started': False, 'error': 'HTTPError'})

    def test_counts_and_fields_read_the_shapes_apps_return(self):
        self.assertEqual(check_api.count([1, 2]), 2)
        self.assertEqual(check_api.count({'data': [1], 'total': 7}), 7)
        self.assertEqual(check_api.count({'data': [1, 2, 3]}), 3)
        self.assertEqual(check_api.field({'config': {'slug': 'home'}}, 'config.slug'), 'home')
        self.assertEqual(check_api.version({'data': {'bazarr_version': '1.6.2'}}), '1.6.2')
        self.assertEqual(check_api.version({'Version': '10.11.11'}), '10.11.11')


class Scratch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def database(self, path, statements):
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(statements)
        return path


class Sqlite(Scratch):
    def setUp(self):
        super().setUp()
        self.path = self.database(self.root / 'app.db', '''
            CREATE TABLE "Series" (Id INTEGER PRIMARY KEY);
            CREATE TABLE "Episodes" (Id INTEGER PRIMARY KEY, SeriesId INTEGER REFERENCES "Series"(Id));
            INSERT INTO "Series" VALUES (1), (2); INSERT INTO "Episodes" VALUES (1, 1);''')

    def test_named_queries_return_their_first_value(self):
        report, passed = check_sqlite.check(self.path, [], [], False, {'first': 'SELECT MIN(Id) FROM "Series"',
                                                                        'none': 'SELECT Id FROM "Series" WHERE 0'})
        self.assertTrue(passed)
        self.assertEqual(report['values'], {'first': 1, 'none': None})

    def test_a_sound_database_passes_with_its_counts_and_time(self):
        report, passed = check_sqlite.check(self.path, ['Series'], ['Episodes', 'Absent'], True)
        self.assertTrue(passed)
        self.assertEqual(report['rows'], {'Series': 2, 'Episodes': 1})
        self.assertEqual(report['total_rows'], 3)
        self.assertAlmostEqual(report['mtime'], self.path.stat().st_mtime)

    def test_an_empty_required_table_fails(self):
        self.database(self.path, 'DELETE FROM "Episodes"; DELETE FROM "Series";')
        self.assertFalse(check_sqlite.check(self.path, ['Series'], [], False)[1])

    def test_a_missing_required_table_fails(self):
        report, passed = check_sqlite.check(self.path, ['History'], [], False)
        self.assertFalse(passed)
        self.assertEqual(report['missing_tables'], ['History'])

    def test_foreign_key_violations_fail_only_when_strict(self):
        self.database(self.path, 'INSERT INTO "Episodes" VALUES (2, 99);')
        self.assertTrue(check_sqlite.check(self.path, [], [], False)[1])
        report, passed = check_sqlite.check(self.path, [], [], True)
        self.assertFalse(passed)
        self.assertEqual(report['foreign_key_violations'], 1)

    def test_an_empty_database_fails(self):
        empty = self.database(self.root / 'empty.db', 'CREATE TABLE t (x INTEGER);')
        self.assertFalse(check_sqlite.check(empty, [], [], False)[1])

    def test_a_file_that_is_not_a_database_fails(self):
        self.path.write_bytes(b'not a database' * 100)
        self.assertEqual(check_sqlite.check(self.path, ['Series'], [], False), ({'error': 'DatabaseError'}, False))


class Zip(Scratch):
    def archive(self, inner_bytes, name='DB2/SQL/database.db'):
        path = self.root / 'latest.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(name, inner_bytes)
            archive.writestr('Plugins/x.js', 'plugin')
        return path

    def test_a_sound_archive_with_its_database_passes(self):
        database = self.database(self.root / 'inner.db', 'CREATE TABLE t (x INTEGER); INSERT INTO t VALUES (1);')
        report, passed = check_zip.check(self.archive(database.read_bytes()), 'DB2/SQL/database.db', self.temporary.name)
        self.assertTrue(passed)
        self.assertEqual(report['entries'], 2)

    def test_the_archived_database_reports_the_requested_tables(self):
        database = self.database(self.root / 'inner.db', 'CREATE TABLE t (x INTEGER); INSERT INTO t VALUES (1), (2);')
        report, passed = check_zip.check(self.archive(database.read_bytes()), 'DB2/SQL/database.db',
                                         self.temporary.name, ['t'])
        self.assertTrue(passed)
        self.assertEqual(report['rows'], {'t': 2})

    def test_an_archive_without_its_database_fails(self):
        report, passed = check_zip.check(self.archive(b'x', name='other'), 'DB2/SQL/database.db', self.temporary.name)
        self.assertFalse(passed)
        self.assertTrue(report['inner_missing'])

    def test_a_corrupt_archive_fails(self):
        path = self.root / 'latest.zip'
        path.write_bytes(b'PK not really a zip')
        self.assertFalse(check_zip.check(path, 'x', self.temporary.name)[1])


class HomeAssistant(Scratch):
    def backup(self, name, metadata, payload=True):
        with tarfile.open(self.root / name, 'w') as archive:
            data = json.dumps(metadata).encode()
            info = tarfile.TarInfo('./backup.json')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
            if payload:
                info = tarfile.TarInfo('./homeassistant.tar.gz')
                info.size = 4
                archive.addfile(info, io.BytesIO(b'data'))

    def test_the_newest_protected_backup_passes_with_its_date(self):
        self.backup('old.tar', {'date': '2026-11-25T04:45:00+00:00', 'protected': False})
        time.sleep(0.01)
        self.backup('new.tar', {'date': '2026-11-27T04:45:00+00:00', 'protected': True})
        report, passed = check_ha.check(self.root)
        self.assertTrue(passed)
        self.assertEqual(report['timestamp'], '2026-11-27T04:45:00+00:00')
        self.assertEqual(report['archives'], 2)

    def test_an_unencrypted_backup_fails(self):
        self.backup('new.tar', {'date': '2026-11-27T04:45:00+00:00', 'protected': False})
        self.assertFalse(check_ha.check(self.root)[1])

    def test_a_backup_without_its_archive_fails(self):
        self.backup('new.tar', {'date': '2026-11-27T04:45:00+00:00', 'protected': True}, payload=False)
        self.assertFalse(check_ha.check(self.root)[1])

    def test_no_backups_fails(self):
        self.assertEqual(check_ha.check(self.root), ({'archives': 0}, False))


if __name__ == '__main__':
    unittest.main()
