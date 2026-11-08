import csv
import sqlite3
from types import SimpleNamespace

import build_usda_db
from agents import orchestrator
from agents.conversation_context import ConversationState, extract_rules
from agents import tool_runtime
from agents.tool_runtime import run_tools
from tools.nutrition_tool import NutritionTool


def _nutrition_db(path, *, branded_table=True):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE food (
                fdc_id INTEGER PRIMARY KEY,
                description TEXT,
                data_type TEXT
            );
            CREATE TABLE food_nutrient (
                fdc_id INTEGER,
                nutrient_id INTEGER,
                amount REAL
            );
            CREATE TABLE nutrient (
                id INTEGER PRIMARY KEY,
                name TEXT,
                unit_name TEXT
            );
            CREATE TABLE measure_unit (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE food_portion (
                id INTEGER PRIMARY KEY,
                fdc_id INTEGER,
                seq_num INTEGER,
                amount REAL,
                measure_unit_id INTEGER,
                portion_description TEXT,
                modifier TEXT,
                gram_weight REAL
            );
            INSERT INTO food VALUES
                (1, 'Oats, rolled', 'foundation_food'),
                (2, 'Chocolate cereal', 'branded_food');
            INSERT INTO nutrient VALUES (1003, 'Protein', 'G');
            INSERT INTO food_nutrient VALUES (1, 1003, 10.0);
            INSERT INTO measure_unit VALUES (1, 'cup');
            INSERT INTO food_portion VALUES
                (1, 1, 1, 0.5, 1, NULL, 'rolled', 20.0);
            """
        )
        if branded_table:
            conn.executescript(
                """
                CREATE TABLE branded_food (
                    fdc_id INTEGER PRIMARY KEY,
                    brand_owner TEXT,
                    brand_name TEXT,
                    gtin_upc TEXT,
                    serving_size REAL,
                    serving_size_unit TEXT,
                    household_serving_fulltext TEXT,
                    short_description TEXT
                );
                INSERT INTO branded_food VALUES
                    (2, 'Acme Foods', 'Cocoa Brand', '0012345678905',
                     30, 'g', '1 bar', 'Chocolate cereal');
                """
            )


def _sr28_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE FOOD_DES (
                ndb_no TEXT, fdgrp_cd TEXT, long_desc TEXT
            );
            CREATE TABLE FD_GROUP (fdgrp_cd TEXT, fdgrp_desc TEXT);
            CREATE TABLE NUT_DATA (ndb_no TEXT, nutr_no TEXT, nutr_val TEXT);
            CREATE TABLE WEIGHT (
                ndb_no TEXT, seq TEXT, amount TEXT, msre_desc TEXT, gm_wgt TEXT
            );
            INSERT INTO FOOD_DES VALUES ('01001', 'FAT', 'Butter, salted');
            INSERT INTO FD_GROUP VALUES ('FAT', 'Fats and Oils');
            INSERT INTO NUT_DATA VALUES
                ('01001', '203', '10'),
                ('01001', '204', '5'),
                ('01001', '205', '20'),
                ('01001', '208', '150');
            INSERT INTO WEIGHT VALUES ('01001', '1', '1', '1 cup chopped', '120');
            """
        )


def test_searches_branded_names_and_exact_upc(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)
    tool = NutritionTool(db_path)
    try:
        by_brand = tool.search_food("Cocoa Brand")
        by_upc = tool.search_food("0012345678905")
    finally:
        tool.close()

    assert by_brand[0]["fdc_id"] == 2
    assert by_brand[0]["brand_name"] == "Cocoa Brand"
    assert by_upc[0]["fdc_id"] == 2


def test_sr28_is_only_used_when_fooddata_central_has_no_match(tmp_path):
    fdc_path = tmp_path / "nutrition.db"
    sr28_path = tmp_path / "sr28.db"
    _nutrition_db(fdc_path)
    _sr28_db(sr28_path)
    tool = NutritionTool(fdc_path, sr28_path)
    try:
        current_match = tool.search_food("oats")
        legacy_match = tool.search_food("butter")
        nutrition = tool.get_sr28_nutrition("1001", grams=50)
        portions = tool.get_portions("01001", source="sr28")
        portion_grams, portion_label = tool.resolve_portion_grams(
            "01001", "2 cups", source="sr28"
        )
    finally:
        tool.close()

    assert current_match[0]["fdc_id"] == 1
    assert "source" not in current_match[0]
    assert legacy_match[0] == {
        "ndb_no": "01001",
        "description": "Butter, salted",
        "food_group": "Fats and Oils",
        "source": "sr28",
    }
    assert nutrition["ndb_no"] == "01001"
    assert nutrition["nutrients"] == {
        "protein_g": 5,
        "fat_g": 2.5,
        "carbohydrates_g": 10,
        "calories_kcal": 75,
    }
    assert portions[0]["gram_weight"] == 120
    assert portion_grams == 240
    assert portion_label == "1 cup chopped"


def test_tool_bridge_runs_legacy_nutrition_without_treating_ndb_as_fdc(
        tmp_path, monkeypatch):
    fdc_path = tmp_path / "nutrition.db"
    sr28_path = tmp_path / "sr28.db"
    _nutrition_db(fdc_path)
    _sr28_db(sr28_path)
    module = SimpleNamespace(
        NutritionTool=lambda db_path: NutritionTool(
            db_path, sr28_db_path=sr28_path
        )
    )
    monkeypatch.setattr(tool_runtime, "_load", lambda _: module)

    result = run_tools(
        sr28_id="01001",
        grams=50,
        db_path=str(fdc_path),
        bmi=False,
        calories=False,
    )

    assert result["results"]["nutrition"]["ndb_no"] == "01001"
    assert result["results"]["nutrition_lookup"] == {
        "source": "sr28",
        "ndb_no": "01001",
        "grams": 50,
        "portion": None,
    }


def test_orchestrator_selects_sr28_candidate_with_its_own_identifier(
        monkeypatch):
    state = ConversationState()
    state.pending_food = {
        "grams": 50,
        "portion": None,
        "candidates": [{
            "description": "Butter, salted",
            "ndb_no": "01001",
            "source": "sr28",
        }],
    }
    calls = []

    def fake_run_tools(**kwargs):
        calls.append(kwargs)
        return {
            "results": {
                "nutrition": {
                    "ndb_no": "01001",
                    "source": "sr28",
                    "serving_grams": 50,
                    "nutrients": {
                        "calories_kcal": 75,
                        "protein_g": 5,
                        "carbohydrates_g": 10,
                        "fat_g": 2.5,
                    },
                },
                "nutrition_lookup": {
                    "source": "sr28",
                    "ndb_no": "01001",
                    "grams": 50,
                    "portion": None,
                },
            },
            "errors": {},
            "missing_fields": {},
        }

    monkeypatch.setattr(orchestrator, "run_tools", fake_run_tools)
    monkeypatch.setattr(
        orchestrator, "route",
        lambda *_: orchestrator.RoutingDecision(["diet"], "test", "test"),
    )
    monkeypatch.setitem(
        orchestrator.AGENTS,
        "diet",
        lambda *_args, **_kwargs: {"answer": "Here is the nutrition estimate.", "sources": []},
    )
    monkeypatch.setattr(
        orchestrator, "synthesize",
        lambda *_args, **_kwargs: "Here is the nutrition estimate.",
    )

    result = orchestrator.ask_coach(
        "1", state=state, routing="keywords", extraction="rules"
    )

    assert calls[0]["fdc_id"] is None
    assert calls[0]["sr28_id"] == "01001"
    assert "legacy USDA Standard Reference 28 data" in result["answer"]


def test_generic_foods_rank_before_branded_description_matches(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO food VALUES (3, 'Chicken, breast, roasted', 'foundation_food')"
        )
        conn.execute(
            "INSERT INTO food VALUES (4, 'Chicken', 'branded_food')"
        )
        conn.execute(
            """
            INSERT INTO branded_food (
                fdc_id, brand_owner, brand_name, gtin_upc, serving_size,
                serving_size_unit, household_serving_fulltext, short_description
            ) VALUES (4, 'Test Company', NULL, '0011111111111', 100, 'g',
                      '1 serving', 'Chicken')
            """
        )
    tool = NutritionTool(db_path)
    try:
        matches = tool.search_food("chicken")
    finally:
        tool.close()

    assert matches[0]["fdc_id"] == 3
    assert matches[1]["fdc_id"] == 4
    assert matches[1]["brand_owner"] == "Test Company"
    assert matches[1]["serving_size"] == 100


def test_portion_resolution_scales_and_uses_gram_weights(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)
    tool = NutritionTool(db_path)
    try:
        portions = tool.get_portions(1)
        grams, label = tool.resolve_portion_grams(1, "2 cups")
        nutrition = tool.get_nutrition(1, grams)
        branded, branded_label = tool.resolve_portion_grams(2, "1 bar")
    finally:
        tool.close()

    assert portions[0]["gram_weight"] == 20
    assert grams == 80
    assert "cup" in label
    assert nutrition["serving_grams"] == 80
    assert nutrition["nutrients"]["protein_g"] == 8
    assert branded == 30
    assert branded_label == "1 bar"


def test_numeric_portion_input_cannot_be_multiplied_as_a_huge_quantity(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)
    tool = NutritionTool(db_path)
    try:
        numeric_weight, numeric_label = tool.resolve_portion_grams(1, "200")
        explicit_weight, explicit_label = tool.resolve_portion_grams(1, "200 g")
        selected_weight, _ = tool.resolve_portion_grams(1, "1")
    finally:
        tool.close()

    assert numeric_weight == explicit_weight == 200
    assert numeric_label == explicit_label == "200 g"
    assert selected_weight == 20


def test_legacy_database_without_brand_table_still_searches(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path, branded_table=False)
    tool = NutritionTool(db_path)
    try:
        matches = tool.search_food("Oats")
    finally:
        tool.close()

    assert len(matches) == 1
    assert matches[0]["fdc_id"] == 1
    assert matches[0]["brand_name"] is None


def test_tool_bridge_accepts_portions_and_keeps_gram_api(tmp_path):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)

    portion_result = run_tools(
        fdc_id=1, grams=0, portion="2 cups", db_path=str(db_path),
        bmi=False, calories=False,
    )
    gram_result = run_tools(
        fdc_id=1, grams=50, db_path=str(db_path),
        bmi=False, calories=False,
    )

    assert portion_result["results"]["nutrition"]["serving_grams"] == 80
    assert portion_result["results"]["nutrition_lookup"]["portion"] == "0.5 cup rolled"
    assert gram_result["results"]["nutrition"]["serving_grams"] == 50


def test_branded_csv_import_is_incremental_and_preserves_food_table(
        tmp_path, monkeypatch):
    source = tmp_path / "branded_food.csv"
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "fdc_id", "brand_owner", "brand_name", "gtin_upc",
            "serving_size", "serving_size_unit",
            "household_serving_fulltext", "short_description",
        ])
        writer.writeheader()
        writer.writerow({
            "fdc_id": 25,
            "brand_owner": "Test Owner",
            "brand_name": "Test Brand",
            "gtin_upc": "0001234567890",
            "serving_size": "25",
            "serving_size_unit": "g",
            "household_serving_fulltext": "1 snack bar",
            "short_description": "Snack bar",
        })
    db_path = tmp_path / "nutrition.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE food (fdc_id INTEGER)")
        conn.execute("INSERT INTO food VALUES (1)")
        conn.execute("CREATE TABLE branded_food (fdc_id INTEGER, brand_name TEXT)")
        conn.execute("INSERT INTO branded_food VALUES (9, 'Old Brand')")
    monkeypatch.setattr(build_usda_db, "DATA_DIR", tmp_path)
    with sqlite3.connect(db_path) as conn:
        build_usda_db.import_branded_food(conn)
        food_count = conn.execute("SELECT COUNT(*) FROM food").fetchone()[0]
        branded = conn.execute(
            "SELECT brand_name, gtin_upc FROM branded_food WHERE fdc_id = 25"
        ).fetchone()

    assert food_count == 1
    assert branded == ("Test Brand", "0001234567890")


def test_portion_request_is_kept_with_food_candidate_for_follow_up(
        tmp_path, monkeypatch):
    db_path = tmp_path / "nutrition.db"
    _nutrition_db(db_path)
    extracted = extract_rules("Nutrition for 2 cups of oats")
    assert extracted["food"] == "oats"
    assert extracted["portion"] == "2 cups"

    state = ConversationState()
    calls = []

    def run_tools(**kwargs):
        calls.append(kwargs)
        if kwargs["fdc_id"] is None:
            return {
                "results": {
                    "food_matches": [{
                        "fdc_id": 1,
                        "description": "Oats, rolled",
                        "brand_name": None,
                    }],
                },
                "errors": {},
                "missing_fields": {},
            }
        return {
            "results": {
                "nutrition": {
                    "serving_grams": 80,
                    "nutrients": {
                        "protein_g": 8,
                        "fat_g": None,
                        "carbohydrates_g": None,
                        "calories_kcal": None,
                    },
                },
                "nutrition_lookup": {
                    "fdc_id": 1,
                    "grams": 80,
                    "portion": "2 cups rolled",
                },
            },
            "errors": {},
            "missing_fields": {},
        }

    monkeypatch.setattr(orchestrator, "run_tools", run_tools)
    monkeypatch.setattr(orchestrator, "route", lambda *_: orchestrator.RoutingDecision(
        ["diet"], "test", "test"
    ))
    def diet_agent(question, **kwargs):
        return {
            "answer": f"Nutrition details for {question} ({len(kwargs)} options).",
            "sources": [],
        }

    monkeypatch.setitem(orchestrator.AGENTS, "diet", diet_agent)
    monkeypatch.setattr(
        orchestrator, "synthesize",
        lambda *_args, **_kwargs: f"Nutrition details for {_args[0]} "
        f"({_kwargs.get('tool_context', 'no tool context')}).",
    )
    orchestrator.ask_coach(
        "Nutrition for 2 cups of oats",
        state=state,
        routing="keywords",
        extraction="rules",
        db_path=str(db_path),
    )
    orchestrator.ask_coach(
        "1",
        state=state,
        routing="keywords",
        extraction="rules",
        db_path=str(db_path),
    )

    assert calls[1]["fdc_id"] == 1
    assert calls[1]["portion"] == "2 cups"


def test_rules_accept_upc_as_a_food_lookup_term():
    extracted = extract_rules("Nutrition for 0012345678905")
    assert extracted["food"] == "0012345678905"
