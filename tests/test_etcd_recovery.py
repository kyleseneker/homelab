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
