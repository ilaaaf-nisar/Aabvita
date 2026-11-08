
import argparse
import csv
import sqlite3
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "Food_Data"
DB_PATH = PROJECT_ROOT / "databases" / "usda_nutrition.db"
BATCH_SIZE = 10_000

FILES = {
    "food": "food.csv",
    "food_nutrient": "food_nutrient.csv",
    "nutrient": "nutrient.csv",
    "food_category": "food_category.csv",
    "food_portion": "food_portion.csv",
    "measure_unit": "measure_unit.csv",
}

# Preserve food category IDs as text.
# Convert other known numerical columns to SQL types.
INTEGER_COLUMNS = {
    "fdc_id", "nutrient_id", "measure_unit_id",
    "id", "seq_num", "data_points",
    "derivation_id", "min_year_acquired",
}

REAL_COLUMNS = {
    "amount", "gram_weight", "min", "max",
    "median", "loq", "percent_daily_value",
    "rank",
}
BRANDED_COLUMNS = (
    "fdc_id",
    "brand_owner",
    "brand_name",
    "gtin_upc",
    "serving_size",
    "serving_size_unit",
    "household_serving_fulltext",
    "short_description",
)


def get_column_type(column):
    if column in INTEGER_COLUMNS:
        return "INTEGER"
    if column in REAL_COLUMNS:
        return "REAL"
    return "TEXT"


def import_csv(conn, table, filename):
    path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(path)

    print(f"\nImporting {filename}...")
    start = time.time()

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames

        if not columns:
            raise ValueError(f"No columns in {filename}")

        definitions = ", ".join(
            f'"{col}" {get_column_type(col)}'
            for col in columns
        )

        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(
            f'CREATE TABLE "{table}" ({definitions})'
        )

        names = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join("?" for _ in columns)

        sql = (
            f'INSERT INTO "{table}" ({names}) '
            f'VALUES ({placeholders})'
        )

        batch = []
        total = 0

        for row in reader:
            values = [
                None if row[col] in ("", None)
                else row[col]
                for col in columns
            ]

            batch.append(values)

            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                conn.commit()

                total += len(batch)
                batch.clear()

                if total % 100_000 == 0:
                    print(f"  {total:,} rows imported")

        if batch:
            conn.executemany(sql, batch)
            conn.commit()
            total += len(batch)

    print(
        f"Completed: {total:,} rows "
        f"in {time.time() - start:.1f}s"
    )


def import_branded_food(conn):
    """Replace only the branded metadata table, leaving core food data intact."""
    path = DATA_DIR / "branded_food.csv"
    if not path.exists():
        raise FileNotFoundError(path)

    print(f"\nImporting {path.name}...")
    start = time.time()
    definitions = """
        fdc_id INTEGER PRIMARY KEY,
        brand_owner TEXT,
        brand_name TEXT,
        gtin_upc TEXT,
        serving_size REAL,
        serving_size_unit TEXT,
        household_serving_fulltext TEXT,
        short_description TEXT
    """
    columns = ", ".join(f'"{column}"' for column in BRANDED_COLUMNS)
    placeholders = ", ".join("?" for _ in BRANDED_COLUMNS)
    sql = f'INSERT INTO branded_food ({columns}) VALUES ({placeholders})'

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = {"fdc_id"} - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing required branded-food columns: {sorted(missing)}")

        with conn:
            conn.execute("DROP TABLE IF EXISTS branded_food")
            conn.execute(f"CREATE TABLE branded_food ({definitions})")
            batch = []
            total = 0
            for row in reader:
                serving_size = row.get("serving_size") or None
                try:
                    serving_size = float(serving_size) if serving_size else None
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid serving_size for FDC ID {row.get('fdc_id')}: "
                        f"{serving_size!r}"
                    ) from exc
                fdc_id = row.get("fdc_id")
                if not fdc_id:
                    continue
                batch.append((
                    int(fdc_id),
                    row.get("brand_owner") or None,
                    row.get("brand_name") or None,
                    row.get("gtin_upc") or None,
                    serving_size,
                    row.get("serving_size_unit") or None,
                    row.get("household_serving_fulltext") or None,
                    row.get("short_description") or None,
                ))
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(sql, batch)
                    total += len(batch)
                    batch.clear()
                    if total % 100_000 == 0:
                        print(f"  {total:,} rows imported")
            if batch:
                conn.executemany(sql, batch)
                total += len(batch)
            conn.execute(
                "CREATE INDEX idx_branded_food_gtin_upc "
                "ON branded_food(gtin_upc)"
            )
            conn.execute(
                "CREATE INDEX idx_branded_food_brand_name "
                "ON branded_food(brand_name COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX idx_branded_food_brand_owner "
                "ON branded_food(brand_owner COLLATE NOCASE)"
            )

    print(f"Completed: {total:,} rows in {time.time() - start:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Build the USDA nutrition database.")
    parser.add_argument(
        "--branded-only",
        action="store_true",
        help="Import branded metadata without rebuilding the other USDA tables.",
    )
    args = parser.parse_args()

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(DATA_DIR)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        if args.branded_only:
            import_branded_food(conn)
        else:
            for table, filename in FILES.items():
                import_csv(conn, table, filename)
            import_branded_food(conn)

        if not args.branded_only:
            print("\nCreating indexes...")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_food_fdc "
                "ON food(fdc_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_food_description "
                "ON food(description COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_food_nutrient_fdc "
                "ON food_nutrient(fdc_id, nutrient_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nutrient_id "
                "ON nutrient(id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_portion_fdc "
                "ON food_portion(fdc_id)"
            )

        conn.commit()

        if args.branded_only:
            count = conn.execute(
                "SELECT COUNT(*) FROM branded_food"
            ).fetchone()[0]
            print(f"branded_food: {count:,} rows")
        else:
            print("\nDatabase summary:")
            for table in (*FILES, "branded_food"):
                count = conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                print(f"{table}: {count:,} rows")

    print(f"\nDatabase created: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()
