"""Exercise containerd pinning and upgrade guards before package mutations."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def tasks_through(role, last):
    tasks = yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/main.yml").read_text())
    end = next(i for i, t in enumerate(tasks) if t["name"] == last)
    return tasks[: end + 1]


def run(tasks, variables, installed="2.2.2-1~ubuntu.24.04~noble", stubs=None, directory=None):
    with tempfile.TemporaryDirectory() as scratch:
        p = Path(directory or scratch)
        binaries = {"dpkg-query": "#!/bin/sh\nprintf '%s' " + repr(installed) + "\n", **(stubs or {})}
        for name, body in binaries.items():
            (p / name).write_text(body)
            (p / name).chmod(0o700)
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
                        "vars": variables,
                        "tasks": tasks,
                    }
                ]
            )
        )
        (p / "ansible.cfg").write_text("[defaults]\ninterpreter_python=auto_silent\n")
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


class GuardAssertions(unittest.TestCase):
    def assertRejected(self, result, message):
        code, output = result
        self.assertNotEqual(code, 0, output)
        self.assertIn(message, output)


@unittest.skipUnless(shutil.which("ansible-playbook"), "requires ansible-core")
class ContainerdUpgradeBoundaryTests(GuardAssertions):
    def exercise(self, target, installed="2.2.2-1~ubuntu.24.04~noble"):
        tasks = tasks_through("containerd_upgrade", "Reject skipped minors and downgrades")
        return run(tasks, {"containerd_upgrade_version": target}, installed)

    def test_patch_upgrade_allowed(self):
        code, output = self.exercise("2.2.6")
        self.assertEqual(code, 0, output)

    def test_next_minor_allowed(self):
        code, output = self.exercise("2.3.6")
        self.assertEqual(code, 0, output)

    def test_current_version_allowed(self):
        code, output = self.exercise("2.2.2")
        self.assertEqual(code, 0, output)

    def test_skipped_minor_rejected(self):
        self.assertRejected(self.exercise("2.4.2"), "one minor at a time")

    def test_downgrade_rejected(self):
        self.assertRejected(self.exercise("2.2.6", installed="2.3.6-1~ubuntu.24.04~noble"), "one minor at a time")

    def test_major_change_rejected(self):
        self.assertRejected(self.exercise("3.0.0", installed="2.3.6-1~ubuntu.24.04~noble"), "one minor at a time")

    def test_missing_target_rejected(self):
        self.assertRejected(self.exercise(""), "Choose an exact target")


@unittest.skipUnless(shutil.which("ansible-playbook"), "requires ansible-core")
class ContainerdBootstrapGuardTests(GuardAssertions):
    def exercise(self, pin, installed):
        tasks = [
            t
            for t in yaml.safe_load((ROOT / "ansible/roles/k8s_prereqs/tasks/main.yml").read_text())
            if t["name"]
            == "Require the containerd upgrade playbook for an initialized node's runtime change"
        ]
        return run(
            tasks,
            {
                "k8s_prereqs_containerd_version": pin,
                "k8s_prereqs_kubelet_identity": {"stat": {"exists": True}},
                "k8s_prereqs_existing_containerd": {"stdout": installed},
            },
        )

    def test_initialized_node_at_pin_allowed(self):
        code, output = self.exercise("2.3.6", "2.3.6-1~ubuntu.24.04~noble")
        self.assertEqual(code, 0, output)

    def test_initialized_node_runtime_change_refused(self):
        self.assertRejected(self.exercise("2.3.6", "2.2.2-1~ubuntu.24.04~noble"), "containerd-upgrade.yml")

    def test_version_prefix_is_not_a_match(self):
        self.assertRejected(self.exercise("2.3.6", "2.3.60-1~ubuntu.24.04~noble"), "containerd-upgrade.yml")


KUBEADM_IMAGES = """#!/bin/sh
printf '%s\\n' registry.k8s.io/kube-apiserver:v1.35.10 registry.k8s.io/coredns/coredns:v1.13.1 registry.k8s.io/pause:3.10.1 registry.k8s.io/etcd:3.6.6-0
"""


@unittest.skipUnless(shutil.which("ansible-playbook"), "requires ansible-core")
class ContainerdSandboxTests(unittest.TestCase):
    def test_sandbox_follows_kubeadm_pause_image(self):
        names = (
            "Read kubeadm's images for the pinned Kubernetes version",
            "Use kubeadm's pause image as the containerd sandbox",
        )
        tasks = [
            t
            for t in yaml.safe_load((ROOT / "ansible/roles/k8s_prereqs/tasks/main.yml").read_text())
            if t["name"] in names
        ]
        self.assertEqual(len(tasks), 2)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                "    [plugins.'io.containerd.cri.v1.images'.pinned_images]\n"
                "      sandbox = 'registry.k8s.io/pause:3.10.2'\n"
                "\n"
                "            sandboxer = 'podsandbox'\n"
            )
            tasks[1]["ansible.builtin.lineinfile"]["path"] = str(config)
            tasks[1].pop("notify")
            code, output = run(
                tasks,
                {"k8s_prereqs_version": "1.35.10"},
                stubs={"kubeadm": KUBEADM_IMAGES},
                directory=directory,
            )
            self.assertEqual(code, 0, output)
            lines = config.read_text().splitlines()
            self.assertEqual(lines[1], "      sandbox = 'registry.k8s.io/pause:3.10.1'")
            self.assertEqual(lines[3], "            sandboxer = 'podsandbox'")


if __name__ == "__main__":
    unittest.main()
