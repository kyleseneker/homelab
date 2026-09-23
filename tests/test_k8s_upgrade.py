"""Exercise upgrade safety checks before package or cluster mutations."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


@unittest.skipUnless(shutil.which("ansible-playbook"), "requires ansible-core")
class UpgradeBoundaryTests(unittest.TestCase):
    def exercise(
        self,
        target="1.32.13",
        node="1.31.4",
        api="1.31.4",
        worker=False,
        backup=True,
        bootstrap=False,
    ):
        root = Path(__file__).resolve().parents[1]
        tasks = yaml.safe_load(
            (root / "ansible/roles/k8s_upgrade/tasks/main.yml").read_text()
        )
        guard = next(
            i
            for i, t in enumerate(tasks)
            if t["name"] == "Reject skipped minors and downgrades"
        )
        tasks = tasks[: guard + 1]
        if bootstrap:
            tasks = [
                t
                for t in yaml.safe_load(
                    (root / "ansible/roles/k8s_prereqs/tasks/main.yml").read_text()
                )
                if t["name"]
                == "Require the upgrade playbook for an initialized node's version change"
            ]
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            hostname = "fixture-worker" if worker else "fixture-control"
            binary = p / "kubectl"
            binary.write_text(
                "#!/usr/bin/env python3\nimport json,sys\n"
                + "print(json.dumps("
                + repr(
                    {
                        "serverVersion": {
                            "gitVersion": "v" + api,
                            "minor": api.split(".")[1],
                        }
                    }
                )
                + ' if "version" in sys.argv else '
                + repr(
                    {
                        "items": [
                            {
                                "metadata": {"name": hostname},
                                "status": {"nodeInfo": {"kubeletVersion": "v" + node}},
                            }
                        ]
                    }
                )
                + "))\n"
            )
            binary.chmod(0o700)
            (p / "inventory").write_text(
                "[control_plane]\nfixture-control ansible_connection=local\n[workers]\nfixture-worker ansible_connection=local\n"
            )
            (p / "play.yml").write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": hostname,
                            "gather_facts": False,
                            "become": False,
                            "vars": {
                                "k8s_upgrade_version": target,
                                "k8s_upgrade_backup_verified": backup,
                                "k8s_prereqs_kubelet_identity": {
                                    "stat": {"exists": True}
                                },
                                "k8s_prereqs_existing_version": {
                                    "stdout": "Kubernetes v" + node
                                },
                                "k8s_prereqs_version": target,
                            },
                            "tasks": tasks,
                        }
                    ]
                )
            )
            (p / "ansible.cfg").write_text(
                "[defaults]\ninterpreter_python=auto_silent\n"
            )
            env = dict(
                os.environ,
                PATH=str(p) + os.pathsep + os.environ["PATH"],
                ANSIBLE_CONFIG=str(p / "ansible.cfg"),
                ANSIBLE_LOCAL_TEMP=str(p / "local"),
                ANSIBLE_REMOTE_TEMP=str(p / "remote"),
            )
            result = subprocess.run(
                ["ansible-playbook", "-i", str(p / "inventory"), str(p / "play.yml")],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode, result.stdout + result.stderr

    def test_readiness_retries_an_unavailable_api(self):
        root = Path(__file__).resolve().parents[1]
        tasks = yaml.safe_load(
            (root / "ansible/roles/k8s_upgrade/tasks/main.yml").read_text()
        )
        task = next(
            t
            for t in tasks
            if t["name"]
            == "Wait for this node to report the target version and readiness"
        )
        task["delay"] = 0
        task["retries"] = 2
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            binary = p / "kubectl"
            binary.write_text(
                "#!/usr/bin/env python3\nfrom pathlib import Path\nimport json,sys\np=Path("
                + repr(str(p / "attempts"))
                + ')\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\nif n==0:sys.exit(1)\nprint(json.dumps({"status":{"nodeInfo":{"kubeletVersion":"v1.32.13"},"conditions":[{"type":"Ready","status":"True"}]}}))\n'
            )
            binary.chmod(0o700)
            (p / "inventory").write_text(
                "[control_plane]\nfixture-control ansible_connection=local\n"
            )
            (p / "play.yml").write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "control_plane",
                            "gather_facts": False,
                            "become": False,
                            "vars": {"k8s_upgrade_version": "1.32.13"},
                            "tasks": [task],
                        }
                    ]
                )
            )
            (p / "ansible.cfg").write_text(
                "[defaults]\ninterpreter_python=auto_silent\n"
            )
            env = dict(
                os.environ,
                PATH=str(p) + os.pathsep + os.environ["PATH"],
                ANSIBLE_CONFIG=str(p / "ansible.cfg"),
                ANSIBLE_LOCAL_TEMP=str(p / "local"),
                ANSIBLE_REMOTE_TEMP=str(p / "remote"),
            )
            result = subprocess.run(
                ["ansible-playbook", "-i", str(p / "inventory"), str(p / "play.yml")],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((p / "attempts").read_text(), "2")

    def test_bootstrap_refuses_initialized_node_version_change(self):
        self.assertNotEqual(self.exercise(bootstrap=True)[0], 0)

    def test_bootstrap_accepts_initialized_node_current_version(self):
        code, output = self.exercise(bootstrap=True, target="1.31.4")
        self.assertEqual(code, 0, output)

    def test_next_minor_allowed(self):
        code, output = self.exercise()
        self.assertEqual(code, 0, output)

    def test_skipped_minor_rejected(self):
        self.assertNotEqual(self.exercise(target="1.33.13")[0], 0)

    def test_downgrade_rejected(self):
        self.assertNotEqual(self.exercise(target="1.30.14")[0], 0)

    def test_worker_cannot_precede_api_upgrade(self):
        self.assertNotEqual(self.exercise(worker=True)[0], 0)

    def test_worker_after_api_upgrade_allowed(self):
        code, output = self.exercise(worker=True, api="1.32.13")
        self.assertEqual(code, 0, output)

    def test_unverified_backup_rejected(self):
        self.assertNotEqual(self.exercise(backup=False)[0], 0)


if __name__ == "__main__":
    unittest.main()
