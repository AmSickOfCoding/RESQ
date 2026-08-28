from datetime import datetime

def dispatch_resource(incident, resource):
    if resource is None:
        return False

    if resource.status != "available":
        return False

   # Dispatch time
    dispatch_time = datetime.now()

    # Waiting Time in minutes
    waiting_time = (
        dispatch_time - incident.created_at
    ).total_seconds() / 60

    # Reference waiting time = 10 minutes
    reference_waiting_time = 10

    # Normalized Waiting Time
    normalized_waiting_time = min(
        waiting_time / reference_waiting_time,
        1
    )

    # Save dispatch and waiting time information
    incident.dispatch_time = dispatch_time
    incident.waiting_time = waiting_time
    incident.normalized_waiting_time = normalized_waiting_time

    # Update resource
    resource.status = "busy"
    resource.workload += 1

    # Update incident
    incident.assigned_resource = resource
    incident.status = "dispatched"

    return True

def release_resource(incident):
    resource = incident.assigned_resource

    if resource is None:
        return False

    if resource.status != "busy":
        return False

    resource.status = "available"

    if resource.workload > 0:
        resource.workload -= 1

    incident.status = "resolved"

    return True