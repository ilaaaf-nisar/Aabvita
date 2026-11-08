
import math
import re
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "usda_nutrition.db"
SR28_DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "usda_sr28.db"
STANDARD_FOOD_TYPES = (
    "foundation_food",
    "sr_legacy_food",
    "survey_fndds_food",
)


class NutritionTool:

    def __init__(self, db_path=DB_PATH, sr28_db_path=SR28_DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.sr28_db_path = sr28_db_path
        self.sr28_conn = None
        if sr28_db_path is not None and Path(sr28_db_path).is_file():
            self.sr28_conn = sqlite3.connect(sr28_db_path)
            self.sr28_conn.row_factory = sqlite3.Row

    def search_food(self, name, limit=15):
        name = name.strip()
    
        if not name:
            return []

        # Escape LIKE wildcards in user input
        escaped = (
            name.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
        )

        has_branded_data = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'branded_food'"
        ).fetchone()
        if has_branded_data:
            if re.fullmatch(r"\d{8,14}", name):
                rows = self.conn.execute(
                    """
                    SELECT f.fdc_id, f.description, f.data_type,
                           b.brand_name, b.brand_owner, b.gtin_upc,
                           b.serving_size, b.serving_size_unit,
                           b.household_serving_fulltext
                    FROM branded_food AS b
                    JOIN food AS f ON f.fdc_id = b.fdc_id
                    WHERE b.gtin_upc = ?
                    LIMIT ?
                    """,
                    (name, limit),
                ).fetchall()
                if rows:
                    return [dict(row) for row in rows]
            match_filter = """(
                f.description LIKE ? ESCAPE '\\'
                OR b.brand_name LIKE ? ESCAPE '\\'
                OR b.brand_owner LIKE ? ESCAPE '\\'
                OR b.gtin_upc = ?
            ) AND f.data_type IN (?, ?, ?, 'branded_food')"""
            filter_parameters = (
                f"%{escaped}%", f"%{escaped}%", f"%{escaped}%", name,
                *STANDARD_FOOD_TYPES,
            )
            category_count = self.conn.execute(
                f"""
                SELECT COUNT(DISTINCT
                    CASE WHEN f.data_type = 'branded_food'
                         THEN 'branded' ELSE 'standard' END
                )
                FROM food AS f
                LEFT JOIN branded_food AS b ON b.fdc_id = f.fdc_id
                WHERE {match_filter}
                """,
                filter_parameters,
            ).fetchone()[0]
            branded_limit = max(1, limit // 3) if category_count > 1 else limit
            standard_limit = limit - branded_limit if category_count > 1 else limit
            query = f"""
            WITH matched AS (
                SELECT f.fdc_id, f.description, f.data_type,
                       b.brand_name, b.brand_owner, b.gtin_upc,
                       b.serving_size, b.serving_size_unit,
                       b.household_serving_fulltext,
                       CASE
                           WHEN b.gtin_upc = ? THEN 0
                           WHEN LOWER(b.brand_name) = LOWER(?)
                             OR LOWER(b.brand_owner) = LOWER(?) THEN 1
                           ELSE 2
                       END AS brand_priority,
                       CASE
                           WHEN LOWER(f.description) = LOWER(?) THEN 0
                           WHEN LOWER(f.description) LIKE LOWER(?) ESCAPE '\\' THEN 1
                           ELSE 2
                       END AS description_priority
                FROM food AS f
                LEFT JOIN branded_food AS b ON b.fdc_id = f.fdc_id
                WHERE {match_filter}
            ), ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY data_type = 'branded_food'
                           ORDER BY brand_priority, description_priority,
                                    LENGTH(description), description
                       ) AS category_rank
                FROM matched
            )
            SELECT fdc_id, description, data_type, brand_name, brand_owner,
                   gtin_upc, serving_size, serving_size_unit,
                   household_serving_fulltext
            FROM ranked
            WHERE (data_type = 'branded_food' AND category_rank <= ?)
               OR (data_type != 'branded_food' AND category_rank <= ?)
            ORDER BY data_type = 'branded_food', brand_priority,
                     description_priority, LENGTH(description), description
            LIMIT ?
            """
            rows = self.conn.execute(
                query,
                (
                    name, name, name, name, f"{escaped}%",
                    *filter_parameters,
                    branded_limit, standard_limit, limit,
                ),
            ).fetchall()
        else:
            placeholders = ", ".join("?" for _ in STANDARD_FOOD_TYPES)
            query = f"""
            SELECT fdc_id, description, data_type,
                   NULL AS brand_name, NULL AS brand_owner, NULL AS gtin_upc,
                   NULL AS serving_size, NULL AS serving_size_unit,
                   NULL AS household_serving_fulltext
            FROM food
            WHERE description LIKE ? ESCAPE '\\'
              AND data_type IN ({placeholders})
            ORDER BY
                CASE
                    WHEN LOWER(description) = LOWER(?) THEN 0
                    WHEN LOWER(description) LIKE LOWER(?) ESCAPE '\\' THEN 1
                    WHEN LOWER(description) LIKE LOWER(?) ESCAPE '\\' THEN 2
                    ELSE 3
                END,
                CASE data_type
                    WHEN 'foundation_food' THEN 0
                    WHEN 'sr_legacy_food' THEN 1
                    ELSE 2
                END,
                LENGTH(description),
                description
            LIMIT ?
            """
            rows = self.conn.execute(
                query,
                (
                    f"%{escaped}%", *STANDARD_FOOD_TYPES,
                    name, f"{escaped},%", f"{escaped} %", limit,
                ),
            ).fetchall()

        matches = [dict(row) for row in rows]
        if matches or self.sr28_conn is None:
            return matches

        legacy_query = """
        SELECT f.ndb_no, f.long_desc AS description,
               g.fdgrp_desc AS food_group
        FROM FOOD_DES AS f
        LEFT JOIN FD_GROUP AS g ON g.fdgrp_cd = f.fdgrp_cd
        WHERE f.long_desc LIKE ? ESCAPE '\\'
        ORDER BY
            CASE
                WHEN LOWER(f.long_desc) = LOWER(?) THEN 0
                WHEN LOWER(f.long_desc) LIKE LOWER(?) ESCAPE '\\' THEN 1
                WHEN LOWER(f.long_desc) LIKE LOWER(?) ESCAPE '\\' THEN 2
                ELSE 3
            END,
            LENGTH(f.long_desc),
            f.long_desc
        LIMIT ?
        """
        legacy_rows = self.sr28_conn.execute(
            legacy_query,
            (f"%{escaped}%", name, f"{escaped},%", f"{escaped} %", limit),
        ).fetchall()
        return [
            {
                "ndb_no": row["ndb_no"],
                "description": row["description"],
                "food_group": row["food_group"],
                "source": "sr28",
            }
            for row in legacy_rows
        ]

    def get_nutrition(self, fdc_id, grams=100):
        if grams <= 0:
            raise ValueError("grams must be positive")

        query = """
        SELECT
            n.id AS nutrient_id,
            n.name,
          n.unit_name,
          fn.amount
      FROM food_nutrient AS fn
      JOIN nutrient AS n
         ON fn.nutrient_id = n.id
        WHERE fn.fdc_id = ?
         AND n.id IN (1003, 1004, 1005, 1008, 2047, 2048)
     """

        rows = self.conn.execute(
           query, (fdc_id,)
        ).fetchall()

        nutrient_map = {
            1003: "protein_g",
            1004: "fat_g",
            1005: "carbohydrates_g"
        }

        nutrients = {
            "protein_g": None,
            "fat_g": None,
            "carbohydrates_g": None,
            "calories_kcal": None
        }

        energy_candidates = {}

        # print("\nDEBUG: Retrieved nutrient rows")

        for row in rows:
            nutrient_id = int(row["nutrient_id"])
            amount = row["amount"]

            # print(
            #     f"ID={nutrient_id}, "
            #     f"Name={row['name']}, "
            #     f"Amount={amount}"
            # )

            if amount is None:
                continue

            amount = float(amount)

            if nutrient_id in nutrient_map:
                key = nutrient_map[nutrient_id]
                nutrients[key] = round(
                    amount * grams / 100, 2
                )

            elif nutrient_id in (1008, 2047, 2048):
                if row["unit_name"].upper() == "KCAL":
                    energy_candidates[nutrient_id] = amount

        energy_id = next(
            (
                nutrient_id
                for nutrient_id in (2048, 2047, 1008)
                if nutrient_id in energy_candidates
            ),
            None
        )

        if energy_id is not None:
            nutrients["calories_kcal"] = round(
                energy_candidates[energy_id] * grams / 100,
                2
            )

        return {
            "fdc_id": fdc_id,
            "serving_grams": grams,
            "nutrients": nutrients,
            "energy_source_nutrient_id": energy_id
        }

    def get_sr28_nutrition(self, ndb_no, grams=100):
        if grams <= 0:
            raise ValueError("grams must be positive")
        if self.sr28_conn is None:
            raise FileNotFoundError(
                f"SR28 database not found: {self.sr28_db_path}"
            )
        ndb_no = self._normalize_ndb_no(ndb_no)
        rows = self.sr28_conn.execute(
            """
            SELECT d.nutr_no, d.nutr_val
            FROM NUT_DATA AS d
            WHERE d.ndb_no = ? AND d.nutr_no IN ('203', '204', '205', '208')
            """,
            (ndb_no,),
        ).fetchall()
        nutrient_map = {
            "203": "protein_g",
            "204": "fat_g",
            "205": "carbohydrates_g",
            "208": "calories_kcal",
        }
        nutrients = {key: None for key in nutrient_map.values()}
        for row in rows:
            value = row["nutr_val"]
            if value is not None:
                nutrients[nutrient_map[row["nutr_no"]]] = round(
                    float(value) * grams / 100, 2
                )
        return {
            "ndb_no": ndb_no,
            "source": "sr28",
            "serving_grams": grams,
            "nutrients": nutrients,
            "energy_source_nutrient_id": 208 if nutrients["calories_kcal"] is not None else None,
        }

    @staticmethod
    def _normalize_ndb_no(ndb_no):
        value = str(ndb_no).strip()
        if not re.fullmatch(r"\d{1,5}", value):
            raise ValueError("SR28 NDB number must contain one to five digits")
        return value.zfill(5)

    def get_portions(self, fdc_id, *, source="fdc"):
        """Return USDA household portions that have a usable gram weight."""
        if source == "sr28":
            if self.sr28_conn is None:
                raise FileNotFoundError(
                    f"SR28 database not found: {self.sr28_db_path}"
                )
            ndb_no = self._normalize_ndb_no(fdc_id)
            rows = self.sr28_conn.execute(
                """
                SELECT amount, msre_desc, gm_wgt
                FROM WEIGHT
                WHERE ndb_no = ?
                ORDER BY CAST(seq AS INTEGER)
                """,
                (ndb_no,),
            ).fetchall()
            portions = []
            seen = set()
            for row in rows:
                try:
                    amount = float(row["amount"] or 1)
                    grams = float(row["gm_wgt"])
                except (TypeError, ValueError):
                    continue
                if (amount <= 0 or grams <= 0
                        or not math.isfinite(amount) or not math.isfinite(grams)):
                    continue
                label = (row["msre_desc"] or "serving").strip()
                key = (label.casefold(), grams)
                if key not in seen:
                    portions.append({
                        "label": label,
                        "amount": amount,
                        "measure_unit": None,
                        "portion_description": label,
                        "modifier": None,
                        "gram_weight": grams,
                        "grams_per_unit": grams / amount,
                        "source": "sr28",
                    })
                    seen.add(key)
            return portions
        if source != "fdc":
            raise ValueError(f"Unsupported nutrition data source: {source}")
        rows = self.conn.execute(
            """
            SELECT fp.amount, mu.name AS measure_unit,
                   fp.portion_description, fp.modifier, fp.gram_weight
            FROM food_portion AS fp
            LEFT JOIN measure_unit AS mu ON mu.id = fp.measure_unit_id
            WHERE fp.fdc_id = ? AND fp.gram_weight > 0
            ORDER BY fp.seq_num, fp.id
            """,
            (fdc_id,),
        ).fetchall()
        portions = []
        seen = set()
        for row in rows:
            amount = float(row["amount"] or 1)
            grams = float(row["gram_weight"])
            if amount <= 0 or not math.isfinite(amount) or not math.isfinite(grams):
                continue
            unit = row["measure_unit"] or ""
            details = row["modifier"] or row["portion_description"] or ""
            label_parts = []
            if unit.casefold() != "undetermined":
                label_parts.append(f"{amount:g} {unit}")
            if details and details.casefold() not in {
                part.casefold() for part in label_parts
            }:
                label_parts.append(details.strip())
            label = " ".join(label_parts) or "serving"
            key = (label.casefold(), grams)
            if key not in seen:
                portions.append({
                    "label": label,
                    "amount": amount,
                    "measure_unit": unit,
                    "portion_description": row["portion_description"],
                    "modifier": row["modifier"],
                    "gram_weight": grams,
                    "grams_per_unit": grams / amount if amount else grams,
                    "source": "food_portion",
                })
                seen.add(key)

        has_branded_data = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'branded_food'"
        ).fetchone()
        if has_branded_data:
            row = self.conn.execute(
                """
                SELECT serving_size, serving_size_unit, household_serving_fulltext
                FROM branded_food WHERE fdc_id = ?
                """,
                (fdc_id,),
            ).fetchone()
            if row and row["serving_size"] and row["serving_size_unit"]:
                unit = row["serving_size_unit"].strip().casefold()
                grams = float(row["serving_size"])
                if unit in {"g", "gram", "grams"} and math.isfinite(grams) and grams > 0:
                    label = (row["household_serving_fulltext"] or
                             f"{grams:g} g serving").strip()
                    key = (label.casefold(), grams)
                    if key not in seen:
                        portions.append({
                            "label": label,
                            "amount": 1.0,
                            "measure_unit": "serving",
                            "portion_description": label,
                            "modifier": None,
                            "gram_weight": grams,
                            "grams_per_unit": grams,
                            "source": "branded_food",
                        })
        return portions

    def resolve_portion_grams(self, fdc_id, portion, *, source="fdc"):
        """Resolve a requested USDA portion and quantity to grams."""
        requested = str(portion).strip()
        if not requested:
            raise ValueError("portion must not be empty")
        portions = self.get_portions(fdc_id, source=source)
        if not portions:
            identifier = "NDB number" if source == "sr28" else "FDC ID"
            raise ValueError(
                f"No gram-based household portions are available for "
                f"{identifier} {fdc_id}"
            )

        weight_match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(g|grams?|kg|kilograms?)", requested, re.I
        )
        if weight_match:
            grams = float(weight_match.group(1))
            if weight_match.group(2).casefold().startswith("k"):
                grams *= 1000
            if not math.isfinite(grams) or not 0 < grams <= 100000:
                raise ValueError("serving weight must be between 0 and 100000 grams")
            return grams, f"{grams:g} g"

        index_match = re.fullmatch(r"(?:option\s*)?(\d+)", requested, re.I)
        if index_match:
            index = int(index_match.group(1)) - 1
            if 0 <= index < len(portions):
                selected = portions[index]
                return selected["gram_weight"], selected["label"]
            if index >= len(portions):
                grams = float(index_match.group(1))
                if grams <= 100000:
                    return grams, f"{grams:g} g"
                raise ValueError("serving weight must not exceed 100000 grams")

        quantity_match = re.fullmatch(
            r"\s*(\d+(?:\.\d+)?)\s*(.*?)\s*", requested
        )
        quantity = 1.0
        selector = requested.casefold()
        if quantity_match:
            quantity = float(quantity_match.group(1))
            selector = quantity_match.group(2).strip().casefold()
        if quantity <= 0:
            raise ValueError("portion quantity must be positive")

        matches = []
        normalized_selector = re.sub(r"\s+", " ", selector).strip()
        aliases = {
            "tbsp": "tablespoon",
            "tbs": "tablespoon",
            "tsp": "teaspoon",
            "oz": "ounce",
            "lbs": "pound",
            "lb": "pound",
        }
        selector_tokens = [
            aliases.get(token, token[:-1] if token.endswith("s") else token)
            for token in re.findall(r"[a-z0-9]+", normalized_selector)
        ]
        for item in portions:
            searchable = " ".join(
                str(item.get(key) or "")
                for key in ("label", "measure_unit", "portion_description", "modifier")
            ).casefold()
            normalized = re.sub(r"\s+", " ", searchable.replace(",", " ")).strip()
            searchable_tokens = {
                aliases.get(token, token[:-1] if token.endswith("s") else token)
                for token in re.findall(r"[a-z0-9]+", normalized)
            }
            if not selector_tokens or set(selector_tokens).issubset(searchable_tokens):
                matches.append(item)
        if len(matches) != 1:
            options = "; ".join(item["label"] for item in portions[:8])
            if not selector:
                raise ValueError(
                    f"Specify a portion name or option number. Available portions: {options}"
                )
            if not matches:
                raise ValueError(
                    f"Portion '{requested}' was not found. Available portions: {options}"
                )
            raise ValueError(
                f"Portion '{requested}' is ambiguous. Available portions: {options}"
            )

        selected = matches[0]
        grams = quantity * selected["grams_per_unit"]
        return round(grams, 2), selected["label"]


    def close(self):
        self.conn.close()
        if self.sr28_conn is not None:
            self.sr28_conn.close()




if __name__ == "__main__":
    tool = NutritionTool()

    try:
        food_name = input("Enter food name: ").strip()

        if not food_name:
            print("Please enter a food name.")
            raise SystemExit(1)

        foods = tool.search_food(food_name, limit=15)

        if not foods:
            print("No matching foods found.")
            raise SystemExit(0)

        print("\nMatching USDA foods:\n")

        for index, food in enumerate(foods, start=1):
            brand = food.get("brand_name") or food.get("brand_owner")
            serving_size = food.get("serving_size")
            serving_unit = food.get("serving_size_unit")
            household = food.get("household_serving_fulltext")
            details = []
            if brand:
                details.append(f"Brand: {brand}")
            if food.get("gtin_upc"):
                details.append(f"UPC: {food['gtin_upc']}")
            if serving_size and serving_unit:
                serving = f"{serving_size:g} {serving_unit}"
                if household:
                    serving += f" ({household})"
                details.append(f"Serving: {serving}")
            suffix = f" | {' | '.join(details)}" if details else ""
            print(
                f"{index}. {food['description']} "
                f"[{food['data_type']}] "
                f"(FDC ID: {food['fdc_id']}){suffix}"
            )

        choice = int(input("\nSelect food number: "))

        if not 1 <= choice <= len(foods):
            print("Invalid selection.")
            raise SystemExit(1)

        selected = foods[choice - 1]

        portions = tool.get_portions(selected["fdc_id"])
        if portions:
            print("\nAvailable household portions:")
            for index, portion in enumerate(portions, start=1):
                print(f"{index}. {portion['label']} ({portion['gram_weight']:g} g)")
            portion_choice = input(
                "Choose a portion (e.g. 1 or 2 slices), or enter grams "
                "(e.g. 200 or 200 g): "
            ).strip()
        else:
            portion_choice = ""

        if portion_choice:
            grams, portion_label = tool.resolve_portion_grams(
                selected["fdc_id"], portion_choice
            )
            print(f"Using {portion_label}: {grams:g} g")
        else:
            grams = float(input("Enter serving weight (grams): "))

        nutrition = tool.get_nutrition(selected["fdc_id"], grams=grams)

        print("\nSelected food:", selected["description"])
        print("Nutrition results:\n")

        for nutrient, value in nutrition["nutrients"].items():
            print(f"{nutrient}: {value}")

        print(
            "Energy source nutrient ID:",
            nutrition["energy_source_nutrient_id"]
        )

    except ValueError as exc:
        print(f"Invalid input: {exc}")

    finally:
        tool.close()
