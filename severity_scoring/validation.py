class SeverityValidationError(ValueError):
    """Raised when a severity scoring input validation fails."""
    pass

from severity_scoring.config import SEVERITY_MAP

REQUIRED_FIELDS = {"incident_id", "incident_severity","people_affected","waiting_time","incident_type",}

def validate_incident_input(incident):
    """Validate the basic incident input."""
    if incident is None:
        raise SeverityValidationError("Incident input cannot be None.")

    if not isinstance(incident, dict):
        raise SeverityValidationError("Incident input must be a dictionary.")

    missing_fields = REQUIRED_FIELDS - incident.keys()
    if missing_fields:
        raise SeverityValidationError(f"Missing required fields: {sorted(missing_fields)}")

    return True
def validate_incident_severity(incident_severity):
    """Validate the incident severity value."""
    if incident_severity not in SEVERITY_MAP:
        raise SeverityValidationError(f"Invalid incident_severity: {incident_severity}." 
                                      f"Expected one of {list(SEVERITY_MAP.keys())}.")
    return True

def validate_people_affected(people_affected):
    """Validate the number of people affected ."""
    if not isinstance(people_affected, int) or isinstance (people_affected, bool):
        raise SeverityValidationError( "people_affected must be an integer.")

    if people_affected < 0:
        raise SeverityValidationError("people_affected cannot be negative.")

    return True

def validate_waiting_time(waiting_time):
    """Validate waiting time in minutes."""
    if not isinstance(waiting_time, (int, float)) or isinstance(waiting_time, bool):
        raise SeverityValidationError("waiting_time must be a number in minutes.")

    if waiting_time < 0:
        raise SeverityValidationError("waiting_time cannot be negative.")

    return True

def validate_incident(incident):
    """Validate the entire incident input."""
    validate_incident_input(incident)
    validate_incident_severity(incident["incident_severity"])
    validate_people_affected(incident["people_affected"])
    validate_waiting_time(incident["waiting_time"])
    return True
