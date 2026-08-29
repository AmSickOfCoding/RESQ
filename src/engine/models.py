class Resource:
    def __init__(self, resource_id, resource_type, status, location, capabilities, workload):
        self.resource_id = resource_id
        self.resource_type = resource_type 
        self.status = status
        self.location = location
        self.capabilities = capabilities   
        self.workload = workload

class Incident:
    def __init__(self, incident_id, location, priority, required_resource_type, incident_type, created_at):
        self.incident_id = incident_id
        self.location = location
        self.priority = priority
        self.required_resource_type = required_resource_type
        self.incident_type = incident_type
        self.created_at = created_at

        self.assigned_resource = None
        self.status = "pending"

