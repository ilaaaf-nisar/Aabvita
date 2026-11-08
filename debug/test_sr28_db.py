import sqlite3

conn = sqlite3.connect("databases/usda_sr28.db")

rows = conn.execute("""
    SELECT
        f.long_desc,
        n.nutrdesc,
        d.nutr_val,
        n.units
    FROM FOOD_DES f
    JOIN NUT_DATA d ON f.ndb_no = d.ndb_no
    JOIN NUTR_DEF n ON d.nutr_no = n.nutr_no
    WHERE f.ndb_no = '01009'
      AND d.nutr_no IN ('203', '208')
""").fetchall()

for row in rows:
    print(row)

conn.close()