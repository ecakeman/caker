import sqlite3
import sys

def main() -> None:
    if len(sys.argv) < 3:
        print("usage: query.py <db_path> <sql>", file=sys.stderr)
        sys.exit(2)
    db_path, sql = sys.argv[1], sys.argv[2]
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(sql)
        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            for row in rows[:200]:
                print(row)
            if len(rows) > 200:
                print(f"... ({len(rows)} rows total, truncated)")
        else:
            conn.commit()
            print("ok", cur.rowcount)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
