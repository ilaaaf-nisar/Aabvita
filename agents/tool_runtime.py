"""Deterministic tool bridge for Aabvita. No LLM-generated numeric inputs."""
from __future__ import annotations
import importlib.util
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def _load(module_name: str):
    path = TOOLS / (module_name + '.py')
    if not path.is_file():
        raise FileNotFoundError(f'Missing tool module: {path}')
    spec = importlib.util.spec_from_file_location(f'my_coach_{module_name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a positive number')
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f'{field} must be a finite positive number')
    return number


def run_tools(*, profile: dict | None = None, food: str | None = None,
              grams: float = 100, fdc_id: int | None = None,
              sr28_id: str | None = None,
              portion: str | None = None,
              db_path: str | None = None, bmi: bool = True,
              calories: bool = True, protein: bool = False,
              protein_goal: str = 'general') -> dict[str, Any]:
    """Execute explicitly requested calculations. No silent defaults for user profile."""
    output: dict[str, Any] = {'results': {}, 'errors': {}, 'missing_fields': {}}
    if profile is not None and (bmi or calories):
        if not isinstance(profile, dict):
            raise ValueError('profile must be a JSON object')
        if bmi:
            common = ('weight_kg', 'height_cm')
            missing = [field for field in common if field not in profile]
            if missing:
                output['missing_fields']['bmi'] = missing
            else:
                try:
                    bmi_tool = _load('bmi_calculator')
                    output['results']['bmi'] = bmi_tool.calculate_bmi(
                        profile['weight_kg'], profile['height_cm'], profile.get('age'))
                except Exception as exc:
                    output['errors']['bmi'] = f'{type(exc).__name__}: {exc}'
        if calories:
            calorie_fields = ('weight_kg', 'height_cm', 'age', 'sex', 'activity_level')
            missing = [field for field in calorie_fields if field not in profile]
            if missing:
                output['missing_fields']['calories'] = missing
            else:
                try:
                    calculator = _load('calorie_calculator')
                    output['results']['calories'] = calculator.calculate_calories(
                        weight_kg=profile['weight_kg'], height_cm=profile['height_cm'],
                        age=profile['age'], sex=profile['sex'],
                        activity_level=profile['activity_level'],
                        goal=profile.get('goal', 'maintain'))
                except Exception as exc:
                    output['errors']['calories'] = f'{type(exc).__name__}: {exc}'
    if protein:
        weight = profile.get('weight_kg') if isinstance(profile, dict) else None
        if weight is None:
            output['missing_fields']['protein'] = ['weight_kg']
        else:
            try:
                module = _load('protein_calculator')
                output['results']['protein'] = module.calculate_protein(
                    weight_kg=weight, goal=protein_goal)
            except Exception as exc:
                output['errors']['protein'] = f'{type(exc).__name__}: {exc}'
    if food is not None or fdc_id is not None or sr28_id is not None:
        try:
            if fdc_id is not None and sr28_id is not None:
                raise ValueError('fdc_id and sr28_id cannot both be provided')
            module = _load('nutrition_tool')
            # Compatible with the earlier NutritionTool(name, limit) and
            # get_nutrition(fdc_id, grams) interface.
            NutritionTool = getattr(module, 'NutritionTool')
            if db_path is not None:
                try:
                    tool = NutritionTool(db_path=db_path)
                except TypeError as exc:
                    raise TypeError('NutritionTool does not accept db_path; update adapter') from exc
            else:
                tool = NutritionTool()
            try:
                source = 'sr28' if sr28_id is not None else 'fdc'
                if fdc_id is not None:
                    chosen_id = int(fdc_id)
                elif sr28_id is not None:
                    chosen_id = sr28_id
                else:
                    matches = tool.search_food(food, limit=5)
                    output['results']['food_matches'] = matches
                    # Never silently select the first ambiguous match.
                    return output
                if portion is not None:
                    quantity, portion_label = tool.resolve_portion_grams(
                        chosen_id, portion, source=source
                    )
                else:
                    quantity = _positive(grams, 'grams')
                    portion_label = None
                if source == 'sr28':
                    output['results']['nutrition'] = tool.get_sr28_nutrition(
                        chosen_id, quantity
                    )
                    output['results']['nutrition_lookup'] = {
                        'source': source,
                        'ndb_no': chosen_id,
                        'grams': quantity,
                        'portion': portion_label,
                    }
                else:
                    output['results']['nutrition'] = tool.get_nutrition(
                        chosen_id, quantity
                    )
                    output['results']['nutrition_lookup'] = {
                        'fdc_id': chosen_id,
                        'grams': quantity,
                        'portion': portion_label,
                    }
            finally:
                tool.close()
        except Exception as exc:
            output['errors']['nutrition'] = f'{type(exc).__name__}: {exc}'
    return output
