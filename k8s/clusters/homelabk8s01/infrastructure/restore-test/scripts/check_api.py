import json
import os
import sys
import time
import urllib.error
import urllib.request

FAILURES = (OSError, urllib.error.URLError, ValueError)


def get(base, path, key, timeout):
    headers = {"X-Api-Key": key} if key else {}
    request = urllib.request.Request(base + path, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def until(deadline, attempt, interval):
    while True:
        try:
            return attempt(), None
        except FAILURES as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if time.monotonic() >= deadline:
                return None, type(error).__name__
            time.sleep(interval)


def version(status):
    if not isinstance(status, dict):
        return None
    return status.get("version") or status.get("Version") or (status.get("data") or {}).get("bazarr_version")


def count(body):
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict) and "total" in body:
        return body["total"]
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return len(body["data"])
    raise ValueError("no count in response")


def field(body, path):
    for part in path.split("."):
        body = body[part]
    return body


def check(spec, key, timeout, interval=5, request_timeout=30):
    base = f"http://127.0.0.1:{spec['port']}"
    deadline = time.monotonic() + timeout
    status, error = until(deadline, lambda: get(base, spec["status"], key, request_timeout), interval)
    if status is None:
        return {"started": False, "error": error}, False
    report = {"started": True, "version": version(status)}
    probe = spec["probe"]
    if not probe.get("path"):
        return {**report, "probe_error": "unresolved"}, False
    body, error = until(deadline, lambda: get(base, probe["path"], key, request_timeout), interval)
    if body is None:
        return {**report, "probe_error": error}, False
    try:
        if "count_table" in probe:
            return {**report, "count": count(body)}, True
        value = field(body, probe["field"])
    except (KeyError, TypeError, ValueError) as failure:
        return {**report, "probe_error": type(failure).__name__}, False
    return {**report, "value": value, "matches": value == probe["equals"]}, True


if __name__ == "__main__":
    report, passed = check(json.loads(sys.argv[1]), os.environ.get("API_KEY", ""),
                           int(os.environ.get("STARTUP_TIMEOUT", "600")))
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
