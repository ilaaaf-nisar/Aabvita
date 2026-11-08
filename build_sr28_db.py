#!/usr/bin/env python3
"""Import USDA Standard Reference 28 ASCII (~quoted, ^ delimited) files to SQLite.

Usage:
    python build_sr28_db.py
"""
import csv
import sqlite3
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "sr28"
DB_PATH = PROJECT_ROOT / "databases" / "usda_sr28.db"
BATCH_SIZE = 10_000

FILES = {
    "FOOD_DES": "FOOD_DES.txt",
    "FD_GROUP": "FD_GROUP.txt",
    "NUT_DATA": "NUT_DATA.txt",
    "NUTR_DEF": "NUTR_DEF.txt",
    "WEIGHT": "WEIGHT.txt",
    "FOOTNOTE": "FOOTNOTE.txt",
    "DERIV_CD": "DERIV_CD.txt",
    "SRC_CD": "SRC_CD.txt",
    "LANGUAL": "LANGUAL.txt",
    "LANGDESC": "LANGDESC.txt",
    "DATA_SRC": "DATA_SRC.txt",
    "DATSRCLN": "DATSRCLN.txt",
}

# USDA SR28 ASCII field positions (official release layout). All values are
# stored as TEXT to preserve zero-padded NDB numbers and source notation.
SCHEMAS = {
    "FOOD_DES": ["ndb_no", "fdgrp_cd", "long_desc", "shrt_desc", "comname", "manufacname", "survey", "ref_desc", "refuse", "sciname", "n_factor", "pro_factor", "fat_factor", "cho_factor"],
    "FD_GROUP": ["fdgrp_cd", "fdgrp_desc"],
    "NUT_DATA": ["ndb_no", "nutr_no", "nutr_val", "num_data_pts", "std_error", "src_cd", "deriv_cd", "ref_ndb_no", "add_nutr_mark", "num_studies", "min", "max", "df", "low_eb", "up_eb", "stat_cmt", "addmod_date"],
    "NUTR_DEF": ["nutr_no", "units", "tagname", "nutrdesc", "num_dec", "sr_order"],
    "WEIGHT": ["ndb_no", "seq", "amount", "msre_desc", "gm_wgt", "num_data_pts", "std_dev"],
    "FOOTNOTE": ["ndb_no", "footnt_no", "footnt_typ", "nutr_no", "footnt_txt"],
    "DERIV_CD": ["deriv_cd", "deriv_desc"],
    "SRC_CD": ["src_cd", "src_desc"],
    "LANGUAL": ["ndb_no", "factor_code"],
    "LANGDESC": ["factor_code", "description"],
    "DATA_SRC": ["datasrc_id", "authors", "title", "year", "journal", "vol_city", "issue_state", "start_page", "end_page"],
    "DATSRCLN": ["ndb_no", "nutr_no", "datasrc_id"],
}

INDEXES = {
    "FOOD_DES": [("ndb_no",), ("long_desc",)],
    "NUT_DATA": [("ndb_no", "nutr_no"), ("nutr_no",)],
    "NUTR_DEF": [("nutr_no",)],
    "WEIGHT": [("ndb_no",)],
    "FD_GROUP": [("fdgrp_cd",)],
    "FOOTNOTE": [("ndb_no",)],
    "DATSRCLN": [("ndb_no", "nutr_no")],
    "DATA_SRC": [("datasrc_id",)],
    "DERIV_CD": [("deriv_cd",)],
    "SRC_CD": [("src_cd",)],
    "LANGUAL": [("ndb_no",)],
    "LANGDESC": [("factor_code",)],
}


def quote_ident(s):
    return '"' + s.replace('"', '""') + '"'


def import_table(conn, table, filename):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  {table:<11} not found (optional; skipped)")
        return 0

    columns = SCHEMAS[table]
    expected = len(columns)

    print(f"\nImporting {filename}...")
    start = time.time()

    conn.execute(f'DROP TABLE IF EXISTS {quote_ident(table)}')
    conn.execute(
        f'CREATE TABLE {quote_ident(table)} (' +
        ', '.join(f'{quote_ident(c)} TEXT' for c in columns) + ')'
    )

    insert_sql = (
        f'INSERT INTO {quote_ident(table)} VALUES (' +
        ','.join('?' for _ in columns) + ')'
    )

    batch = []
    total = 0

    with path.open('r', encoding='latin-1', newline='') as fh:
        reader = csv.reader(fh, delimiter='^', quotechar='~', doublequote=True)
        for line_number, row in enumerate(reader, 1):
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            # The USDA ASCII release typically terminates each line with a ^.
            if len(row) == expected + 1 and row[-1] == '':
                row.pop()
            if len(row) != expected:
                raise ValueError(
                    f'{path.name} line {line_number}: expected {expected} '
                    f'fields, got {len(row)}. First fields: {row[:4]!r}'
                )
            
            values = [None if x == '' else x for x in row]
            batch.append(tuple(values))

            if len(batch) >= BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                conn.commit()
                total += len(batch)
                batch.clear()

                if total % 100_000 == 0:
                    print(f"  {total:,} rows imported")

        if batch:
            conn.executemany(insert_sql, batch)
            conn.commit()
            total += len(batch)

    print(f"Completed: {total:,} rows in {time.time() - start:.1f}s")
    return total


def main():
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"Source directory not found: {DATA_DIR}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Source: {DATA_DIR}\nDatabase: {DB_PATH}\n")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        counts = {}
        for table, filename in FILES.items():
            count = import_table(conn, table, filename)
            if count > 0:
                counts[table] = count

        print("\nCreating indexes...")
        for table, keys in INDEXES.items():
            if table not in counts:
                continue
            for cols in keys:
                index_name = 'idx_' + table.lower() + '_' + '_'.join(cols)
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS {quote_ident(index_name)} '
                    f'ON {quote_ident(table)} (' +
                    ', '.join(quote_ident(c) for c in cols) + ')'
                )

        conn.execute('CREATE TABLE IF NOT EXISTS import_info (key TEXT PRIMARY KEY, value TEXT)')
        conn.execute("INSERT OR REPLACE INTO import_info VALUES ('dataset', 'USDA Standard Reference 28 (SR28)')")
        conn.execute("INSERT OR REPLACE INTO import_info VALUES ('source_directory', ?)", (str(DATA_DIR),))
        conn.commit()

        print("\nValidation:")
        try:
            example = conn.execute('''
                SELECT f.ndb_no, f.long_desc, n.nutrdesc, d.nutr_val, n.units
                FROM FOOD_DES f
                JOIN NUT_DATA d ON d.ndb_no = f.ndb_no
                JOIN NUTR_DEF n ON n.nutr_no = d.nutr_no
                WHERE f.ndb_no = '01009' AND d.nutr_no IN ('203','208')
                ORDER BY d.nutr_no
            ''').fetchall()
            for record in example:
                print('  ', record)
        except Exception:
            pass

        print("\nDatabase summary:")
        for table in counts:
            count = conn.execute(f'SELECT COUNT(*) FROM {quote_ident(table)}').fetchone()[0]
            print(f"  {table:<11}: {count:,} rows")

    print(f"\nDatabase created: {DB_PATH.resolve()}")
    print("NOTE: SR28 NDB numbers are NOT FoodData Central fdc_id values.")


if __name__ == '__main__':
    main()