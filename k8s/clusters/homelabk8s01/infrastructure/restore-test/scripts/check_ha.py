import json
import pathlib
import sys
import tarfile


PAYLOADS = (".tar.gz", ".tgz", ".tar")


def decrypt(path, password):
    from securetar import SecureTarArchive

    payloads = entries = 0
    config_entries = False
    with SecureTarArchive(path, "r", password=password) as archive:
        for member in archive.tar.getmembers():
            if not member.name.endswith(PAYLOADS):
                continue
            with archive.extract_tar(member) as decrypted, tarfile.open(fileobj=decrypted, mode="r|*") as inner:
                for item in inner:
                    entries += 1
                    config_entries = config_entries or item.name.endswith(".storage/core.config_entries")
            payloads += 1
    return {"decrypted": payloads, "entries": entries, "config_entries": config_entries}


def check(directory, key_file=None):
    archives = sorted(pathlib.Path(directory).glob("*.tar"), key=lambda path: path.stat().st_mtime)
    if not archives:
        return {"archives": 0}, False
    newest = archives[-1]
    try:
        with tarfile.open(newest) as archive:
            members = archive.getmembers()
            for member in members:
                if member.isfile():
                    handle = archive.extractfile(member)
                    while handle.read(1 << 20):
                        pass
            name = next(n for n in archive.getnames() if n.removeprefix("./") == "backup.json")
            metadata = json.load(archive.extractfile(name))
    except (OSError, StopIteration, ValueError, tarfile.TarError) as error:
        return {"archives": len(archives), "error": type(error).__name__}, False
    payloads = [m.name for m in members if m.name.endswith(PAYLOADS)]
    protected = metadata.get("protected") is True
    report = {"archives": len(archives), "members": len(members), "payloads": len(payloads),
              "protected": protected, "timestamp": metadata.get("date")}
    passed = protected and bool(payloads) and bool(metadata.get("date"))
    if key_file is None:
        return report, passed
    try:
        report.update(decrypt(newest, pathlib.Path(key_file).read_text().strip()))
    except Exception as error:
        return {**report, "decrypt_error": type(error).__name__}, False
    return report, passed and report["decrypted"] == len(payloads) and report["config_entries"]


if __name__ == "__main__":
    report, passed = check(*sys.argv[1:3])
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
