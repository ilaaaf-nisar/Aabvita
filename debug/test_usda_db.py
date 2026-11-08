import sqlite3

conn = sqlite3.connect("databases/usda_nutrition.db")
conn.row_factory = sqlite3.Row

query = """
SELECT
    f.fdc_id,
    f.description,
    f.data_type,
    n.name AS nutrient,
    fn.amount,
    n.unit_name
FROM food AS f
JOIN food_nutrient AS fn
    ON f.fdc_id = fn.fdc_id
JOIN nutrient AS n
    ON fn.nutrient_id = n.id
WHERE f.description LIKE ?
  AND n.name IN (
      'Protein',
      'Total lipid (fat)',
      'Carbohydrate, by difference',
      'Energy'
  )
ORDER BY f.fdc_id, n.name
LIMIT 30
"""

rows = conn.execute(query, ("%chicken breast%",))

for row in rows:
    print(dict(row))

conn.close()
