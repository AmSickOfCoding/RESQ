from severity_scoring.config import (SEVERITY_MAP, WEIGHT_INCIDENT_SEVERITY,)

def calculate_incident_severity_contribution(incident_severity):
    """Calculate the weighted contribution of incident severity."""
    mapped_value = SEVERITY_MAP[incident_severity]
    contribution = mapped_value * WEIGHT_INCIDENT_SEVERITY
    return contribution

def normalize_waiting_time(waiting_time):
    """Normalize waiting time using the 10-minute reference."""

    normalized_value = min(waiting_time / 10, 1)
    return normalized_value

def calculate_weighted_contribution(mapped_value, weight):
    """Calculate the weighted contribution of a factor."""
    return mapped_value * weight

def calculate_final_score(contributions):
    """Calculate the final normalized score based from factors contributions."""
    final_score = sum(contributions.values())
    return final_score

def convert_score_to_100(normalized_score):
    """Convert the normalized score from 0-1  to a 100-point scale."""
    return normalized_score * 100

def categorize_score(score):
    """Categorize the final score into Low, Medium, High, or Critical."""
    if 0 <= score < 24:
        return "Low"
    elif 25 <= score < 49:
        return "Medium"
    elif 50 <= score < 74:
        return "High"
    elif 75 <= score <= 100:
        return "Critical"
    else:
        raise ValueError("Score must be between 0 and 100.")