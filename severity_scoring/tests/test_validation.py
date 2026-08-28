import pytest

from severity_scoring.validation import (
    SeverityValidationError,
    validate_incident_input,
    validate_incident_severity,
    validate_people_affected,
    validate_waiting_time,
    validate_required_unit_type,
    validate_incident,
)


def test_valid_incident():
    incident = {
        "incident_id": "INC001",
        "severity": 3,
        "people_affected": 5,
        "waiting_time": 10,
        "required_unit_type": "AMBULANCE",
    }

    assert validate_incident(incident) is True


def test_missing_required_field():
    incident = {
        "incident_id": "INC001",
        "severity": 3,
        "people_affected": 5,
        "waiting_time": 10,
    }

    with pytest.raises(SeverityValidationError):
        validate_incident(incident)


def test_invalid_severity():
    with pytest.raises(SeverityValidationError):
        validate_incident_severity(0)

    with pytest.raises(SeverityValidationError):
        validate_incident_severity(6)

    with pytest.raises(SeverityValidationError):
        validate_incident_severity(2.5)


def test_invalid_people_affected():
    with pytest.raises(SeverityValidationError):
        validate_people_affected(-1)

    with pytest.raises(SeverityValidationError):
        validate_people_affected(2.5)


def test_invalid_waiting_time():
    with pytest.raises(SeverityValidationError):
        validate_waiting_time(-1)


def test_invalid_required_unit_type():
    with pytest.raises(SeverityValidationError):
        validate_required_unit_type("FIRE_TRUCK")