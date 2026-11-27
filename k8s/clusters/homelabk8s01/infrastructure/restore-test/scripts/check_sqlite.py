import json
import os
import sqlite3
import sys


def check(path, required, reported, strict_foreign_keys):
    try:
        mtime = os.stat(path).st_mtime
        connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
        connection.close()
    except (OSError, sqlite3.Error) as error:
        return {"error": type(error).__name__}, False
    missing = [table for table in required if table not in counts]
    rows = {table: counts[table] for table in [*required, *reported] if table in counts}
    total = sum(counts.values())
    passed = (integrity == ["ok"] and not missing and total > 0
              and all(counts[table] > 0 for table in required)
              and (not strict_foreign_keys or not foreign))
    report = {"integrity": "ok" if integrity == ["ok"] else f"{len(integrity)} problems",
              "foreign_key_violations": len(foreign), "rows": rows, "total_rows": total, "mtime": mtime}
    if missing:
        report["missing_tables"] = missing
    return report, passed


def names(value):
    return [name for name in value.split(",") if name]


if __name__ == "__main__":
    report, passed = check(sys.argv[1], names(sys.argv[2]), names(sys.argv[3]), sys.argv[4] == "1")
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
