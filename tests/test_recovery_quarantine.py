import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / 'scripts/quarantine-recovered-workloads.py'
spec = importlib.util.spec_from_file_location('quarantine', PATH)
quarantine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quarantine)


class RecoveryQuarantine(unittest.TestCase):
    def test_execution_and_stale_cilium_keys_are_selected(self):
        cases = {
            '/registry/pods/arr/sonarr': '/registry/pods/',
            '/registry/cronjobs/backups/etcd-backup': '/registry/cronjobs/',
            '/registry/minions/old-node': '/registry/minions/',
            '/registry/admissionregistration.k8s.io/validatingwebhookconfigurations/policy':
                '/registry/admissionregistration.k8s.io/validatingwebhookconfigurations/',
            '/registry/cilium.io/ciliumnodes/old-node': '/registry/cilium.io/ciliumnodes/',
        }
        for key, expected in cases.items():
            self.assertEqual(quarantine.removal_prefix(key), expected)

    def test_names_do_not_select_credentials_or_unrelated_configuration(self):
        for key in ['/registry/secrets/pods/client', '/registry/configmaps/deployments/settings',
                    '/registry/clusterroles/controllers', '/registry/cilium.io/ciliumnodeconfigs/settings',
                    '/registry/custom.example/pods/record', '/registry/services/specs/default/kubernetes']:
            self.assertIsNone(quarantine.removal_prefix(key), key)
