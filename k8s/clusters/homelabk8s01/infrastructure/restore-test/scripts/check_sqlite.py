import json
import sqlite3
import sys


def check(path, tables):
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        rows = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
        connection.close()
    except sqlite3.Error as error:
        return {"error": type(error).__name__}, False
    passed = integrity == ["ok"] and not foreign and all(count > 0 for count in rows.values())
    return {"integrity": "ok" if integrity == ["ok"] else f"{len(integrity)} problems",
            "foreign_key_violations": len(foreign), "rows": rows}, passed


if __name__ == "__main__":
    report, passed = check(sys.argv[1], sys.argv[2:])
    print(json.dumps(report))
    sys.exit(0 if passed else 1)
