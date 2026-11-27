import json
import pathlib
import sys
import tarfile


def check(directory):
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
    payloads = [m.name for m in members if m.name.endswith((".tar.gz", ".tar"))]
    protected = metadata.get("protected") is True
    report = {"archives": len(archives), "members": len(members), "payloads": len(payloads),
              "protected": protected, "timestamp": metadata.get("date")}
    return report, protected and bool(payloads) and bool(metadata.get("date"))


if __name__ == "__main__":
    report, passed = check(sys.argv[1])
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
