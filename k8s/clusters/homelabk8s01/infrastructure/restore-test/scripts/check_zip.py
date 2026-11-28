from contextlib import closing
import json
import os
import shutil
import sqlite3
import sys
import zipfile


def check(path, inner, workdir, reported=()):
    try:
        mtime = os.stat(path).st_mtime
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            entries = len(archive.namelist())
            if bad is not None:
                return {"entries": entries, "bad_member": True, "mtime": mtime}, False
            if inner not in archive.namelist():
                return {"entries": entries, "inner_missing": True, "mtime": mtime}, False
            extracted = os.path.join(workdir, "inner.db")
            with archive.open(inner) as source, open(extracted, "wb") as target:
                shutil.copyfileobj(source, target)
        with closing(sqlite3.connect(f"file:{extracted}?mode=ro&immutable=1", uri=True)) as connection:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            rows = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in reported}
    except (OSError, zipfile.BadZipFile, sqlite3.Error) as error:
        return {"error": type(error).__name__}, False
    passed = integrity == ["ok"]
    return {"entries": entries, "inner_integrity": "ok" if passed else f"{len(integrity)} problems",
            "rows": rows, "mtime": mtime}, passed


if __name__ == "__main__":
    report, passed = check(sys.argv[1], sys.argv[2], sys.argv[3], list(filter(None, sys.argv[4].split(","))))
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
