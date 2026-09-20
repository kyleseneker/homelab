#!/usr/bin/env bash
# Read-only audit of the current series referenced by local PrometheusRule files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$ROOT" <<'PY'
"""Audit current selector coverage, not rule correctness or alert delivery.

Use the running Prometheus parser instead of guessing PromQL with regular
expressions. Selectors nested inside absent()/absent_over_time() are reported
separately; their absence is intentional. Other occurrences remain audited.
Range windows, offsets, joins, thresholds, and notification delivery are outside
this check. /api/v1/parse_query is experimental: unknown AST shapes fail closed.
API contract: https://prometheus.io/docs/prometheus/latest/querying/api/
"""

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode

import yaml


class AuditError(Exception):
    pass


class Prometheus:
    def __init__(self, root):
        self.command = [
            "kubectl", "--kubeconfig", os.environ.get("KUBECONFIG", str(root / "kubeconfig")),
            "-n", os.environ.get("PROM_NS", "monitoring"), "exec", "-c", "prometheus",
            os.environ.get("PROM_STS", "statefulset/prometheus-kube-prometheus-stack-prometheus"),
            "--", "wget", "-qO-",
        ]

    def request(self, endpoint, expression):
        url = "http://localhost:9090/api/v1/" + endpoint + "?" + urlencode({"query": expression})
        try:
            result = subprocess.run(self.command + [url], capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AuditError(f"{endpoint}: {error}") from error
        if result.returncode:
            detail = result.stderr.strip() or f"kubectl/wget exited {result.returncode}"
            raise AuditError(f"{endpoint}: {detail}")
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AuditError(f"{endpoint}: response was not valid JSON") from error
        if not isinstance(response, dict) or response.get("status") != "success":
            detail = response.get("error", "missing success status") if isinstance(response, dict) else "expected object"
            raise AuditError(f"{endpoint}: {detail}")
        for key in ("warnings", "infos"):
            notices = response.get(key, [])
            if not isinstance(notices, list) or any(not isinstance(item, str) for item in notices):
                raise AuditError(f"{endpoint}: response has malformed {key}")
            for notice in notices:
                print(f"  API NOTICE   {endpoint}: {notice}", file=sys.stderr)
        if "data" not in response:
            raise AuditError(f"{endpoint}: response has no data")
        return response["data"]


def selector_text(node):
    matchers = node.get("matchers")
    if not isinstance(matchers, list) or not matchers:
        raise AuditError("parser returned a selector without matchers")
    if not isinstance(node.get("name"), str):
        raise AuditError("parser returned a selector without a name field")
    parts = []
    for matcher in matchers:
        if not isinstance(matcher, dict):
            raise AuditError("parser returned a malformed matcher")
        name, operator, value = (matcher.get(key) for key in ("name", "type", "value"))
        if not isinstance(name, str) or not isinstance(value, str) or operator not in ("=", "!=", "=~", "!~"):
            raise AuditError("parser returned a malformed matcher")
        label = name if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name) else json.dumps(name, ensure_ascii=False)
        parts.append(label + operator + json.dumps(value, ensure_ascii=False))
    if node["name"] and not any(m["name"] == "__name__" and m["type"] == "=" and m["value"] == node["name"] for m in matchers):
        raise AuditError("parser omitted the selector's metric-name matcher")
    # The AST includes an __name__ matcher for explicit metric names. Keeping all
    # matchers also supports name-less selectors and recording rules with colons.
    return "{" + ",".join(sorted(parts)) + "}"


def selectors(node, absence=False):
    """Yield (selector, inside_absence_function) from known expression nodes."""
    if not isinstance(node, dict):
        raise AuditError("parser returned a malformed expression node")
    kind = node.get("type")
    if kind in ("vectorSelector", "matrixSelector"):
        yield selector_text(node), absence
        return
    if kind in ("numberLiteral", "stringLiteral"):
        return
    if kind == "call":
        function = node.get("func")
        children = node.get("args")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not isinstance(children, list):
            raise AuditError("parser returned a malformed function call")
        absence = absence or function["name"] in ("absent", "absent_over_time")
    elif kind == "aggregation":
        children = [node.get("expr")]
        if node.get("param") is not None:
            children.append(node["param"])
    elif kind == "binaryExpr":
        children = [node.get("lhs"), node.get("rhs")]
    elif kind in ("parenExpr", "unaryExpr", "subquery"):
        children = [node.get("expr")]
    else:
        raise AuditError(f"unsupported Prometheus AST node {kind!r}; update the selector audit for this server version")
    for child in children:
        yield from selectors(child, absence)


def read_rules(root):
    paths = sorted(path for path in (root / "k8s").rglob("*") if path.suffix in (".yml", ".yaml"))
    rules, files = [], set()
    for path in paths:
        source = path.read_text()
        if "PrometheusRule" not in source:
            continue
        try:
            for document in yaml.safe_load_all(source):
                if not isinstance(document, dict) or document.get("kind") != "PrometheusRule":
                    continue
                files.add(path)
                for group in document["spec"]["groups"]:
                    for rule in group.get("rules", []):
                        name = rule.get("alert") or rule.get("record")
                        expression = rule["expr"]
                        if not isinstance(name, str) or isinstance(expression, bool) or not isinstance(expression, (str, int, float)):
                            raise ValueError("rule needs an alert/record name and a PromQL expression")
                        rules.append((f"{path.relative_to(root)}: {name}", str(expression)))
        except (yaml.YAMLError, KeyError, TypeError, AttributeError, ValueError) as error:
            raise AuditError(f"{path}: cannot read PrometheusRule: {error}") from error
    if not rules:
        raise AuditError("no local PrometheusRule rules found under k8s")
    return rules, len(files)


def has_series(data):
    """Validate the result of count(selector), whose empty input returns []."""
    if not isinstance(data, dict) or data.get("resultType") != "vector" or not isinstance(data.get("result"), list):
        raise AuditError("query returned an unexpected result shape")
    result = data["result"]
    if not result:
        return False
    try:
        if len(result) != 1 or len(result[0]["value"]) != 2:
            raise ValueError("expected one count sample")
        count = float(result[0]["value"][1])
        if not math.isfinite(count) or count < 0 or not count.is_integer():
            raise ValueError("invalid count")
    except (KeyError, TypeError, ValueError) as error:
        raise AuditError("query returned an invalid count sample") from error
    return count > 0


def main(root, client=None):
    try:
        rules, file_count = read_rules(root)
        client = client or Prometheus(root)
        if not has_series(client.request("query", "vector(1)")):
            raise AuditError("Prometheus connectivity query returned no result")
        required, absence_only = set(), set()
        for name, expression in rules:
            try:
                for selector, inside_absence in selectors(client.request("parse_query", expression)):
                    (absence_only if inside_absence else required).add((name, selector))
            except AuditError as error:
                raise AuditError(f"{name}: {error}") from error
    except (AuditError, OSError) as error:
        print(f"ERROR: selector audit could not complete: {error}", file=sys.stderr)
        return 2

    print(f"Auditing {len(required)} rule/selector pairs from {len(rules)} rules in {file_count} local files.")
    print(f"Skipping {len(absence_only - required)} pairs used only inside absence functions.")
    print("Scope: current series only; does not verify history, rule logic, deployed rules, or alert delivery.")
    missing = errors = 0
    results = {}
    for name, selector in sorted(required):
        if selector not in results:
            try:
                results[selector] = has_series(client.request("query", f"count({selector})"))
            except AuditError as error:
                results[selector] = error
        result = results[selector]
        if isinstance(result, AuditError):
            print(f"  QUERY ERROR  {name} -> {selector}: {result}", file=sys.stderr)
            errors += 1
        elif not result:
            print(f"  NO SERIES    {name} -> {selector}")
            missing += 1
    if errors or missing:
        print(f"AUDIT FAILED: {missing} missing-series pairs, {errors} query-error pairs out of {len(required)} audited.")
        return 2 if errors else 1
    print(f"OK: all {len(required)} audited rule/selector pairs currently match at least one series.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
PY
