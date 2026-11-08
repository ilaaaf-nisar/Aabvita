
import sqlite3

conn = sqlite3.connect("usda_nutrition.db")
conn.row_factory = sqlite3.Row

fdc_id = 2759004

query = """
SELECT
    n.id,
    n.name,
    n.unit_name,
    fn.amount
FROM food_nutrient fn
JOIN nutrient n
    ON fn.nutrient_id = n.id
WHERE fn.fdc_id = ?
ORDER BY n.id
"""

rows = conn.execute(query, (fdc_id,)).fetchall()

for row in rows:
    print(dict(row))

conn.close()
