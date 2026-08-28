# Factor Weights

WEIGHT_INCIDENT_SEVERITY = 0.40
WEIGHT_PEOPLE_AFFECTED = 0.25
WEIGHT_WAITING_TIME = 0.20
WEIGHT_INCIDENT_TYPE = 0.15


# Incident Severity Direct Mapping

SEVERITY_MAP = {
    "Low": 0.10,
    "Medium": 0.40,
    "High": 0.70,
    "Critical": 1.00,
}


# Final Score Category Thresholds

CATEGORY_THRESHOLDS = [
    (0, 24, "Low"),
    (25, 49, "Medium"),
    (50, 74, "High"),
    (75, 100, "Critical"),
]


# TBD - People Affected

PEOPLE_AFFECTED_FORMULA = None
PEOPLE_AFFECTED_MAX_REFERENCE = None


# TBD - Waiting Time

WAITING_TIME_FORMULA = "min(waiting_time / 10, 1)"
WAITING_TIME_MAX_REFERENCE = 10
WAITING_TIME_UNIT = "minutes"


# TBD - Incident Type

INCIDENT_TYPE_MAP = None