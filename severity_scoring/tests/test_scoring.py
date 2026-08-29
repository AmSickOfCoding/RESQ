from severity_scoring.scoring import (
    calculate_incident_severity_contribution,
    normalize_people_affected,
    calculate_people_affected_contribution,
    normalize_waiting_time,
    calculate_incident_type_contribution,
    calculate_final_score,
    convert_score_to_100,
    categorize_score,
)


def test_severity_contribution():
    assert calculate_incident_severity_contribution(1) == 0.04
    assert calculate_incident_severity_contribution(3) == 0.22
    assert calculate_incident_severity_contribution(5) == 0.40


def test_people_affected_normalization():
    assert normalize_people_affected(0) == 0.0
    assert normalize_people_affected(100) == 1.0


def test_people_affected_contribution():
    assert calculate_people_affected_contribution(0) == 0.0
    assert calculate_people_affected_contribution(100) == 0.25


def test_waiting_time_normalization():
    assert normalize_waiting_time(0) == 0
    assert normalize_waiting_time(10) == 1
    assert normalize_waiting_time(20) == 1


def test_incident_type_contribution():
    assert calculate_incident_type_contribution("MEDICAL") == 0.15
    assert calculate_incident_type_contribution("FIRE") == 0.14
    assert calculate_incident_type_contribution("POLICE") == 0.12
    assert calculate_incident_type_contribution("OTHER") == 0.10


def test_final_score():
    contributions = {
        "severity": 0.40,
        "people_affected": 0.25,
        "waiting_time": 0.20,
        "incident_type": 0.15,
    }

    assert calculate_final_score(contributions) == 1.0


def test_score_conversion():
    assert convert_score_to_100(1.0) == 100.0
    assert convert_score_to_100(0.5) == 50.0


def test_score_categories():
    assert categorize_score(24) == "Low"
    assert categorize_score(25) == "Medium"
    assert categorize_score(49) == "Medium"
    assert categorize_score(50) == "High"
    assert categorize_score(74) == "High"
    assert categorize_score(75) == "Critical"
    assert categorize_score(100) == "Critical"