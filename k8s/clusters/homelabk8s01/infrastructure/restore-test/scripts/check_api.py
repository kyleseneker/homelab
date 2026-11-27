import json
import os
import sys
import time
import urllib.error
import urllib.request

FAILURES = (OSError, urllib.error.URLError, ValueError)


def get(base, path, key, timeout):
    request = urllib.request.Request(base + path, headers={"X-Api-Key": key})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def until(deadline, attempt, interval):
    while True:
        try:
            return attempt(), None
        except FAILURES as error:
            if time.monotonic() >= deadline:
                return None, type(error).__name__
            time.sleep(interval)


def check(port, status_path, count_path, key, timeout, interval=5, request_timeout=30):
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    status, error = until(deadline, lambda: get(base, status_path, key, request_timeout), interval)
    if status is None:
        return {"started": False, "error": error}, False
    items, error = until(deadline, lambda: get(base, count_path, key, request_timeout), interval)
    if items is None:
        return {"started": True, "version": status.get("version"), "count_error": error}, False
    return {"started": True, "version": status.get("version"), "count": len(items)}, True


if __name__ == "__main__":
    report, passed = check(sys.argv[1], sys.argv[2], sys.argv[3], os.environ["API_KEY"],
                           int(os.environ.get("STARTUP_TIMEOUT", "600")))
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
