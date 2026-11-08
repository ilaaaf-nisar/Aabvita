"""Adult BMI calculator for Aabvita. Standard WHO adult BMI categories.

BMI is a screening measure, not a diagnosis or body-fat measurement.
Not appropriate for interpreting children, pregnancy, or some athletic builds.
No external dependencies.
"""
from __future__ import annotations

import math
from typing import Any


def calculate_bmi(weight_kg: float, height_cm: float, age: int | None = None) -> dict[str, Any]:
    """Return adult BMI and WHO classification. Height in centimeters."""
    weight_kg = float(weight_kg)
    height_cm = float(height_cm)
    if not math.isfinite(weight_kg) or weight_kg <= 0:
        raise ValueError("weight_kg must be a finite positive number")
    if not math.isfinite(height_cm) or height_cm <= 0:
        raise ValueError("height_cm must be a finite positive number")
    if age is not None and (isinstance(age, bool) or int(age) != age or age < 18):
        raise ValueError("Adult BMI classification requires age >= 18")

    bmi = weight_kg / (height_cm / 100) ** 2
    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal range"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obesity"
    return {
        "bmi": round(bmi, 2),
        "category": category,
        "classification": "WHO adult BMI",
        "note": "BMI is a screening metric, not a diagnosis. Consider waist circumference, body composition and clinical context. Adult cutoffs are not appropriate for children or pregnancy.",
    }


if __name__ == "__main__":
    print("Adult BMI calculator")
    try:
        weight = float(input("Weight (kg): "))
        height = float(input("Height (cm): "))
        age = int(input("Age (years): "))
        result = calculate_bmi(weight, height, age)
        for key, value in result.items():
            print(f"{key}: {value}")
    except ValueError as exc:
        print(f"Input error: {exc}")