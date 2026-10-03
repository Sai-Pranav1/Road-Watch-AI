"""
Priority Score Engine
Formula: Priority Score = f(Severity, Confidence, Road Class, Defect Coverage)
Output: Integer between 0 and 100
"""

from typing import Dict, Any

# Baseline severity weights
SEVERITY_WEIGHTS: Dict[str, float] = {
    "Critical": 92.0,
    "High": 76.0,
    "Medium": 52.0,
    "Low": 28.0,
}

# Road hierarchy multipliers reflecting traffic volume & vehicle speed risks
ROAD_CLASS_WEIGHTS: Dict[str, float] = {
    "Highway / Arterial": 1.18,
    "Collector / Main Ave": 1.08,
    "Local Street": 1.00,
    "Residential": 0.88,
}

# Damage type danger coefficients
DAMAGE_TYPE_COEFFICIENTS: Dict[str, float] = {
    "pothole": 1.05,       # Potholes cause direct tire/rim blowout and motorcycle crashes
    "edge break": 1.02,    # Edge breaks cause vehicle rollover/swerving
    "crack": 0.95,         # Longitudinal/alligator cracks precede pothole collapse
    "surface wear": 0.90,  # Friction loss / raveling
}


def calculate_priority_score(
    severity: str,
    confidence: float,
    road_class: str = "Local Street",
    damage_type: str = "pothole",
    defect_area_ratio: float = 0.08
) -> int:
    """
    Computes a composite priority score (0 - 100) based on defect severity,
    model confidence, road classification hierarchy, defect type, and bounding-box area ratio.
    """
    # Normalize severity string
    sev_key = severity.capitalize() if severity else "Medium"
    base_sev = SEVERITY_WEIGHTS.get(sev_key, 50.0)

    # Road hierarchy multiplier
    road_mult = ROAD_CLASS_WEIGHTS.get(road_class, 1.0)

    # Damage type coefficient
    dtype_key = damage_type.lower() if damage_type else "pothole"
    dtype_coef = DAMAGE_TYPE_COEFFICIENTS.get(dtype_key, 1.0)

    # Confidence scaling (0.6 - 1.0)
    # High confidence reinforces priority; lower confidence scales it down gracefully
    conf_clamped = max(0.2, min(1.0, float(confidence)))
    conf_weight = 0.80 + (0.20 * conf_clamped)

    # Defect size ratio bonus (0.0 to 1.0)
    # If a pothole/crack covers > 12% of the road view, add up to 10 points
    area_clamped = max(0.0, min(1.0, float(defect_area_ratio)))
    area_bonus = min(12.0, area_clamped * 60.0)

    # Composite formula
    raw_score = (base_sev * road_mult * dtype_coef * conf_weight) + area_bonus

    # Ensure result is an integer strictly bounded within [0, 100]
    final_score = int(round(max(0.0, min(100.0, raw_score))))
    return final_score


def determine_severity_from_defect(
    damage_type: str,
    defect_area_ratio: float,
    aspect_ratio: float = 1.0,
    intensity_contrast: float = 0.5
) -> str:
    """
    Determines severity category (Low, Medium, High, Critical)
    based on defect size ratio and bounding-box coverage.
    """
    # Large area defects or deep contrast depressions are Critical/High
    if defect_area_ratio >= 0.18 or (defect_area_ratio >= 0.12 and intensity_contrast > 0.65):
        return "Critical"
    elif defect_area_ratio >= 0.09 or (defect_area_ratio >= 0.06 and intensity_contrast > 0.50):
        return "High"
    elif defect_area_ratio >= 0.035:
        return "Medium"
    else:
        return "Low"
