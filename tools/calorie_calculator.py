"""Estimate adult resting and daily energy needs for Aabvita.

Uses Mifflin-St Jeor for estimated resting metabolic rate (RMR) and
an activity multiplier for estimated total daily energy expenditure (TDEE).
These are population estimates, not measured energy needs or medical advice.
No external dependencies.
"""
from __future__ import annotations

import math
from typing import Any

ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def calculate_calories(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
    activity_level: str = "sedentary",
    goal: str = "maintain",
) -> dict[str, Any]:
    """Estimate adult RMR, TDEE, and optional goal-based calorie target.

    `sex` is the male/female coefficient used by this specific published
    equation, not a statement about gender identity. If neither coefficient
    fits, use a clinician-guided or measured energy estimate.
    """
    weight_kg = float(weight_kg)
    height_cm = float(height_cm)
    if not math.isfinite(weight_kg) or weight_kg <= 0:
        raise ValueError("weight_kg must be a finite positive number")
    if not math.isfinite(height_cm) or height_cm <= 0:
        raise ValueError("height_cm must be a finite positive number")
    if isinstance(age, bool) or not isinstance(age, int) or not 18 <= age <= 120:
        raise ValueError("age must be an integer from 18 to 120")
    sex = sex.strip().lower()
    if sex not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female' for Mifflin-St Jeor")
    activity_level = activity_level.strip().lower()
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError(f"activity_level must be one of: {', '.join(ACTIVITY_FACTORS)}")
    goal = goal.strip().lower()
    if goal not in ("maintain", "lose", "gain"):
        raise ValueError("goal must be 'maintain', 'lose', or 'gain'")

    rmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "male" else -161)
    tdee = rmr * ACTIVITY_FACTORS[activity_level]
    # Small illustrative adjustment; actual needs should be personalized and monitored.
    adjustment = {"maintain": 0, "lose": -300, "gain": 300}[goal]
    target = tdee + adjustment
    return {
        "method": "Mifflin-St Jeor",
        "rmr_kcal_per_day": round(rmr),
        "tdee_kcal_per_day": round(tdee),
        "activity_level": activity_level,
        "activity_factor": ACTIVITY_FACTORS[activity_level],
        "goal": goal,
        "illustrative_goal_adjustment_kcal": adjustment,
        "illustrative_target_kcal_per_day": round(target),
        "note": (
            "Estimates only; activity factors are approximate. The goal adjustment is "
            "illustrative, not an individualized prescription. Not validated for pregnancy, "
            "lactation, children, or complex medical conditions; seek professional guidance "
            "when applicable. Monitor outcomes and adjust with clinical context."
        ),
    }


if __name__ == "__main__":
    print("Adult calorie needs estimator")
    try:
        weight = float(input("Weight (kg): "))
        height = float(input("Height (cm): "))
        age = int(input("Age (years): "))
        sex = input("Equation coefficient (male/female): ")
        print("Activity levels:", ", ".join(ACTIVITY_FACTORS))
        activity = input("Activity level [sedentary]: ").strip() or "sedentary"
        goal = input("Goal (maintain/lose/gain) [maintain]: ").strip() or "maintain"
        result = calculate_calories(weight, height, age, sex, activity, goal)
        for key, value in result.items():
            print(f"{key}: {value}")
    except ValueError as exc:
        print(f"Input error: {exc}")
