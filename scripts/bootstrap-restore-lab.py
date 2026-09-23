#!/usr/bin/env python3
"""Bootstrap the isolated lab, refusing production or an unexpected endpoint."""
import argparse
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
KUBECTL = ["kubectl", "--kubeconfig", str(ROOT / ".lab/kubeconfig")]
EXPECTED = {
    "homelabrestore01-node-1": "172.26.0.10",
    "homelabrestore01-node-2": "172.26.0.11",
}


def verify_target(config, nodes):
    if config.get("current-context") != "homelabrestore01":
        raise ValueError("The lab kubeconfig must select homelabrestore01")
    if len(config.get("clusters", [])) != 1:
        raise ValueError("Expected one selected lab cluster")
    cluster = config["clusters"][0]["cluster"]
    if (
        cluster.get("server") != "https://127.0.0.1:16443"
        or cluster.get("tls-server-name") != "172.26.0.10"
    ):
        raise ValueError("Expected the verified local lab tunnel and TLS identity")
    addresses = {
        n["metadata"]["name"]: next(
            (
                a["address"]
                for a in n["status"]["addresses"]
                if a["type"] == "InternalIP"
            ),
            None,
        )
        for n in nodes["items"]
    }
    if addresses != EXPECTED:
        raise ValueError("Refusing a cluster other than the two isolated lab nodes")


def apply_isolation():
    """Establish the lab network boundary before Applications can start Pods."""
    resources = {}
    for config in sorted((ROOT / "k8s/clusters/homelabrestore01").rglob("config.yml")):
        app = yaml.safe_load(config.read_text())
        if app["sourceType"] == "git":
            path = ROOT / app["gitPath"]
        elif app.get("hasResources"):
            path = config.parent
        else:
            continue
        rendered = subprocess.check_output(["kubectl", "kustomize", str(path)])
        for resource in yaml.safe_load_all(rendered):
            if resource and resource["kind"] in {
                "Namespace",
                "NetworkPolicy",
                "CiliumNetworkPolicy",
            }:
                metadata = resource["metadata"]
                namespace = (
                    metadata["name"]
                    if resource["kind"] == "Namespace"
                    else metadata.get("namespace", "")
                )
                if not (
                    namespace.startswith("restore-")
                    or namespace == "local-path-storage"
                ):
                    raise ValueError("Unexpected namespace in lab isolation resources")
                resources[(resource["kind"], namespace, metadata["name"])] = resource
    payload = json.dumps(
        {"apiVersion": "v1", "kind": "List", "items": list(resources.values())}
    )
    subprocess.run(
        KUBECTL + ["apply", "--server-side", "-f", "-"],
        input=payload.encode(),
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["check", "argocd", "applications"])
    args = parser.parse_args()
    config = json.loads(
        subprocess.check_output(KUBECTL + ["config", "view", "--minify", "-o", "json"])
    )
    nodes = json.loads(
        subprocess.check_output(KUBECTL + ["get", "nodes", "-o", "json"])
    )
    verify_target(config, nodes)
    if args.stage == "check":
        return
    if args.stage == "applications":
        apply_isolation()
    path = (
        ROOT
        / "k8s/bootstrap/restore-lab"
        / ("argocd" if args.stage == "argocd" else "applicationsets")
    )
    subprocess.run(KUBECTL + ["apply", "--server-side", "-k", str(path)], check=True)
    if args.stage == "argocd":
        subprocess.run(
            KUBECTL
            + [
                "wait",
                "--for=condition=Established",
                "--timeout=120s",
                "crd/applications.argoproj.io",
                "crd/applicationsets.argoproj.io",
                "crd/appprojects.argoproj.io",
            ],
            check=True,
        )
        for kind, name in [
            ("deployment", "argocd-server"),
            ("deployment", "argocd-repo-server"),
            ("deployment", "argocd-applicationset-controller"),
            ("statefulset", "argocd-application-controller"),
        ]:
            subprocess.run(
                KUBECTL
                + [
                    "-n",
                    "argocd",
                    "rollout",
                    "status",
                    f"{kind}/{name}",
                    "--timeout=300s",
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
