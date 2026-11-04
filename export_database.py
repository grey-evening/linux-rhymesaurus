import os
import sqlite3
import fdb

SOURCE = os.path.abspath("Rhymesaurus-original.fdb")
DESTINATION = os.path.abspath("rhymesaurus.sqlite3")

FBROOT = os.environ["FBROOT"]
FB_LIBRARY = os.path.join(FBROOT, "lib", "libfbembed.so.2.5.9")

TABLES = [
    "DICTIONARY",
    "IDIOMS",
    "RHYMES",
    "RHYMESLO",
    "THESAURUS",
]

def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'

print("Connecting to Firebird...")
fb = fdb.connect(
    dsn=SOURCE,
    user="SYSDBA",
    password="masterkey",
    charset="WIN1251",
    fb_library_name=FB_LIBRARY
)

print("Creating SQLite database...")
if os.path.exists(DESTINATION):
    os.remove(DESTINATION)

sql = sqlite3.connect(DESTINATION)
sql.execute("PRAGMA journal_mode=WAL")
sql.execute("PRAGMA synchronous=NORMAL")

for table in TABLES:
    print(f"\nExporting {table}...")

    source_cursor = fb.cursor()
    source_cursor.execute(f"SELECT * FROM {table}")

    columns = [description[0] for description in source_cursor.description]
    quoted_columns = ", ".join(quote_identifier(c) for c in columns)

    sql.execute(
        f"CREATE TABLE {quote_identifier(table)} "
        f"({quoted_columns})"
    )

    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f"INSERT INTO {quote_identifier(table)} "
        f"({quoted_columns}) VALUES ({placeholders})"
    )

    total = 0

    while True:
        rows = source_cursor.fetchmany(5000)
        if not rows:
            break

        sql.executemany(insert_sql, rows)
        total += len(rows)
        print(f"  {total:,} records copied", end="\r")

    sql.commit()
    source_cursor.close()
    print(f"  Finished: {total:,} records")

fb.close()

print("\nChecking SQLite database...")
for table in TABLES:
    count = sql.execute(
        f"SELECT COUNT(*) FROM {quote_identifier(table)}"
    ).fetchone()[0]
    print(f"  {table}: {count:,} records")

print("\nIntegrity check:")
print(sql.execute("PRAGMA integrity_check").fetchone()[0])

sql.close()
print(f"\nExport complete: {DESTINATION}")
