import math
from severity_scoring.config import (INCIDENT_TYPE_MAP,WEIGHT_INCIDENT_TYPE, SEVERITY_MAP, WEIGHT_INCIDENT_SEVERITY, 
                                     WEIGHT_PEOPLE_AFFECTED, PEOPLE_AFFECTED_MAX_REFERENCE)
def calculate_incident_severity_contribution(severity):
    """Calculate the weighted contribution of incident severity."""
    mapped_value = SEVERITY_MAP[severity]
    contribution = round(mapped_value * WEIGHT_INCIDENT_SEVERITY, 2)
    return contribution
def normalize_people_affected(people_affected):
    """Normalize the number of people affected using logarithmic scaling."""
    normalized_value = min(math.log(people_affected + 1) / math.log(PEOPLE_AFFECTED_MAX_REFERENCE + 1), 1)
    return round(normalized_value, 2)

def calculate_incident_type_contribution(incident_type):
    """Calculate the weighted contribution of incident type."""
    mapped_value = INCIDENT_TYPE_MAP [incident_type]
    contribution = round(mapped_value * WEIGHT_INCIDENT_TYPE, 2)
    return contribution

def calculate_people_affected_contribution(people_affected):
    """Calculate the weighted contribution of people affected."""
    normalized_value = normalize_people_affected(people_affected)
    contribution = round(normalized_value * WEIGHT_PEOPLE_AFFECTED, 2)
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
    if 0 <= score <= 24:
        return "Low"
    elif 25 <= score <= 49:
        return "Medium"
    elif 50 <= score <= 74:
        return "High"
    elif 75 <= score <= 100:
        return "Critical"
    else:
        raise ValueError("Score must be between 0 and 100.")


def calculate_score_and_category(contributions):
        """Calculate the final score and its category based on contributions."""
        final_score = calculate_final_score(contributions)
        normalized_score = convert_score_to_100(final_score)
        category = categorize_score(normalized_score)
        return round(normalized_score, 2), category