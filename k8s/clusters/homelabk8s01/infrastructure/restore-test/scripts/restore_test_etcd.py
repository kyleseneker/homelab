import base64
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import restore_test as harness

KNOWN_KEYS = ["/registry/namespaces/kube-system", "/registry/namespaces/media", "/registry/namespaces/backups"]
KINDS = ("snapshot-", "pki-", "control-plane-")
MAX_SET_AGE = 26 * 3600
CLIENT = "http://127.0.0.1:2379"


def newest_record(directory):
    records = sorted(pathlib.Path(directory).glob("recovery-*.json"))
    return records[-1] if records else None


def set_time(record):
    stamp = json.loads(record.read_text())["timestamp"]
    moment = datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=datetime.timezone.utc)
    return moment.timestamp()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def readable_archive(path):
    try:
        with tarfile.open(path) as archive:
            for member in archive:
                if member.isfile():
                    handle = archive.extractfile(member)
                    while handle.read(1 << 20):
                        pass
        return True
    except (OSError, EOFError, tarfile.TarError):
        return False


def verify_set(record):
    manifest = json.loads(record.read_text())
    problems, snapshot = [], None
    names = [item["name"] for item in manifest["files"]]
    for kind in KINDS:
        if not any(name.startswith(kind) for name in names):
            problems.append(f"no {kind.rstrip('-')} file")
    for item in manifest["files"]:
        path = record.parent / item["name"]
        if not path.is_file():
            problems.append(f"{item['name']} missing")
        elif path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            problems.append(f"{item['name']} does not match its checksum")
        elif item["name"].endswith(".tar.gz") and not readable_archive(path):
            problems.append(f"{item['name']} does not read")
        elif item["name"].startswith("snapshot-"):
            snapshot = path
    return snapshot, problems


def restore(binaries, snapshot, data_dir):
    completed = subprocess.run([str(binaries / "etcdutl"), "snapshot", "restore", str(snapshot),
                                "--data-dir", str(data_dir)], capture_output=True, text=True)
    return completed.returncode == 0


def request(path, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request(CLIENT + path, data=data), timeout=timeout) as response:
        return json.load(response)


def encode(text):
    return base64.b64encode(text.encode()).decode()


def count(key, range_end=None):
    body = {"key": encode(key), "count_only": True}
    if range_end:
        body["range_end"] = encode(range_end)
    return int(request("/v3/kv/range", body).get("count", 0))


def serve(binaries, data_dir, timeout=120):
    process = subprocess.Popen([str(binaries / "etcd"), "--name", "default", "--data-dir", str(data_dir),
                                "--listen-client-urls", CLIENT, "--advertise-client-urls", CLIENT,
                                "--listen-peer-urls", "http://127.0.0.1:2380", "--log-level", "error"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        try:
            if request("/health", timeout=5).get("health") == "true":
                return process
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(2)
    process.kill()
    return None


def check(snapshots, binaries, work, now):
    result = {"tiers": {}, "fences": {}, "rows": {}}
    record = newest_record(snapshots)
    result["tiers"]["restored"] = record is not None
    if record is None:
        harness.log("etcd: no recovery set found")
        return result
    snapshot, problems = verify_set(record)
    result["tiers"]["intact"] = not problems
    result["data_age"] = now - set_time(record)
    result["tiers"]["fresh"] = 0 <= result["data_age"] <= MAX_SET_AGE
    harness.log(f"etcd: {record.name}, {result['data_age'] / 3600:.1f} hours old, problems: {problems or 'none'}")
    if snapshot is None:
        return result
    usable = restore(binaries, snapshot, work / "data")
    process = serve(binaries, work / "data") if usable else None
    result["tiers"]["usable"] = process is not None
    if process is None:
        result["tiers"]["answers"] = False
        return result
    try:
        keys = count("/registry/", "/registry0")
        known = {key: count(key) > 0 for key in KNOWN_KEYS}
        result["rows"] = {"keys": keys}
        result["tiers"]["answers"] = keys > 0 and all(known.values())
        harness.log(f"etcd: {keys} keys under /registry/, known keys present: {json.dumps(known)}")
    except (OSError, urllib.error.URLError, ValueError) as error:
        harness.log(f"etcd: query failed: {type(error).__name__}")
        result["tiers"]["answers"] = False
    finally:
        process.terminate()
        process.wait(timeout=30)
    return result


def push(pushgateway, source, result, now):
    url = f"{pushgateway}/metrics/job/restore_test/target/etcd/source/{source}"
    outgoing = urllib.request.Request(url, data=harness.metrics(result, now).encode(), method="POST")
    with urllib.request.urlopen(outgoing, timeout=30):
        pass


def main(environ):
    started = time.time()
    try:
        result = check(pathlib.Path(environ["SNAPSHOTS"]), pathlib.Path(environ["ETCD_BIN"]),
                       pathlib.Path(environ["WORK"]), started)
    except Exception as error:
        harness.log(f"etcd: check failed: {type(error).__name__}: {error}")
        result = {"tiers": {"restored": False}, "fences": {}, "rows": {}}
    now = time.time()
    result["duration"] = now - started
    result["passed"] = harness.passed(result)
    harness.log(f"etcd: {'passed' if result['passed'] else 'FAILED'} {json.dumps(result['tiers'])}")
    push(environ["PUSHGATEWAY_URL"], environ["SOURCE"], result, now)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(os.environ))
