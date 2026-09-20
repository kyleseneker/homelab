import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("contract", ROOT / "scripts/check-appset-contract.py")
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ApplicationSetContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "k8s/clusters/homelabk8s01/apps/arr/sonarr"
        self.data = yaml.safe_load((self.directory / "config.yml").read_text())

    def test_actual_generator_contract(self):
        self.assertFalse(contract.main())

    def test_quoted_false_cannot_enable_namespace_or_resource_source(self):
        self.data.update(createNamespace="false", hasResources="false")
        errors = contract.validate(self.data, self.directory)
        self.assertTrue(any("createNamespace must be a YAML boolean" in e for e in errors))
        self.assertTrue(any("hasResources must be a YAML boolean" in e for e in errors))

    def test_unreferenced_supporting_resources_are_rejected(self):
        self.data["hasResources"] = False
        self.assertTrue(any("hasResources must match" in e for e in contract.validate(self.data, self.directory)))

    def test_unknown_source_cannot_silently_become_git(self):
        self.data["sourceType"] = "heml"
        self.assertTrue(any("sourceType" in e for e in contract.validate(self.data, self.directory)))


class BootstrapDependencyTests(unittest.TestCase):
    def local_resources(self, directory):
        """Walk local Kustomize resources without fetching the upstream install."""
        kustomization = next(directory / name for name in ("kustomization.yml", "kustomization.yaml")
                             if (directory / name).is_file())
        documents = []
        for resource in yaml.safe_load(kustomization.read_text())["resources"]:
            if resource.startswith("https://"):
                self.assertRegex(resource, r"^https://raw\.githubusercontent\.com/argoproj/argo-cd/v[0-9]+\.[0-9]+\.[0-9]+/manifests/install\.yaml$")
                continue
            path = directory / resource
            if path.is_dir():
                documents.extend(self.local_resources(path))
            else:
                documents.extend(document for document in yaml.safe_load_all(path.read_text()) if document)
        return documents

    def test_bootstrap_never_requires_a_controller_it_has_yet_to_install(self):
        # Kubernetes built-ins, Gateway CRDs installed by Ansible, and Argo CRDs
        # from the pinned upstream install are available before the ApplicationSet.
        builtin_groups = {
            "", "apps", "batch", "rbac.authorization.k8s.io", "networking.k8s.io",
            "policy", "autoscaling", "apiextensions.k8s.io", "apiregistration.k8s.io",
            "admissionregistration.k8s.io", "scheduling.k8s.io", "storage.k8s.io",
        }
        custom_apis = {("argoproj.io/v1alpha1", "ApplicationSet"),
                       ("argoproj.io/v1alpha1", "Application"),
                       ("argoproj.io/v1alpha1", "AppProject")}
        for path in (ROOT / "k8s/components/gateway-api").glob("*.yml"):
            for crd in yaml.safe_load_all(path.read_text()):
                for version in crd["spec"]["versions"]:
                    if version.get("served"):
                        custom_apis.add((f"{crd['spec']['group']}/{version['name']}", crd["spec"]["names"]["kind"]))
        documents = self.local_resources(ROOT / "k8s/bootstrap/argocd")
        documents += self.local_resources(ROOT / "k8s/bootstrap/applicationsets")
        self.assertTrue(documents)
        for document in documents:
            api, kind = document["apiVersion"], document["kind"]
            group = api.partition("/")[0] if "/" in api else ""
            self.assertTrue(group in builtin_groups or (api, kind) in custom_apis,
                            f"Bootstrap requires {api} {kind} before its controller can be installed")

    def test_notification_secret_is_reachable_through_the_applicationset(self):
        directory = ROOT / "k8s/clusters/homelabk8s01/infrastructure/argocd-notifications"
        path = directory / "config.yml"
        config = yaml.safe_load(path.read_text())
        appset = yaml.safe_load((ROOT / "k8s/bootstrap/applicationsets/cluster-apps.yml").read_text())
        discovered = {match for generator in appset["spec"]["generators"]
                      for pattern in generator["git"]["files"]
                      for match in ROOT.glob(pattern["path"])}
        self.assertIn(path, discovered)
        self.assertEqual(config["sourceType"], "git")
        self.assertEqual(config["namespace"], "argocd")
        self.assertFalse(contract.validate(config, directory))
        documents = self.local_resources(ROOT / config["gitPath"])
        secrets = [document for document in documents if document["kind"] == "ExternalSecret"
                   and document["metadata"]["name"] == "argocd-notifications-slack"]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(secrets[0]["metadata"]["namespace"], "argocd")
        self.assertEqual(secrets[0]["spec"]["target"]["name"], "argocd-notifications-secret")


class SecretWriteTests(unittest.TestCase):
    def test_failed_patch_cannot_overwrite_existing_secret(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            vault = directory / "vault"
            vault.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["CALL_LOG"], "a") as out:
    out.write(json.dumps({"args":sys.argv[1:], "payload":json.load(sys.stdin)})+"\\n")
if sys.argv[2] == "patch":
    sys.exit(2)
# Simulate the server refusing CAS=0 because the secret already exists.
sys.exit(2 if "-cas=0" in sys.argv else 0)
''')
            vault.chmod(0o755)
            value = 'literal $HOME $(touch should-not-exist) `false` "quotes"\nsecond line'
            env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}", VAULT_TOKEN="test",
                       SECRET_PATH="apps/arr", KEY="sonarr-api-key", VAL=value,
                       CALL_LOG=str(directory / "calls"))
            result = subprocess.run([str(ROOT / "scripts/vault-put-secret.sh")], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            calls = [json.loads(line) for line in (directory / "calls").read_text().splitlines()]
            self.assertEqual(len(calls), 2)
            self.assertIn("-cas=0", calls[1]["args"])
            self.assertEqual(calls[0]["payload"], {"sonarr-api-key": value})
            self.assertNotIn(value.encode(), result.stdout + result.stderr)

    def test_port_forward_failure_never_runs_vault_command(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            kubectl = directory / "kubectl"
            kubectl.write_text('#!/bin/sh\necho "address already in use" >&2\nexit 1\n')
            kubectl.chmod(0o755)
            marker = directory / "executed"
            result = subprocess.run([str(ROOT / "scripts/with-vault.sh"), "touch", str(marker)],
                                    env=dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}"),
                                    capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())


class RenovateTests(unittest.TestCase):
    def test_every_helm_config_is_discovered_once_with_unquoted_version(self):
        config = json.loads((ROOT / "renovate.json").read_text())
        managers = [m for m in config["customManagers"] if "Helm charts in ApplicationSet" in m["description"]]
        patterns = [(m, re.compile(re.sub(r"\(\?<([a-zA-Z]+)>", r"(?P<\1>", m["matchStrings"][0]))) for m in managers]
        for path in (ROOT / "k8s/clusters").rglob("config.yml"):
            data = yaml.safe_load(path.read_text())
            if data["sourceType"] != "helm":
                continue
            found = [(manager, pattern.search(path.read_text())) for manager, pattern in patterns]
            found = [(manager, match) for manager, match in found if match]
            self.assertEqual(len(found), 1, str(path))
            self.assertEqual(found[0][1]["currentValue"], data["chartVersion"])
            self.assertEqual(found[0][1]["depName"], data["chartName"])


if __name__ == "__main__":
    unittest.main()
