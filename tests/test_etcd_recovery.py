import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('etcd_recovery', Path(__file__).parents[1] / 'scripts/verify-etcd-recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryGuards(unittest.TestCase):
    def test_rejects_production_host_before_creating_work(self):
        with tempfile.TemporaryDirectory() as root:
            work = Path(root) / 'new'
            with patch.object(recovery.os, 'geteuid', return_value=0), patch.object(recovery.socket, 'gethostname', return_value='homelabk8s01-node-1'):
                with self.assertRaisesRegex(RuntimeError, 'only as root'):
                    recovery.main(Path(root), work)
            self.assertFalse(work.exists())

    def test_rejects_existing_work_before_extracting(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(recovery.os, 'geteuid', return_value=0), patch.object(recovery.socket, 'gethostname', return_value='homelabrestore01-node-1'):
                with self.assertRaisesRegex(RuntimeError, 'Existing drill'):
                    recovery.main(Path(root), Path(root))

    def test_rejects_archive_escape_and_links(self):
        for name, kind in [('pki/../../etc/shadow', tarfile.REGTYPE), ('/pki/key', tarfile.REGTYPE),
                           ('other/key', tarfile.REGTYPE), ('pki/link', tarfile.SYMTYPE), ('pki/link', tarfile.LNKTYPE)]:
            member = tarfile.TarInfo(name)
            member.type = kind
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                recovery.validate_archive([member])

    def test_accepts_only_expected_pki_paths(self):
        directory = tarfile.TarInfo('pki/etcd')
        directory.type = tarfile.DIRTYPE
        recovery.validate_archive([directory, tarfile.TarInfo('pki/etcd/server.key')])

    def test_requires_unambiguous_original_identity(self):
        for command in [[], ['--name=one', '--name=two']]:
            with self.assertRaises(ValueError):
                recovery.flag(command, '--name')
        self.assertEqual(recovery.flag(['etcd', '--name=original'], '--name'), 'original')


controller_spec = importlib.util.spec_from_file_location('recovery_controllers', Path(__file__).parents[1] / 'scripts/recovery_controllers.py')
controllers = importlib.util.module_from_spec(controller_spec)
controller_spec.loader.exec_module(controllers)


class ControllerGuards(unittest.TestCase):
    def test_low_memory_refuses_before_credentials_or_processes(self):
        def unexpected(*args, **kwargs):
            self.fail('No operation may run without memory headroom')
        with patch.object(Path, 'read_text', return_value='MemAvailable: 1024 kB\n'):
            with self.assertRaisesRegex(RuntimeError, 'headroom'):
                controllers.verify(Path('/unused'), Path('/unused'), '192.168.10.50',
                                   unexpected, unexpected, unexpected, unexpected)

    def test_changed_controller_version_requires_revalidation(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)
            (source / 'kube-scheduler-source.json').write_text('{"image":"registry.k8s.io/kube-scheduler:v1.32.0","command":["kube-scheduler"]}')
            with self.assertRaisesRegex(RuntimeError, 'Revalidate'):
                controllers.controller_source(source, 'kube-scheduler')


runtime_spec = importlib.util.spec_from_file_location('recovery_runtime', Path(__file__).parents[1] / 'scripts/recovery_runtime.py')
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


class RuntimeGuards(unittest.TestCase):
    @staticmethod
    def versions(args, **kwargs):
        from types import SimpleNamespace
        values = {'kubelet': b'Kubernetes v1.31.4\n', 'containerd': b'containerd github.com/containerd/containerd/v2 v2.3.5\n'}
        if len(args) != 2 or args[1] != '--version':
            raise AssertionError('Unexpected runtime operation before preflight succeeds')
        return SimpleNamespace(stdout=values[args[0]])

    def test_changed_kubelet_refuses_before_stopping_controllers(self):
        from types import SimpleNamespace
        def unexpected(*args, **kwargs):
            self.fail('No mutable operation allowed with an unvalidated kubelet')
        with self.assertRaisesRegex(RuntimeError, 'changed kubelet'):
            runtime.verify(Path('/unused'), lambda args: SimpleNamespace(stdout=b'Kubernetes v1.32.0\n'),
                           unexpected, unexpected)

    def test_low_memory_refuses_before_host_mutation(self):
        stopped = []
        with patch.object(Path, 'read_text', return_value='MemAvailable: 1024 kB\n'):
            with self.assertRaisesRegex(RuntimeError, 'headroom'):
                runtime.verify(Path('/unused'), self.versions, lambda *a, **k: self.fail('Unexpected API write'), stopped.append)
        self.assertEqual(stopped, ['etcd-recovery-kube-scheduler', 'etcd-recovery-kube-controller-manager'])

    def test_existing_pod_cgroup_is_never_reused(self):
        with patch.object(Path, 'read_text', return_value='MemAvailable: 1048576 kB\n'), patch.object(Path, 'exists', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'new dedicated pod cgroup'):
                runtime.verify(Path('/unused'), self.versions, lambda *a, **k: self.fail('Unexpected API write'), lambda name: None)


class RuntimeSocketIsolation(unittest.TestCase):
    def config(self, root):
        return {'root': str(root / 'data'), 'state': str(root / 'state'), 'imports': [], 'plugins': {
            'io.containerd.server.v1.grpc': {'address': str(root / 'containerd.sock')},
            'io.containerd.server.v1.ttrpc': {'address': str(root / 'containerd.ttrpc')},
            'io.containerd.server.v1.grpc-tcp': {'address': ''},
            'io.containerd.server.v1.debug': {'address': ''},
            'io.containerd.server.v1.metrics': {'address': ''},
            'io.containerd.shim.v1.manager': {'socket_dir': str(root / 'shim-sockets')}}}

    def test_ignored_legacy_grpc_setting_cannot_touch_host_socket(self):
        root = Path('/private/recovery')
        config = self.config(root)
        config['grpc'] = {'address': str(root / 'containerd.sock')}
        config['plugins']['io.containerd.server.v1.grpc']['address'] = '/run/containerd/containerd.sock'
        with self.assertRaisesRegex(RuntimeError, 'socket is not isolated'):
            runtime.validate_runtime_config(config, root)

    def test_ttrpc_socket_is_isolated_too(self):
        root = Path('/private/recovery')
        config = self.config(root)
        config['plugins']['io.containerd.server.v1.ttrpc']['address'] = '/run/containerd/containerd.sock.ttrpc'
        with self.assertRaisesRegex(RuntimeError, 'socket is not isolated'):
            runtime.validate_runtime_config(config, root)

    def test_host_config_imports_are_rejected(self):
        root = Path('/private/recovery')
        config = self.config(root)
        config['imports'] = ['/etc/containerd/conf.d/*.toml']
        with self.assertRaisesRegex(RuntimeError, 'roots/imports'):
            runtime.validate_runtime_config(config, root)

    def test_accepts_effective_private_endpoints(self):
        root = Path('/private/recovery')
        runtime.validate_runtime_config(self.config(root), root)

    def test_masked_defaults_require_explicit_namespace_context(self):
        root = Path('/private/recovery')
        config = self.config(root)
        config['imports'] = ['/etc/containerd/conf.d/*.toml', str(root / 'conf.d/*.toml')]
        config['plugins']['io.containerd.shim.v1.manager']['socket_dir'] = '/run/containerd/s'
        with self.assertRaisesRegex(RuntimeError, 'roots/imports'):
            runtime.validate_runtime_config(config, root)
        runtime.validate_runtime_config(config, root, host_config_masked=True)

    def test_masking_known_directories_does_not_allow_other_imports(self):
        root = Path('/private/recovery')
        config = self.config(root)
        config['imports'] = ['/etc/other-runtime/*.toml']
        with self.assertRaisesRegex(RuntimeError, 'roots/imports'):
            runtime.validate_runtime_config(config, root, host_config_masked=True)


class RepositoryPasswordExport(unittest.TestCase):
    def secret(self):
        import base64
        return {'kind': 'Secret', 'metadata': {'namespace': 'backups', 'name': 'velero-repo-credentials'},
                'data': {'repository-password': base64.b64encode(b'test-only-password').decode()}}

    def test_export_is_private_and_never_overwrites(self):
        import stat
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'password'
            recovery.export_kopia_password(self.secret(), target)
            self.assertEqual(target.read_bytes(), b'test-only-password')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                recovery.export_kopia_password(self.secret(), target)

    def test_wrong_secret_is_rejected_before_writing(self):
        secret = self.secret()
        secret['metadata']['name'] = 'unrelated'
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'password'
            with self.assertRaises(ValueError):
                recovery.export_kopia_password(secret, target)
            self.assertFalse(target.exists())
