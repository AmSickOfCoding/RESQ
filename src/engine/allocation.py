def calculate_resource_score(incident, resource):
    score = 0

    # Resource must be available
    if resource.status != "available":
        return -1

    # Resource type must match
    if resource.resource_type != incident.required_resource_type:
        return -1

    # Resource must have the required capability
    if incident.incident_type not in resource.capabilities:
        return -1

    # Same location gets a higher score
    if resource.location == incident.location:
        score += 50

    # Lower workload is better
    score += max(0, 20 - (resource.workload * 5))

    # Lower workload gets a better score
    if resource.workload == 0:
        score += 10

    return score


def allocate_resource(incident, resources):
    best_resource = None
    best_score = -1

    for resource in resources:
        score = calculate_resource_score(incident, resource)

        if score > best_score:
            best_score = score
            best_resource = resource

    return best_resource, best_score


def get_allocation_reason(incident, resource):
    reasons = []

    if resource.resource_type == incident.required_resource_type:
        reasons.append("Correct resource type")

    if resource.status == "available":
        reasons.append("Resource is available")

    if incident.incident_type in resource.capabilities:
        reasons.append("Required capability is available")

    if resource.location == incident.location:
        reasons.append("Same location")

    if resource.workload == 0:
        reasons.append("No current workload")
    else:
        reasons.append(f"Current workload: {resource.workload}")

    return reasons
