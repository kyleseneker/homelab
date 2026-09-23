"""Regression guards for the lab/production bootstrap boundary."""

import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lab_bootstrap", ROOT / "scripts/bootstrap-restore-lab.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class LabBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "current-context": "homelabrestore01",
            "clusters": [
                {
                    "cluster": {
                        "server": "https://127.0.0.1:16443",
                        "tls-server-name": "172.26.0.10",
                    }
                }
            ],
        }
        self.nodes = {
            "items": [
                {
                    "metadata": {"name": name},
                    "status": {
                        "addresses": [{"type": "InternalIP", "address": address}]
                    },
                }
                for name, address in bootstrap.EXPECTED.items()
            ]
        }

    def test_expected_lab_is_accepted(self):
        bootstrap.verify_target(self.config, self.nodes)

    def test_production_context_is_rejected(self):
        self.config["current-context"] = "kubernetes-admin@kubernetes"
        with self.assertRaises(ValueError):
            bootstrap.verify_target(self.config, self.nodes)

    def test_tunnel_to_unexpected_server_is_rejected(self):
        self.config["clusters"][0]["cluster"]["server"] = "https://192.168.10.50:6443"
        with self.assertRaises(ValueError):
            bootstrap.verify_target(self.config, self.nodes)

    def test_node_identity_is_verified_even_with_lab_context(self):
        self.nodes["items"][0]["status"]["addresses"][0]["address"] = "192.168.10.50"
        with self.assertRaises(ValueError):
            bootstrap.verify_target(self.config, self.nodes)

    def test_lab_overlay_selects_only_lab_configs_and_project(self):
        path = ROOT / "k8s/bootstrap/restore-lab/applicationsets"
        overlay = yaml.safe_load((path / "kustomization.yml").read_text())
        patches = yaml.safe_load(overlay["patches"][0]["patch"])
        self.assertIn(
            {
                "op": "replace",
                "path": "/spec/generators/0/git/files/0/path",
                "value": "k8s/clusters/homelabrestore01/**/config.yml",
            },
            patches,
        )
        self.assertIn(
            {
                "op": "replace",
                "path": "/spec/template/spec/project",
                "value": "restore-lab",
            },
            patches,
        )
        project = yaml.safe_load((path / "project.yml").read_text())["spec"]
        self.assertEqual(
            {d["namespace"] for d in project["destinations"]},
            {"restore-*", "local-path-storage"},
        )
        self.assertEqual(
            {d["server"] for d in project["destinations"]},
            {"https://kubernetes.default.svc"},
        )


class LabVolumeBoundaryTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "lab_data", ROOT / "scripts/restore-lab-data.py"
        )
        self.data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.data)
        self.pv = {
            "metadata": {"name": "pvc-test"},
            "spec": {
                "claimRef": {"namespace": "restore-test", "name": "data"},
                "hostPath": {"path": "/opt/local-path-provisioner/pvc-test"},
                "storageClassName": "local-path",
                "nodeAffinity": {
                    "required": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "kubernetes.io/hostname",
                                        "operator": "In",
                                        "values": ["homelabrestore01-node-2"],
                                    }
                                ]
                            }
                        ]
                    }
                },
            },
        }
        self.pvc = {
            "metadata": {"namespace": "restore-test", "name": "data"},
            "spec": {"volumeName": "pvc-test"},
        }

    def test_export_refuses_inflight_sync(self):
        for app in [
            {"operation": {"sync": {}}},
            {"status": {"operationState": {"phase": "Running"}}},
        ]:
            with self.assertRaises(ValueError):
                self.data.require_idle([app])

    def test_restore_refuses_host_system_paths(self):
        self.pv["spec"]["hostPath"]["path"] = "/etc/kubernetes"
        with self.assertRaises(AssertionError):
            self.data.validate_volumes([self.pv], [self.pvc])

    def test_restore_refuses_production_claims(self):
        self.pv["spec"]["claimRef"]["namespace"] = "vault"
        with self.assertRaises(AssertionError):
            self.data.validate_volumes([self.pv], [self.pvc])

    def test_restore_refuses_unmatched_claims(self):
        self.pvc["spec"]["volumeName"] = "different-volume"
        with self.assertRaises(AssertionError):
            self.data.validate_volumes([self.pv], [self.pvc])


if __name__ == "__main__":
    unittest.main()
