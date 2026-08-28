# Integration Contract & Data Schemas

This document defines the schema contracts for primary domain entities, events, and API interfaces within the RESQ Digital Twin platform.

## 1. Incident Schema
- `incident_id` (string): Unique identifier for the emergency incident.
- `severity` (integer, 1-5): Incident criticality rating.
- `required_unit_type` (enum): Type of response unit required (`AMBULANCE`, `FIRE`, `POLICE`).
- `location_node_id` (string): Target node identifier in the city graph.
- `reported_at` (float): Simulation tick timestamp when reported.
- `status` (enum): Lifecycle state (`REPORTED`, `QUEUED`, `ASSIGNED`, `IN_TRANSIT`, `ON_SCENE`, `RESOLVED`).

## 2. Unit Schema
- `unit_id` (string): Unique identifier for the response vehicle.
- `unit_type` (enum): Unit classification (`AMBULANCE`, `FIRE`, `POLICE`).
- `base_station_id` (string): Station node where the unit originates.
- `current_node_id` (string): Current location node identifier.
- `status` (enum): Operational state (`IDLE`, `EN_ROUTE`, `ON_SCENE`, `OFFLINE`).

## 3. Event & Failure Injection Schemas
- `ROAD_CLOSURE`: `{ "edge_id": string, "is_closed": boolean }`
- `UNIT_OFFLINE`: `{ "unit_id": string, "status": "OFFLINE" }`
- `HOSPITAL_CAPACITY_UPDATE`: `{ "hospital_id": string, "available_beds": integer }`
