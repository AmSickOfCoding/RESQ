from models import Resource, Incident
from allocation import allocate_resource, get_allocation_reason
from dispatch import dispatch_resource, release_resource
from datetime import datetime
from integration import process_incident

ambulance1 = Resource(1, "ambulance", "available", "Amman", ["medical", "trauma"], 0)
ambulance2 = Resource(2, "ambulance", "busy", "Amman", ["medical"], 1)
fire_truck1 = Resource(3, "fire_truck", "available", "Amman", ["fire", "rescue"], 0)

incident = Incident(101, "Amman", "high", "ambulance", "trauma", datetime.now())

resources = [ambulance1, ambulance2, fire_truck1]

selected_resource, score = allocate_resource(incident, resources)
\

if selected_resource is None:

    print("No suitable resource is available.")

else:

    print("Selected Resource:", selected_resource.resource_id)
    print("Allocation Score:", score)

    print("Reasons:")
    reasons = get_allocation_reason(
        incident,
        selected_resource
    )

    for reason in reasons:
        print("-", reason)


    # Dispatch
    success = dispatch_resource(
        incident,
        selected_resource
    )


    if success:
        print("\nResource dispatched successfully.")
        print("Incident Status:", incident.status)
        print("Resource Status:", selected_resource.status)
        print("Resource Workload:", selected_resource.workload)
        print("Waiting Time:", incident.waiting_time, "minutes")
        print("Normalized Waiting Time:", incident.normalized_waiting_time)


    # Release
    release_resource(incident)

    print("\nAfter Release:")
    print("Incident Status:", incident.status)
    print("Resource Status:", selected_resource.status)
    print("Resource Workload:", selected_resource.workload)

result = process_incident(incident, resources)

print(result)    