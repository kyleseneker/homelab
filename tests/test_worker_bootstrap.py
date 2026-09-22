"""Exercise worker-only joins and token cleanup without a real cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('ansible-playbook'), 'requires ansible-core')
class WorkerBootstrap(unittest.TestCase):
    def exercise(self, fail_join=False):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'bin'
            binary.mkdir()
            fake = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['BOOTSTRAP_TEST_LOG'], 'a') as output:
    output.write(json.dumps([Path(sys.argv[0]).name] + args) + '\\n')
if args[:2] == ['token', 'create']:
    print('kubeadm join 127.0.0.1:6443 --token abcdef.0123456789abcdef --discovery-token-ca-cert-hash sha256:fixture')
elif args[:1] == ['join']:
    sys.exit(int(os.environ['BOOTSTRAP_TEST_FAIL']))
elif Path(sys.argv[0]).name == 'kubectl':
    print('True')
'''
            for name in ('kubeadm', 'kubectl'):
                script = binary / name
                script.write_text(fake)
                script.chmod(0o700)
            (root / 'inventory').write_text('[control_plane]\nfixture-control ansible_connection=local\n[workers]\nfixture-worker ansible_connection=local\n')
            # Replace only the filesystem probe, so developer machines with a
            # kubelet.conf do not skip the join. Execute the actual role block.
            import yaml
            tasks = yaml.safe_load((repo / 'ansible/roles/k8s_worker/tasks/main.yml').read_text())
            tasks[0] = {'ansible.builtin.set_fact': {'k8s_worker_kubelet_conf': {'stat': {'exists': False}}}}
            play = [{'hosts': 'workers', 'gather_facts': False, 'become': False, 'tasks': tasks}]
            (root / 'play.yml').write_text(yaml.safe_dump(play))
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       BOOTSTRAP_TEST_LOG=str(root / 'calls.jsonl'), BOOTSTRAP_TEST_FAIL=str(int(fail_join)),
                       ANSIBLE_CONFIG=str(root / 'ansible.cfg'), ANSIBLE_LOCAL_TEMP=str(root / 'local'),
                       ANSIBLE_REMOTE_TEMP=str(root / 'remote'))
            (root / 'ansible.cfg').write_text('[defaults]\ninterpreter_python=auto_silent\n')
            result = subprocess.run(['ansible-playbook', '-i', str(root / 'inventory'), str(root / 'play.yml'), '--limit', 'fixture-worker'],
                                    env=env, capture_output=True, text=True, timeout=90)
            calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
            self.assertEqual(result.returncode == 0, not fail_join, result.stdout + result.stderr)
            self.assertIn(['kubeadm', 'token', 'create', '--ttl', '15m', '--print-join-command'], calls)
            self.assertIn(['kubeadm', 'token', 'delete', 'abcdef.0123456789abcdef'], calls)
            self.assertNotIn('abcdef.0123456789abcdef', result.stdout + result.stderr)

    def test_worker_only_join_revokes_token(self):
        self.exercise()

    def test_failed_join_still_revokes_token(self):
        self.exercise(fail_join=True)
