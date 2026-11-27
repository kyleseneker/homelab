import datetime
import json
import os
import pathlib
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://kubernetes.default.svc"
ACCOUNT = pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount")
SCRIPTS = pathlib.Path(__file__).resolve().parent
SANDBOX = "restore-sandbox"
VELERO = "backups"
MODIFIERS = "restore-test-modifiers"
STORAGE_CLASS = "nfs-restore-test"
SELECTOR = {"app.kubernetes.io/component": "backup-volume"}
BACKUP_DONE = {"Completed", "PartiallyFailed", "Failed", "FailedValidation"}
RESTORE_DONE = {"Completed", "PartiallyFailed", "Failed", "FailedValidation"}
RESTRICTED = {"readOnlyRootFilesystem": True, "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
SMALL = {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "256Mi"}}
HOUR = 3600
CANARY = {
    "apiVersion": "arrchitect.dev/v1alpha1",
    "kind": "Sonarr",
    "metadata": {"name": "restore-test-canary", "namespace": SANDBOX},
    "spec": {"connection": {"url": "http://192.0.2.1:8989", "apiKeySecretRef": {"name": "restore-test-canary", "key": "api-key"}}},
}


def pvr_app(name, port, version, collection, table):
    return {
        "deployment": name,
        "port": port,
        "config": f"/config/{name}.db",
        "api_key_env": f"{name.upper()}__AUTH__APIKEY",
        "status_path": f"/api/{version}/system/status",
        "count_path": f"/api/{version}/{collection}",
        "count_table": table,
    }


def target(name, namespace, claim, kind, path, max_dump_age=26 * HOUR, **extra):
    return {"name": name, "namespace": namespace, "claim": claim, "kind": kind, "path": path,
            "max_dump_age": max_dump_age, **extra}


TARGETS = [
    target("sonarr", "media", "config-backups", "sqlite", "sonarr/sonarr.db",
           require=["Series"], report=["Episodes", "EpisodeFiles"], strict_foreign_keys=True,
           app=pvr_app("sonarr", 8989, "v3", "series", "Series")),
    target("radarr", "media", "config-backups", "sqlite", "radarr/radarr.db",
           require=["VersionInfo"], report=["Movies", "MovieFiles"],
           app=pvr_app("radarr", 7878, "v3", "movie", "Movies")),
    target("prowlarr", "media", "config-backups", "sqlite", "prowlarr/prowlarr.db",
           require=["VersionInfo"], report=["Indexers", "Applications"],
           app=pvr_app("prowlarr", 9696, "v1", "indexer", "Indexers")),
    target("bazarr", "media", "config-backups", "sqlite", "bazarr/db/bazarr.db"),
    target("jellyfin", "media", "config-backups", "sqlite", "jellyfin/data/data/jellyfin.db"),
    target("seerr", "media", "config-backups", "sqlite", "seerr/db/db.sqlite3"),
    target("tdarr", "media", "config-backups", "zip", "tdarr/latest.zip", max_dump_age=50 * HOUR,
           inner="DB2/SQL/database.db"),
    target("uptime-kuma", "monitoring", "uptime-kuma-backups", "sqlite", "kuma.db"),
    target("authentik", "auth", "authentik-backups", "pgdump", "authentik.dump",
           stamp="completed-at", image_from={"namespace": "auth", "cronjob": "authentik-backup", "container": "dump"}),
    target("home-assistant", "home-automation", "home-assistant-backups", "hatar", "", max_dump_age=40 * HOUR),
]


def log(message):
    print(f"{datetime.datetime.now(datetime.timezone.utc):%H:%M:%S} {message}", flush=True)


def parse_time(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class Api:
    def __init__(self):
        self.context = ssl.create_default_context(cafile=str(ACCOUNT / "ca.crt"))

    def call(self, method, path, body=None, query=None):
        url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + (ACCOUNT / "token").read_text().strip())
        if data is not None:
            kind = "application/merge-patch+json" if method == "PATCH" else "application/json"
            request.add_header("Content-Type", kind)
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=60) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def json(self, method, path, body=None, query=None):
        status, text = self.call(method, path, body, query)
        if status not in (200, 201):
            raise RuntimeError(f"{method} {path} returned HTTP {status}")
        return json.loads(text) if text else {}


def wait_for(check, timeout, what, interval=5):
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {what}")
        time.sleep(interval)


def restore_body(name, schedule, namespaces):
    return {
        "apiVersion": "velero.io/v1",
        "kind": "Restore",
        "metadata": {"name": name, "namespace": VELERO, "labels": {"app.kubernetes.io/name": "restore-test"}},
        "spec": {
            "scheduleName": schedule,
            "includedNamespaces": sorted(namespaces),
            "namespaceMapping": {namespace: SANDBOX for namespace in sorted(namespaces)},
            "includedResources": ["pods", "persistentvolumeclaims", "persistentvolumes"],
            "includeClusterResources": False,
            "labelSelector": {"matchLabels": dict(SELECTOR)},
            "existingResourcePolicy": "none",
            "resourceModifier": {"kind": "ConfigMap", "name": MODIFIERS},
        },
    }


def backup_pod(name, target, containers, init=None, workdir=False):
    volumes = [
        {"name": "backup", "persistentVolumeClaim": {"claimName": target["claim"], "readOnly": True}},
        {"name": "config", "emptyDir": {}},
        {"name": "work", "emptyDir": {}},
    ]
    spec = {
        "restartPolicy": "Never",
        "automountServiceAccountToken": False,
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": containers,
        "volumes": volumes,
    }
    if init:
        spec["initContainers"] = init
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "namespace": SANDBOX, "labels": {"app.kubernetes.io/name": "restore-test-check"}},
        "spec": spec,
    }


def helper(name, user, image, command, mounts, env=None):
    uid, gid = user
    return {
        "name": name,
        "image": image,
        "command": command,
        "securityContext": {**RESTRICTED, "runAsNonRoot": True, "runAsUser": uid, "runAsGroup": gid},
        "resources": SMALL,
        "volumeMounts": mounts,
        "env": [{"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}, *(env or [])],
    }


BACKUP_MOUNT = {"name": "backup", "mountPath": "/backup", "readOnly": True}
COPY = "import os, shutil, sys; shutil.copyfile(sys.argv[1], sys.argv[2]); os.chmod(sys.argv[2], 0o666)"
WORK_MOUNT = {"name": "work", "mountPath": "/work"}


def check_command(target, scripts):
    path = "/backup/" + target["path"]
    if target["kind"] == "sqlite":
        return ["python3", "-c", scripts["check_sqlite"], path, ",".join(target.get("require", [])),
                ",".join(target.get("report", [])), "1" if target.get("strict_foreign_keys") else "0"]
    if target["kind"] == "zip":
        return ["python3", "-c", scripts["check_zip"], path, target["inner"], "/work"]
    if target["kind"] == "hatar":
        return ["python3", "-c", scripts["check_ha"], "/backup"]
    if target["kind"] == "pgdump":
        return ["sh", "-c", scripts["check_pgdump"], "check", path, "/backup/" + target["stamp"]]
    raise ValueError(f"unknown target kind {target['kind']}")


def integrity_pod(target, image, user, scripts):
    command = check_command(target, scripts)
    check = helper("check", user, image, command, [BACKUP_MOUNT, WORK_MOUNT])
    return backup_pod(f"check-{target['name']}", target, [check])


def app_pod(target, deployment, image, user, key, script):
    app = target["app"]
    live = deployment["spec"]["template"]["spec"]["containers"][0]
    env = [item for item in live.get("env", []) if "value" in item and item["name"] != app["api_key_env"]]
    env.append({"name": app["api_key_env"], "value": key})
    copy = helper(
        "copy", user, image,
        ["python3", "-c", COPY, "/backup/" + target["path"], app["config"]],
        [BACKUP_MOUNT, {"name": "config", "mountPath": "/config"}],
    )
    application = {
        "name": "app",
        "image": live["image"],
        "env": env,
        "securityContext": live.get("securityContext", {}),
        "resources": live.get("resources", {}),
        "volumeMounts": [{"name": "config", "mountPath": "/config"}],
    }
    check = helper(
        "check", user, image,
        ["python3", "-c", script, str(app["port"]), app["status_path"], app["count_path"]],
        [], [{"name": "API_KEY", "value": key}],
    )
    return backup_pod(f"app-{target['name']}", target, [application, check], init=[copy])


def dump_time(report):
    if report.get("mtime") is not None:
        return float(report["mtime"])
    if report.get("timestamp"):
        try:
            return parse_time(report["timestamp"])
        except ValueError:
            return None
    return None


def fresh(backup_started, dump_written, now, max_backup_age, max_dump_age):
    if dump_written is None:
        return False
    dump_age = backup_started - dump_written
    return now - backup_started <= max_backup_age and 0 <= dump_age <= max_dump_age


def metrics(result, now):
    lines = [
        f"restore_test_last_attempt_timestamp_seconds {now:.0f}",
        f"restore_test_duration_seconds {result['duration']:.0f}",
    ]
    for name, key in (("data_age_seconds", "data_age"), ("dump_age_seconds", "dump_age"),
                      ("restored_bytes", "bytes"), ("foreign_key_violations", "foreign_key_violations"),
                      ("total_rows", "total_rows")):
        if result.get(key) is not None:
            lines.append(f"restore_test_{name} {result[key]:.0f}")
    for tier, passed in result["tiers"].items():
        lines.append(f'restore_test_tier_passed{{tier="{tier}"}} {int(passed)}')
    for fence, passed in result["fences"].items():
        lines.append(f'restore_test_fence_passed{{fence="{fence}"}} {int(passed)}')
    for table, count in result.get("rows", {}).items():
        lines.append(f'restore_test_rows{{table="{table}"}} {count}')
    if result["passed"]:
        lines.append(f"restore_test_last_success_timestamp_seconds {now:.0f}")
    return "\n".join(lines) + "\n"


def passed(result):
    return bool(result["tiers"]) and all(result["tiers"].values()) and all(result["fences"].values())


class Run:
    def __init__(self, api, environ):
        self.api = api
        self.source = environ["SOURCE"]
        self.schedule = environ["SCHEDULE"]
        self.max_age = int(environ["MAX_BACKUP_AGE_SECONDS"])
        self.pushgateway = environ["PUSHGATEWAY_URL"]
        self.image = environ["CHECK_IMAGE"]
        self.keep = environ.get("KEEP_SANDBOX") == "true"
        self.scripts = {name: (SCRIPTS / file).read_text() for name, file in (
            ("check_sqlite", "check_sqlite.py"), ("check_zip", "check_zip.py"), ("check_ha", "check_ha.py"),
            ("check_api", "check_api.py"), ("check_pgdump", "check_pgdump.sh"))}
        self.restore = None
        self.restore_started = None
        self.created = False
        self.results = {target["name"]: {"tiers": {}, "fences": {}, "rows": {}} for target in TARGETS}

    def backups(self):
        items = self.api.json("GET", f"/apis/velero.io/v1/namespaces/{VELERO}/backups",
                              query={"labelSelector": f"velero.io/schedule-name={self.schedule}"})["items"]
        if not items:
            raise RuntimeError(f"no backups from {self.schedule}")
        return sorted(items, key=lambda item: item["metadata"]["creationTimestamp"], reverse=True)

    def latest_finished(self):
        latest = self.backups()[0]
        return latest.get("status", {}).get("phase") in BACKUP_DONE

    def newest_completed(self):
        for item in self.backups():
            if item.get("status", {}).get("phase") == "Completed":
                return item["metadata"]["name"]
        raise RuntimeError(f"no completed backup from {self.schedule}")

    def fences(self):
        deployment = self.api.json("GET", "/apis/apps/v1/namespaces/arrchitect/deployments/arrchitect")
        args = [arg for container in deployment["spec"]["template"]["spec"]["containers"] for arg in container.get("args", [])]
        status, text = self.api.call("POST", f"/apis/arrchitect.dev/v1alpha1/namespaces/{SANDBOX}/sonarrs",
                                     CANARY, query={"dryRun": "All"})
        refused = status in (400, 403, 422) and "deny-arrchitect-in-restore-sandbox" in text
        return {"watch_namespace": "--watch-namespace=media" in args, "arrchitect_refused": refused}

    def arrchitect_absent(self):
        resources = self.api.json("GET", "/apis/arrchitect.dev/v1alpha1")["resources"]
        for resource in resources:
            if "/" in resource["name"]:
                continue
            status, text = self.api.call("GET", f"/apis/arrchitect.dev/v1alpha1/namespaces/{SANDBOX}/{resource['name']}")
            if status == 403:
                continue
            if status != 200 or json.loads(text)["items"]:
                return False
        return True

    def create_sandbox(self):
        labels = {
            "pod-security.kubernetes.io/enforce": "baseline",
            "pod-security.kubernetes.io/warn": "restricted",
            "pod-security.kubernetes.io/audit": "restricted",
        }
        self.api.json("POST", "/api/v1/namespaces",
                      {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SANDBOX, "labels": labels}})
        self.created = True
        wait_for(lambda: self.api.call("GET", f"/api/v1/namespaces/{SANDBOX}/serviceaccounts/default")[0] == 200,
                 120, "the sandbox's default ServiceAccount", 2)

    def run_restore(self):
        name = f"restore-test-{self.source}-{datetime.datetime.now(datetime.timezone.utc):%Y%m%d%H%M%S}"
        namespaces = {target["namespace"] for target in TARGETS}
        self.restore_started = time.time()
        self.api.json("POST", f"/apis/velero.io/v1/namespaces/{VELERO}/restores",
                      restore_body(name, self.schedule, namespaces))
        self.restore = name
        path = f"/apis/velero.io/v1/namespaces/{VELERO}/restores/{name}"

        def finished():
            current = self.api.json("GET", path)
            return current if current.get("status", {}).get("phase") in RESTORE_DONE else None

        restore = wait_for(finished, 1800, "the restore to finish", 10)
        status = restore.get("status", {})
        log(f"restore {name}: {status.get('phase')}, {status.get('errors', 0)} errors, {status.get('warnings', 0)} warnings")
        return restore

    def release_volumes(self):
        released = 0
        for volume in self.api.json("GET", "/api/v1/persistentvolumes")["items"]:
            spec = volume["spec"]
            if spec.get("storageClassName") != STORAGE_CLASS or spec.get("claimRef", {}).get("namespace") != SANDBOX:
                continue
            if spec.get("persistentVolumeReclaimPolicy") != "Delete":
                self.api.json("PATCH", f"/api/v1/persistentvolumes/{volume['metadata']['name']}",
                              {"spec": {"persistentVolumeReclaimPolicy": "Delete"}})
                released += 1
        return released

    def volume_restores(self):
        return self.api.json("GET", f"/apis/velero.io/v1/namespaces/{VELERO}/podvolumerestores",
                             query={"labelSelector": f"velero.io/restore-name={self.restore}"})["items"]

    def restored_volume(self, target, pods, volume_restores):
        for pod in pods:
            for volume in pod["spec"].get("volumes", []):
                if volume.get("persistentVolumeClaim", {}).get("claimName") != target["claim"]:
                    continue
                context = pod["spec"].get("securityContext", {})
                user = (context.get("runAsUser", 65534), context.get("runAsGroup", context.get("fsGroup", 65534)))
                for item in volume_restores:
                    if item["spec"]["pod"]["name"] == pod["metadata"]["name"] and item["spec"]["volume"] == volume["name"]:
                        status = item.get("status", {})
                        return status.get("phase"), status.get("progress", {}).get("totalBytes", 0), user
                return None, 0, user
        return None, 0, None

    def run_pod(self, pod, container, timeout):
        name = pod["metadata"]["name"]
        self.api.json("POST", f"/api/v1/namespaces/{SANDBOX}/pods", pod)
        path = f"/api/v1/namespaces/{SANDBOX}/pods/{name}"

        def finished():
            current = self.api.json("GET", path)
            if current.get("status", {}).get("phase") == "Failed":
                return current
            for status in current.get("status", {}).get("containerStatuses", []):
                if status["name"] == container and "terminated" in status.get("state", {}):
                    return current
            return None

        current = wait_for(finished, timeout, f"{name} to finish", 5)
        code = next((s["state"]["terminated"]["exitCode"] for s in current["status"].get("containerStatuses", [])
                     if s["name"] == container and "terminated" in s.get("state", {})), None)
        status, text = self.api.call("GET", f"{path}/log", query={"container": container})
        report = {}
        if status == 200 and text.strip():
            try:
                report = json.loads(text.strip().splitlines()[-1])
            except ValueError:
                report = {}
        return code == 0, report

    def check_image(self, target):
        source = target.get("image_from")
        if not source:
            return self.image
        cronjob = self.api.json("GET", f"/apis/batch/v1/namespaces/{source['namespace']}/cronjobs/{source['cronjob']}")
        spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        containers = spec.get("initContainers", []) + spec["containers"]
        return next(c["image"] for c in containers if c["name"] == source["container"])

    def check(self, target, user, backup_started):
        result = self.results[target["name"]]
        tiers = result["tiers"]
        pod = integrity_pod(target, self.check_image(target), user, self.scripts)
        intact, report = self.run_pod(pod, "check", 900)
        tiers["intact"] = intact
        result["rows"] = report.get("rows", {})
        for key in ("foreign_key_violations", "total_rows"):
            if key in report:
                result[key] = report[key]
        written = dump_time(report)
        result["dump_age"] = None if written is None else backup_started - written
        tiers["fresh"] = fresh(backup_started, written, time.time(), self.max_age, target["max_dump_age"])
        log(f"{target['name']}: intact={intact} fresh={tiers['fresh']} {json.dumps(report)}")
        if not intact or "app" not in target:
            return
        app = target["app"]
        deployment = self.api.json("GET", f"/apis/apps/v1/namespaces/{target['namespace']}/deployments/{app['deployment']}")
        key = secrets.token_hex(16)
        ran, report = self.run_pod(app_pod(target, deployment, self.image, user, key, self.scripts["check_api"]), "check", 900)
        tiers["usable"] = bool(report.get("started"))
        expected = result["rows"].get(app["count_table"])
        tiers["answers"] = ran and expected is not None and report.get("count") == expected
        log(f"{target['name']}: usable={tiers['usable']} answers={tiers['answers']} "
            f"count={report.get('count')} expected={expected} version={report.get('version')}")

    def push(self, name, result, now):
        url = f"{self.pushgateway}/metrics/job/restore_test/target/{name}/source/{self.source}"
        request = urllib.request.Request(url, data=metrics(result, now).encode(), method="POST")
        with urllib.request.urlopen(request, timeout=30):
            pass

    def cleanup(self):
        if self.keep:
            log("keeping the sandbox for inspection")
            return
        self.release_volumes()
        self.api.call("DELETE", f"/api/v1/namespaces/{SANDBOX}")
        wait_for(lambda: self.api.call("GET", f"/api/v1/namespaces/{SANDBOX}")[0] == 404, 900, "the sandbox to go", 10)
        if self.restore:
            self.api.call("DELETE", f"/apis/velero.io/v1/namespaces/{VELERO}/restores/{self.restore}")
        log("sandbox removed")

    def execute(self):
        try:
            if self.api.call("GET", f"/api/v1/namespaces/{SANDBOX}")[0] != 404:
                raise RuntimeError(f"{SANDBOX} already exists")
            wait_for(self.latest_finished, 2700, "the latest backup to finish", 30)
            self.create_sandbox()
            fences = self.fences()
            restore = self.run_restore()
            log(f"set {self.release_volumes()} restored volumes to be deleted with the sandbox")
            backup_name = restore["spec"].get("backupName") or self.newest_completed()
            backup = self.api.json("GET", f"/apis/velero.io/v1/namespaces/{VELERO}/backups/{backup_name}")
            backup_started = parse_time(backup["status"]["startTimestamp"])
            log(f"backup {backup_name}, {(time.time() - backup_started) / HOUR:.1f} hours old")
            fences["arrchitect_absent"] = self.arrchitect_absent()
            log(f"fences: {json.dumps(fences)}")
            status = restore.get("status", {})
            restore_clean = status.get("phase") == "Completed" and not status.get("errors")
            pods = self.api.json("GET", f"/api/v1/namespaces/{SANDBOX}/pods")["items"]
            volume_restores = self.volume_restores()
            for target in TARGETS:
                result = self.results[target["name"]]
                result["fences"] = dict(fences)
                result["data_age"] = time.time() - backup_started
                phase, size, user = self.restored_volume(target, pods, volume_restores)
                result["bytes"] = size
                result["tiers"]["restored"] = restore_clean and phase == "Completed" and size > 0
                log(f"{target['name']}: restored={result['tiers']['restored']} ({phase}, {size} bytes)")
                if result["tiers"]["restored"]:
                    try:
                        self.check(target, user, backup_started)
                    except Exception as error:
                        log(f"{target['name']}: check failed: {error}")
                        for tier in ("intact", "fresh"):
                            result["tiers"].setdefault(tier, False)
                        if "app" in target:
                            for tier in ("usable", "answers"):
                                result["tiers"].setdefault(tier, False)
                result["duration"] = time.time() - self.restore_started
        except Exception as error:
            log(f"run failed: {error}")
            for result in self.results.values():
                result["tiers"].setdefault("restored", False)
        finally:
            now = time.time()
            failures = 0
            for name, result in self.results.items():
                result.setdefault("duration", now - (self.restore_started or now))
                result["passed"] = passed(result)
                failures += not result["passed"]
                try:
                    self.push(name, result, now)
                except OSError as error:
                    log(f"{name}: could not push results: {error}")
                    failures += 1
                log(f"{name}: {'passed' if result['passed'] else 'FAILED'} {json.dumps(result['tiers'])}")
            if self.created:
                try:
                    self.cleanup()
                except Exception as error:
                    log(f"cleanup failed: {error}")
                    failures += 1
        return 1 if failures else 0


def main():
    return Run(Api(), os.environ).execute()


if __name__ == "__main__":
    sys.exit(main())
