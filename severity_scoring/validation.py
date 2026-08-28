class SeverityValidationError(ValueError):
    """Raised when a severity scoring input validation fails."""
    pass

REQUIRED_FIELDS = {"incident_id", "severity","people_affected","waiting_time","required_unit_type",}

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
def validate_incident_severity(severity):
    """Validate the incident severity value."""
    if not isinstance (severity, int) or isinstance(severity, bool):
        raise SeverityValidationError("severity must be an integer.")

    if not 1 <= severity <= 5:
        raise SeverityValidationError("severity must be an integer between 1 and 5.")
    
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

def validate_required_unit_type(required_unit_type):
    """Validate the required response unit type."""
    allowed_types = {"AMBULANCE", "FIRE", "POLICE"}

    if required_unit_type not in allowed_types:
        raise SeverityValidationError("required_unit_type must be one of: AMBULANCE, FIRE, POLICE")

    return True

def validate_incident(incident):
    """Validate the entire incident input."""
    validate_incident_input(incident)
    validate_incident_severity(incident["severity"])
    validate_people_affected(incident["people_affected"])
    validate_waiting_time(incident["waiting_time"])
    validate_required_unit_type(incident["required_unit_type"])
    return True
