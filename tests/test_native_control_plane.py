"""Containment regression checks for the disposable native boot drill."""
import copy
import importlib.util
from pathlib import Path
import unittest
import tempfile

PATH = Path(__file__).parents[1] / 'scripts/verify-native-control-plane.py'
spec = importlib.util.spec_from_file_location('native_recovery', PATH)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeRecovery(unittest.TestCase):
    def test_standalone_config_preserves_source_and_disables_api_dependencies(self):
        source = {'staticPodPath': '/etc/kubernetes/manifests', 'cgroupDriver': 'systemd',
                  'rotateCertificates': True, 'serverTLSBootstrap': True,
                  'authentication': {'webhook': {'enabled': True}},
                  'authorization': {'mode': 'Webhook'}}
        original = copy.deepcopy(source)
        result = native.standalone(source)
        self.assertEqual(source, original)
        self.assertFalse(result['enableServer'])
        self.assertFalse(result['authentication']['webhook']['enabled'])
        self.assertFalse(result['rotateCertificates'])
        self.assertFalse(result['serverTLSBootstrap'])
        self.assertEqual(result['cgroupDriver'], 'systemd')

    def test_changed_static_pod_directory_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'static Pod directory'):
            native.standalone({'staticPodPath': '/unreviewed/pods'})

    def test_fresh_package_marker_is_allowed_but_pods_are_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.kubelet-keep').touch()
            self.assertTrue(native.empty_manifests(root))
            (root / 'etcd.yaml').write_text('existing pod')
            self.assertFalse(native.empty_manifests(root))

    def test_package_marker_cannot_hide_data_or_a_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / '.kubelet-keep'
            marker.write_text('unexpected')
            self.assertFalse(native.empty_manifests(root))
            marker.unlink()
            marker.symlink_to('/dev/null')
            self.assertFalse(native.empty_manifests(root))
