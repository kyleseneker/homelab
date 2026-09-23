#!/usr/bin/env python3
"""Preserve or restore application data for a clean, isolated lab rebuild.

This is a planned migration helper, not a replacement for offsite recovery or
full VM rollback archives. Export stops lab application deployments. Import
requires an empty local-path directory on the fresh worker.
"""
import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def validate_volumes(pvs, pvcs):
    """Only worker-local recovery volumes may be exported or imported."""
    assert pvs, "No bound recovery volumes found"
    claims = set()
    for pv in pvs:
        spec = pv["spec"]
        ref = spec["claimRef"]
        assert ref["namespace"].startswith("restore-")
        path = PurePosixPath(spec["hostPath"]["path"])
        assert path.parent == PurePosixPath("/opt/local-path-provisioner")
        assert path.name.startswith("pvc-") and ".." not in path.parts
        assert spec["storageClassName"] == "local-path"
        assert spec["nodeAffinity"]["required"]["nodeSelectorTerms"] == [
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
        claims.add((ref["namespace"], ref["name"], pv["metadata"]["name"]))
    assert claims == {
        (v["metadata"]["namespace"], v["metadata"]["name"], v["spec"]["volumeName"])
        for v in pvcs
    }


def require_idle(applications):
    for app in applications:
        if app.get("operation") or app.get("status", {}).get("operationState", {}).get(
            "phase"
        ) in {"Running", "Terminating"}:
            raise ValueError(
                "Wait for lab Application operations to finish before exporting data"
            )


def pause_applications(p, k):
    crd = subprocess.check_output(
        k
        + ["get", "crd", "applications.argoproj.io", "--ignore-not-found", "-o", "name"]
    )
    applications = []
    if crd.strip():
        applications = json.loads(
            subprocess.check_output(
                k + ["-n", "argocd", "get", "applications", "-o", "json"]
            )
        )["items"]
        assert all(a["spec"]["project"] == "restore-lab" for a in applications)
        require_idle(applications)
    saved = [
        {
            "name": a["metadata"]["name"],
            "skip": a["metadata"]
            .get("annotations", {})
            .get("argocd.argoproj.io/skip-reconcile"),
        }
        for a in applications
    ]
    (p / "applications-before.json").write_text(json.dumps(saved))
    controllers = []
    if crd.strip():
        controller = json.loads(
            subprocess.check_output(
                k
                + [
                    "-n",
                    "argocd",
                    "get",
                    "statefulset",
                    "argocd-application-controller",
                    "-o",
                    "json",
                ]
            )
        )
        controllers.append(
            {
                "name": controller["metadata"]["name"],
                "replicas": controller["spec"].get("replicas", 1),
            }
        )
    (p / "controllers-before.json").write_text(json.dumps(controllers))
    for controller in controllers:
        subprocess.run(
            k
            + [
                "-n",
                "argocd",
                "scale",
                "statefulset",
                controller["name"],
                "--replicas=0",
            ],
            check=True,
        )
        subprocess.run(
            k
            + [
                "-n",
                "argocd",
                "wait",
                "--for=delete",
                "pod",
                "-l",
                "app.kubernetes.io/name=argocd-application-controller",
                "--timeout=120s",
            ],
            check=True,
        )

    for app in saved:
        subprocess.run(
            k
            + [
                "-n",
                "argocd",
                "annotate",
                "application",
                app["name"],
                "argocd.argoproj.io/skip-reconcile=true",
                "--overwrite",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    if applications:
        require_idle(
            json.loads(
                subprocess.check_output(
                    k + ["-n", "argocd", "get", "applications", "-o", "json"]
                )
            )["items"]
        )


def resume(p, k):
    for deployment in json.loads((p / "replicas.json").read_text()):
        subprocess.run(
            k
            + [
                "-n",
                deployment["namespace"],
                "scale",
                "deployment",
                deployment["name"],
                "--replicas=" + str(deployment["replicas"]),
            ],
            check=True,
        )
    for app in json.loads((p / "applications-before.json").read_text()):
        annotation = "argocd.argoproj.io/skip-reconcile"
        annotation += "-" if app["skip"] is None else "=" + app["skip"]
        subprocess.run(
            k
            + [
                "-n",
                "argocd",
                "annotate",
                "application",
                app["name"],
                annotation,
                "--overwrite",
            ],
            check=True,
        )

    controllers = p / "controllers-before.json"
    if controllers.exists():
        for controller in json.loads(controllers.read_text()):
            subprocess.run(
                k
                + [
                    "-n",
                    "argocd",
                    "scale",
                    "statefulset",
                    controller["name"],
                    "--replicas=" + str(controller["replicas"]),
                ],
                check=True,
            )


def export(p, k):
    def get(*args):
        return json.loads(subprocess.check_output(k + list(args)))

    nodes = get("get", "nodes", "-o", "json")["items"]
    assert {n["metadata"]["name"] for n in nodes} == {
        "homelabrestore01-node-1",
        "homelabrestore01-node-2",
    }
    assert not (p / "replicas.json").exists()
    (p / "nodes-before.json").write_text(json.dumps(nodes))
    pvs = get("get", "pv", "-o", "json")
    pvcs = get("get", "pvc", "-A", "-o", "json")
    pvs["items"] = [v for v in pvs["items"] if v["status"]["phase"] == "Bound"]
    validate_volumes(pvs["items"], pvcs["items"])
    (p / "volumes-before.json").write_text(json.dumps(pvs))
    (p / "claims-before.json").write_text(json.dumps(pvcs))
    secrets = [
        s
        for s in get("get", "secrets", "-A", "-o", "json")["items"]
        if s["metadata"]["namespace"].startswith("restore-")
        and s["type"] == "Opaque"
        and not any(
            o.get("kind") == "ExternalSecret"
            for o in s["metadata"].get("ownerReferences", [])
        )
    ]
    assert secrets, "No bootstrap Secrets found"
    for s in secrets:
        s["metadata"] = {
            k: v for k, v in s["metadata"].items() if k in ["name", "namespace"]
        }
    (p / "bootstrap-secrets.json").write_text(
        json.dumps(dict(apiVersion="v1", kind="List", items=secrets))
    )
    replicas = [
        dict(
            namespace=d["metadata"]["namespace"],
            name=d["metadata"]["name"],
            replicas=d["spec"].get("replicas", 1),
        )
        for d in get("get", "deployments", "-A", "-o", "json")["items"]
        if d["metadata"]["namespace"].startswith("restore-")
    ]
    (p / "replicas.json").write_text(json.dumps(replicas))
    pause_applications(p, k)
    for d in replicas:
        subprocess.run(
            k
            + ["-n", d["namespace"], "scale", "deployment", d["name"], "--replicas=0"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    for ns in sorted({v["metadata"]["namespace"] for v in pvcs["items"]}):
        for pod in get("-n", ns, "get", "pods", "-o", "json")["items"]:
            if pod["status"].get("phase") not in ("Succeeded", "Failed"):
                subprocess.run(
                    k
                    + [
                        "-n",
                        ns,
                        "wait",
                        "--for=delete",
                        "pod/" + pod["metadata"]["name"],
                        "--timeout=120s",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
    running = [
        pod
        for pod in get("get", "pods", "-A", "-o", "json")["items"]
        if pod["metadata"]["namespace"].startswith("restore-")
        and pod["status"].get("phase") not in ("Succeeded", "Failed")
    ]
    assert not running, "Application writers remain active; refusing to copy live files"
    worker = [
        "ssh",
        "-i",
        ".lab/id_ed25519",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ProxyCommand=ssh -i "
        + str(Path.home() / ".ssh/id_ed25519_homelab")
        + " -o IdentitiesOnly=yes -o BatchMode=yes -W %h:%p root@192.168.10.2",
        "labadmin@172.26.0.11",
    ]
    paths = [Path(v["spec"]["hostPath"]["path"]).name for v in pvs["items"]]
    with (p / "volumes.tar.gz").open("wb") as f:
        subprocess.run(
            worker
            + [
                "sudo tar --numeric-owner -czf - -C /opt/local-path-provisioner "
                + " ".join(shlex.quote(path) for path in paths)
            ],
            check=True,
            stdout=f,
        )
    subprocess.run(
        ["tar", "-tzf", str(p / "volumes.tar.gz")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print(
        f'Preserved {len(pvs["items"])} stopped volumes and {len(secrets)} bootstrap Secrets privately; replica counts are saved.',
        flush=True,
    )


def restore(p, k, resume=False):
    pvs = json.loads((p / "volumes-before.json").read_text())["items"]
    pvcs = json.loads((p / "claims-before.json").read_text())["items"]
    validate_volumes(pvs, pvcs)
    roots = {Path(v["spec"]["hostPath"]["path"]).name for v in pvs}
    manifest = {}
    with tarfile.open(p / "volumes.tar.gz", "r:gz") as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            assert (
                not path.is_absolute()
                and ".." not in path.parts
                and path.parts[0] in roots
            )
            assert (
                member.isfile() or member.isdir()
            ), f"Unexpected archive member type: {member.name}"
            if member.isfile():
                f = tar.extractfile(member)
                h = hashlib.sha256()
                while True:
                    data = f.read(1024 * 1024)
                    if not data:
                        break
                    h.update(data)
                manifest[member.name] = h.hexdigest()
    worker = [
        "ssh",
        "-i",
        ".lab/id_ed25519",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ProxyCommand=ssh -i "
        + str(Path.home() / ".ssh/id_ed25519_homelab")
        + " -o IdentitiesOnly=yes -o BatchMode=yes -W %h:%p root@192.168.10.2",
        "labadmin@172.26.0.11",
    ]
    if not resume:
        with (p / "volumes.tar.gz").open("rb") as f:
            subprocess.run(
                worker
                + [
                    "sudo test ! -e /opt/local-path-provisioner && sudo mkdir -p /opt/local-path-provisioner && sudo tar --numeric-owner -xzf - -C /opt/local-path-provisioner"
                ],
                stdin=f,
                check=True,
            )
    verify = """sudo python3 - <<'INNER'
from pathlib import Path
import hashlib,json
root=Path('/opt/local-path-provisioner');result={}
for p in root.rglob('*'):
 if p.is_file():
  h=hashlib.sha256()
  with p.open('rb') as f:
   while True:
    d=f.read(1024*1024)
    if not d:break
    h.update(d)
  result[str(p.relative_to(root))]=h.hexdigest()
print(json.dumps(result))
INNER"""
    actual = json.loads(subprocess.check_output(worker + [verify]))
    assert actual == manifest
    (p / "volume-hashes.json").write_text(json.dumps(manifest))
    namespaces = sorted({v["metadata"]["namespace"] for v in pvcs})

    def apply(items):
        subprocess.run(
            k + ["apply", "--server-side", "-f", "-"],
            input=json.dumps(dict(apiVersion="v1", kind="List", items=items)).encode(),
            check=True,
            stdout=subprocess.DEVNULL,
        )

    apply(
        [
            dict(apiVersion="v1", kind="Namespace", metadata=dict(name=n))
            for n in namespaces
        ]
    )
    for v in pvs:
        v.pop("status", None)
        v["metadata"] = {"name": v["metadata"]["name"]}
        v["spec"]["claimRef"] = {
            k: v["spec"]["claimRef"][k] for k in ["name", "namespace"]
        }
    for v in pvcs:
        v.pop("status", None)
        v["metadata"] = {k: v["metadata"][k] for k in ["name", "namespace"]}
    apply(pvs)
    apply(pvcs)
    subprocess.run(
        k + ["apply", "--server-side", "-f", str(p / "bootstrap-secrets.json")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print(
        f"Restored {len(manifest)} files with matching hashes into {len(pvs)} volumes and restored the bootstrap Secrets."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import", "resume"])
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Verify already extracted files without overwriting them",
    )
    args = parser.parse_args()
    if args.resume and args.action != "import":
        parser.error("--resume applies only to import")
    os.umask(0o077)
    p = args.work_dir.resolve()
    if ROOT / ".lab" not in p.parents:
        parser.error("Use a private work directory beneath the ignored .lab directory")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/bootstrap-restore-lab.py"), "check"],
        check=True,
    )
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    p.chmod(0o700)
    os.chdir(ROOT)
    k = ["kubectl", "--kubeconfig", str(ROOT / ".lab/kubeconfig")]
    if args.action == "export":
        export(p, k)
    elif args.action == "import":
        restore(p, k, args.resume)
    else:
        resume(p, k)


if __name__ == "__main__":
    main()
