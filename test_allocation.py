from models import Resource, Incident
from allocation import allocate_resource
from datetime import datetime


def test_select_available_resource():
    ambulance1 = Resource(
        1,
        "ambulance",
        "available",
        "Amman",
        ["medical", "trauma"],
        0
    )

    ambulance2 = Resource(
        2,
        "ambulance",
        "busy",
        "Amman",
        ["medical"],
        1
    )

    fire_truck = Resource(
        3,
        "fire_truck",
        "available",
        "Amman",
        ["fire", "rescue"],
        0
    )

    incident = Incident(
        101,
        "Amman",
        "high",
        "ambulance",
        "trauma",
        datetime.now()
    )

    resources = [ambulance1, ambulance2, fire_truck]

    selected_resource, score = allocate_resource(
        incident,
        resources
    )

    assert selected_resource is not None
    assert selected_resource.resource_id == 1
    assert score > 0

if __name__ == "__main__":
    test_select_available_resource()
    print("Test passed successfully!")


    