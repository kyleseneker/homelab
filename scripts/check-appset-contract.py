#!/usr/bin/env python3
"""Validate the values consumed by the ApplicationSet's Go template."""
import glob
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMMON = {"appName", "sourceType", "namespace", "syncOptions", "createNamespace"}
HELM = {"chartRepo", "chartName", "chartVersion", "hasResources"}
GIT = {"gitPath"}
OPTIONAL = {"annotations"}


def validate(data, directory, root=ROOT):
    errors = []
    if not isinstance(data, dict):
        return ["config must be a mapping"]
    source = data.get("sourceType")
    if source not in ("helm", "git"):
        errors.append("sourceType must be helm or git")
    required = COMMON | (HELM if source == "helm" else GIT)
    for key in sorted(required - data.keys()):
        errors.append(f"missing {key}; missingkey=error blocks the generator")
    for key in sorted(data.keys() - (COMMON | HELM | GIT | OPTIONAL)):
        errors.append(f"unknown field {key}")
    for key in ("appName", "sourceType"):
        if not isinstance(data.get(key), str) or not data[key]:
            errors.append(f"{key} must be a nonempty string")
    if not isinstance(data.get("namespace"), str) or (source == "helm" and not data["namespace"]):
        errors.append("namespace must be a string, and nonempty for Helm")
    for key in ("createNamespace",) + (("hasResources",) if source == "helm" else ()):
        if type(data.get(key)) is not bool:
            errors.append(f"{key} must be a YAML boolean, not a quoted string")
    options = data.get("syncOptions")
    if not isinstance(options, list) or not all(isinstance(v, str) for v in options):
        errors.append("syncOptions must be a list of strings")
    annotations = data.get("annotations", {})
    if not isinstance(annotations, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in annotations.items()
    ):
        errors.append("annotations must map strings to strings")
    if source == "helm":
        for key in ("chartRepo", "chartName", "chartVersion"):
            if not isinstance(data.get(key), str) or not data[key]:
                errors.append(f"{key} must be a nonempty string (quote numeric versions)")
        if not (directory / "values.yml").is_file():
            errors.append("Helm source is missing values.yml")
        has_kustomization = any((directory / name).is_file() for name in ("kustomization.yml", "kustomization.yaml"))
        if bool(data.get("hasResources")) != has_kustomization:
            errors.append("hasResources must match the presence of a kustomization")
    if source == "git":
        path = data.get("gitPath")
        if not isinstance(path, str) or not path:
            errors.append("gitPath must be a nonempty string")
        elif root.resolve() not in ((root / path).resolve(), *(root / path).resolve().parents):
            errors.append("gitPath must stay inside the repository")
        elif not (root / path).is_dir():
            errors.append(f"gitPath does not exist: {path}")
    return errors


def main():
    appset = ROOT / "k8s/bootstrap/applicationsets/cluster-apps.yml"
    src = appset.read_text()
    refs = set()
    for action in re.findall(r"\{\{(.*?)\}\}", src, re.S):
        refs.update(re.findall(r"(?<![\w$])\.([A-Za-z][A-Za-z0-9_]*)", action))
    errors = [f"ApplicationSet reads unknown field {key}" for key in refs - (COMMON | HELM | GIT | OPTIONAL | {"path"})]
    names = {}
    # Use the actual generator globs so this validates exactly what Argo discovers.
    document = yaml.safe_load(src)
    files = set()
    for generator in document["spec"]["generators"]:
        for pattern in generator["git"]["files"]:
            files.update(Path(p) for p in glob.glob(str(ROOT / pattern["path"]), recursive=True))
    if not files:
        errors.append("ApplicationSet generator matched no configs")
    for path in sorted(files):
        try:
            data = yaml.safe_load(path.read_text())
            errors.extend(f"{path.relative_to(ROOT)}: {error}" for error in validate(data, path.parent))
            if isinstance(data, dict) and isinstance(data.get("appName"), str):
                name = data["appName"]
                if name in names:
                    errors.append(f"duplicate appName {name}: {names[name]} and {path}")
                names[name] = path
        except yaml.YAMLError as error:
            errors.append(f"{path}: {error}")
    for error in errors:
        print(f"  FAIL {error}", file=sys.stderr)
    if not errors:
        print(f"  {len(files)} ApplicationSet configs valid")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
