"""Deterministic daily protein target estimator for Aabvita.

Population guidance only, not a prescription. People with kidney disease, liver
disease, pregnancy, or lactation need individualized advice from a clinician or
registered dietitian.
"""
from __future__ import annotations

import math
from typing import Any

GUIDELINES = {
    "general": (0.8, 1.0, "general adult maintenance"),
    "active": (1.2, 1.6, "regular exercise or training"),
    "strength": (1.6, 2.2, "strength training or muscle gain"),
    "weight_loss": (1.6, 2.0, "weight loss while preserving muscle"),
}


def calculate_protein(weight_kg: float, goal: str = "general") -> dict[str, Any]:
    """Return a daily protein range based on body weight and training context."""
    weight_kg = float(weight_kg)
    if not math.isfinite(weight_kg) or weight_kg <= 0:
        raise ValueError("weight_kg must be a finite positive number")
    goal = goal.strip().lower()
    if goal not in GUIDELINES:
        raise ValueError(f"goal must be one of: {', '.join(GUIDELINES)}")

    low_per_kg, high_per_kg, context = GUIDELINES[goal]
    return {
        "weight_kg": round(weight_kg, 1),
        "context": context,
        "grams_per_kg_range": [low_per_kg, high_per_kg],
        "grams_per_day_range": [round(weight_kg * low_per_kg),
                                round(weight_kg * high_per_kg)],
        "note": (
            "Population guidance only, not a prescription. Protein needs vary with "
            "medical conditions, kidney or liver disease, pregnancy, and lactation; "
            "seek individualized clinical or dietitian advice when relevant."
        ),
    }


if __name__ == "__main__":
    print("Daily protein target estimator")
    try:
        weight = float(input("Weight (kg): "))
        print("Contexts:", ", ".join(GUIDELINES))
        goal = input("Context [general]: ").strip() or "general"
        result = calculate_protein(weight, goal)
        for key, value in result.items():
            print(f"{key}: {value}")
    except ValueError as exc:
        print(f"Input error: {exc}")
