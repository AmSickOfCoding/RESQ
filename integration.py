from allocation import allocate_resource, get_allocation_reason
from dispatch import dispatch_resource


def process_incident(incident, resources):

    selected_resource, score = allocate_resource(
        incident,
        resources
    )

    if selected_resource is None:
        return {
            "success": False,
            "message": "No suitable resource is available"
        }

    reasons = get_allocation_reason(
        incident,
        selected_resource
    )

    success = dispatch_resource(
        incident,
        selected_resource
    )

    return {
        "success": success,
        "incident_id": incident.incident_id,
        "selected_resource_id": selected_resource.resource_id,
        "allocation_score": score,
        "allocation_reasons": reasons,
        "incident_status": incident.status,
        "resource_status": selected_resource.status,
        "waiting_time": incident.waiting_time,
        "normalized_waiting_time": incident.normalized_waiting_time
    }