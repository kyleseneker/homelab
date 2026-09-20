"""Selector-audit regressions; all Prometheus/kubectl responses are fixtures.

AST fixtures follow Prometheus v3.5.0 web/api/v1/translate_ast.go, also used by
the server's expression browser. No test contacts or mutates a cluster.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check-alert-metrics.sh"
# Keep the existing command self-contained while testing its Python entry point.
audit = types.ModuleType("alert_selector_audit")
source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
exec(compile(source, str(SCRIPT), "exec"), audit.__dict__)


def vector(name, matchers=(), kind="vectorSelector"):
    return {"type": kind, "name": name, "offset": 0, "timestamp": None,
            "startOrEnd": None,
            "matchers": list(matchers) + ([{"name": "__name__", "type": "=", "value": name}] if name else [])}


def call(name, *args):
    return {"type": "call", "func": {"name": name}, "args": list(args)}


def binary(left, right):
    return {"type": "binaryExpr", "op": "or", "lhs": left, "rhs": right,
            "matching": None, "bool": False}


def count_result(value="1"):
    return {"resultType": "vector", "result": [] if value is None else [{"metric": {}, "value": [1, value]}]}


def write_rules(root, rules, newline=True):
    path = root / "k8s/fixture.yaml"
    path.parent.mkdir(parents=True)
    data = {"apiVersion": "monitoring.coreos.com/v1", "kind": "PrometheusRule",
            "metadata": {"name": "fixture"}, "spec": {"groups": [{"name": "fixture", "rules": rules}]}}
    path.write_text(yaml.safe_dump(data).rstrip("\n") + ("\n" if newline else ""))


class SelectorASTTests(unittest.TestCase):
    def test_grouping_matching_labels_and_function_strings_are_not_metrics(self):
        requests = vector("http_requests_total", kind="matrixSelector")
        requests["range"] = 300000
        grouped = {"type": "aggregation", "op": "sum", "param": None,
                   "grouping": ["backup_location_name", "instance_name"], "without": False,
                   "expr": call("rate", requests)}
        renamed = call("label_replace", vector("up"),
                       *({"type": "stringLiteral", "val": value}
                         for value in ("service_name", "$1", "instance_name", "ghost_metric")))
        expression = binary(grouped, renamed)
        expression.update(op="/", matching={"labels": ["instance_name"], "include": ["service_name"],
                                            "on": True, "card": "many-to-one"})
        self.assertEqual(list(audit.selectors(expression)),
                         [('{__name__="http_requests_total"}', False), ('{__name__="up"}', False)])

    def test_absence_context_covers_nested_calls_but_not_a_sibling_occurrence(self):
        metric = vector("backup_success")
        nested = call("absent", {"type": "aggregation", "op": "sum", "param": None,
                                  "grouping": [], "without": False,
                                  "expr": call("rate", vector("backup_success", kind="matrixSelector"))})
        expression = binary(nested, binary(metric, call("absent_over_time", vector("other", kind="matrixSelector"))))
        self.assertEqual(list(audit.selectors(expression)),
                         [('{__name__="backup_success"}', True), ('{__name__="backup_success"}', False),
                          ('{__name__="other"}', True)])

    def test_label_literals_preserve_escapes_braces_spaces_and_newlines(self):
        value = 'literal } \\"quoted"\n two words\\path'
        node = vector("service:requests", [{"name": "path", "type": "=~", "value": value}])
        selector, absence = next(audit.selectors(node))
        self.assertFalse(absence)
        self.assertTrue(selector.startswith('{__name__="service:requests",path=~'))
        self.assertEqual(json.loads(selector.split("path=~", 1)[1][:-1]), value)
        self.assertNotIn("\n", selector)

    def test_name_less_selectors_are_included(self):
        node = vector("", [{"name": "job", "type": "=~", "value": "exporter.+"}])
        self.assertEqual(list(audit.selectors(node)), [('{job=~"exporter.+"}', False)])

    def test_aggregation_parameter_and_subquery_are_walked(self):
        expression = {"type": "aggregation", "op": "topk", "grouping": [], "without": False,
                      "param": call("scalar", vector("limit")),
                      "expr": {"type": "subquery", "expr": {"type": "parenExpr", "expr": vector("up")}}}
        self.assertEqual(set(audit.selectors(expression)),
                         {('{__name__="limit"}', False), ('{__name__="up"}', False)})

    def test_unknown_or_incomplete_ast_cannot_report_success(self):
        for expression in ({"type": "futureNode"}, {"type": "binaryExpr", "lhs": vector("up")},
                           {"type": "vectorSelector", "matchers": []},
                           {"type": "vectorSelector", "name": "up",
                            "matchers": [{"name": "job", "type": "=", "value": "prometheus"}]}):
            with self.subTest(expression=expression), self.assertRaises(audit.AuditError):
                list(audit.selectors(expression))


class APIResponseTests(unittest.TestCase):
    def request_with_response(self, response, returncode=0, stderr=""):
        with patch.object(audit.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode, response, stderr)):
            return audit.Prometheus(ROOT).request("query", "up")

    def test_pretty_printed_empty_result_is_recognized(self):
        response = json.dumps({"status": "success", "data": count_result(None)}, indent=2)
        self.assertFalse(audit.has_series(self.request_with_response(response)))

    def test_prometheus_and_transport_errors_are_visible(self):
        with self.assertRaisesRegex(audit.AuditError, "bad expression"):
            self.request_with_response('{"status":"error","error":"bad expression"}')
        with self.assertRaisesRegex(audit.AuditError, "forbidden"):
            self.request_with_response("", returncode=1, stderr="forbidden")
        with self.assertRaisesRegex(audit.AuditError, "valid JSON"):
            self.request_with_response("<html>success</html>")

    def test_api_warnings_are_not_silenced(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.request_with_response(json.dumps({"status": "success", "data": count_result(),
                                                   "warnings": ["partial data"], "infos": ["sample omitted"]}))
        self.assertIn("partial data", stderr.getvalue())
        self.assertIn("sample omitted", stderr.getvalue())

    def test_malformed_query_shapes_are_errors_not_missing_series(self):
        for result in ({}, {"resultType": "matrix", "result": []}, count_result("NaN"),
                       count_result("-1"), count_result("0.5"), {"resultType": "vector", "result": [{}]}):
            with self.subTest(result=result), self.assertRaises(audit.AuditError):
                audit.has_series(result)

    def test_query_is_encoded_and_exec_scope_is_preserved(self):
        response = json.dumps({"status": "success", "data": count_result()})
        query = 'count({path="two words & ? \\\"quoted\\\""})'
        with patch.object(audit.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, response, "")) as run:
            audit.Prometheus(ROOT).request("query", query)
        command = run.call_args.args[0]
        self.assertEqual(command[-4:-1], ["--", "wget", "-qO-"])
        self.assertIn("exec", command)
        self.assertEqual(parse_qs(urlparse(command[-1]).query), {"query": [query]})
        self.assertEqual(run.call_args.kwargs["timeout"], 45)


class AuditCommandTests(unittest.TestCase):
    def test_final_selector_without_newline_is_queried_and_reported_missing(self):
        # Run the actual shell entry point, using a fake kubectl for both APIs.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            script = root / "scripts/check-alert-metrics.sh"
            shutil.copy2(SCRIPT, script)
            write_rules(root, [{"alert": "AFirst", "expr": "up"},
                               {"alert": "ZLast", "expr": "last_metric"}], newline=False)
            fixtures = {"up": vector("up"), "last_metric": vector("last_metric")}
            (root / "ast.json").write_text(json.dumps(fixtures))
            kubectl = root / "kubectl"
            kubectl.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
root = Path(os.environ["FIXTURE_ROOT"])
url = urlparse(sys.argv[-1])
query = parse_qs(url.query)["query"][0]
with (root / "queries.jsonl").open("a") as out:
    out.write(json.dumps([url.path, query]) + "\\n")
if url.path.endswith("/parse_query"):
    data = json.loads((root / "ast.json").read_text())[query]
else:
    data = {"resultType": "vector", "result": [] if "last_metric" in query else [{"metric": {}, "value": [1, "1"]}]}
print(json.dumps({"status": "success", "data": data}, indent=2))
''')
            kubectl.chmod(0o755)
            result = subprocess.run([str(script)], capture_output=True, text=True, timeout=10,
                                    env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", FIXTURE_ROOT=str(root)))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("NO SERIES", result.stdout)
            self.assertIn("ZLast", result.stdout)
            self.assertIn("1 missing-series pairs, 0 query-error pairs out of 2 audited", result.stdout)
            queries = [json.loads(line) for line in (root / "queries.jsonl").read_text().splitlines()]
            self.assertIn(["/api/v1/query", 'count({__name__="last_metric"})'], queries)

    def test_absence_only_selectors_are_skipped_but_sibling_selector_is_audited(self):
        class Client:
            def __init__(self):
                self.queries = []

            def request(self, endpoint, expression):
                self.queries.append((endpoint, expression))
                if endpoint == "parse_query":
                    return binary(call("absent", vector("up")), binary(vector("up"), call("absent", vector("optional"))))
                return count_result()

        with tempfile.TemporaryDirectory() as directory:
            root, client, stdout = Path(directory), Client(), io.StringIO()
            write_rules(root, [{"alert": "Mixed", "expr": "absent(up) or up or absent(optional)"}])
            with redirect_stdout(stdout):
                self.assertEqual(audit.main(root, client), 0)
            self.assertIn(("query", 'count({__name__="up"})'), client.queries)
            self.assertNotIn(("query", 'count({__name__="optional"})'), client.queries)
            self.assertIn("Skipping 1 pairs used only inside absence functions", stdout.getvalue())

    def test_invalid_local_yaml_stops_before_any_live_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "k8s").mkdir()
            (root / "k8s/bad.yml").write_text("kind: PrometheusRule\nspec: [invalid")
            with redirect_stderr(io.StringIO()), patch.object(audit.Prometheus, "request") as request:
                self.assertEqual(audit.main(root), 2)
            request.assert_not_called()

    def test_query_failure_is_reported_separately_from_missing_series(self):
        class Client:
            def request(self, endpoint, expression):
                if endpoint == "parse_query":
                    return binary(vector("up"), vector("gone"))
                if expression == "vector(1)":
                    return count_result()
                if '"gone"' in expression:
                    return count_result(None)
                raise audit.AuditError("request timed out")

        with tempfile.TemporaryDirectory() as directory:
            root, stdout, stderr = Path(directory), io.StringIO(), io.StringIO()
            write_rules(root, [{"alert": "MixedFailure", "expr": "up or gone"}])
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(audit.main(root, Client()), 2)
            self.assertIn("1 missing-series pairs, 1 query-error pairs", stdout.getvalue())
            self.assertIn("request timed out", stderr.getvalue())
            self.assertNotIn("OK:", stdout.getvalue())

    def test_repository_rules_are_discovered(self):
        rules, files = audit.read_rules(ROOT)
        self.assertGreater(files, 1)
        self.assertTrue(any(name.endswith(": HighNodeCPU") for name, _ in rules))


if __name__ == "__main__":
    unittest.main()
