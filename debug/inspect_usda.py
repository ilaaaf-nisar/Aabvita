
import csv
from pathlib import Path

# Change this to your USDA CSV directory
DATA_DIR = Path(r"C:\Users\ilaf0\Downloads\My_Coach\data\Food_Data")

files = [
    "food.csv",
    "food_nutrient.csv",
    "nutrient.csv",
    "food_category.csv",
    "food_portion.csv",
    "measure_unit.csv",
]

for filename in files:
    path = DATA_DIR / filename

    print(f"\n{'=' * 60}")
    print(f"FILE: {filename}")

    if not path.exists():
        print("File not found")
        continue

    print(f"Size: {path.stat().st_size / (1024**2):.2f} MB")

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        print("Columns:", reader.fieldnames)

        for i, row in enumerate(reader):
            if i == 2:
                break
            print(f"Sample {i + 1}:", row)
