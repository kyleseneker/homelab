import json
import os
import sys
import time
import urllib.error
import urllib.request


def get(base, path, key):
    request = urllib.request.Request(base + path, headers={"X-Api-Key": key})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def check(port, status_path, count_path, key, timeout):
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while True:
        try:
            status = get(base, status_path, key)
            break
        except (OSError, urllib.error.URLError, ValueError):
            if time.monotonic() >= deadline:
                return {"started": False}, False
            time.sleep(5)
    count = len(get(base, count_path, key))
    return {"started": True, "version": status.get("version"), "count": count}, True


if __name__ == "__main__":
    report, passed = check(sys.argv[1], sys.argv[2], sys.argv[3], os.environ["API_KEY"],
                           int(os.environ.get("STARTUP_TIMEOUT", "600")))
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
