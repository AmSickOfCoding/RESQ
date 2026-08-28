"""
RESQ - Simulation engine.

OWNER: Partner D (System Core).

This is the heart of the system. It owns simulated time and it is the ONLY
place where the world is mutated. Every tick it runs the same pipeline:

    1. release any incidents whose report time has arrived
    2. ask Partner A to order the waiting incidents
    3. ask Partner B to choose a unit for each waiting incident, in that order
    4. ask Partner C for the route for each newly assigned unit
    5. advance every moving unit along its route
    6. handle arrivals: on-scene work, hospital transport, resolution
    7. write everything to the audit log

Because the three components arrive through the constructor, swapping a stub
for a real implementation is a one-line change in main.py and needs no edit
here. That is the whole point of the design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .audit import AuditLog, DecisionRecord
from .models import (
    Incident,
    IncidentStatus,
    ResponseUnit,
    UnitStatus,
)
from .results import ErrorCode
from .world import World


@dataclass
class EngineConfig:
    """Tunable simulation settings. Kept in one place so scenarios can vary them."""

    tick_seconds: float = 30.0        # one tick of simulated time
    max_ticks: int = 2000             # safety stop
    unit_returns_home: bool = True    # idle units drive back to their station
    abandon_after_seconds: float = 3600.0  # give up on an unservable incident


class Engine:
    """Runs the simulation. Holds no decision logic of its own by design."""

    def __init__(
        self,
        world: World,
        prioritizer,
        dispatcher,
        router,
        config: Optional[EngineConfig] = None,
        audit: Optional[AuditLog] = None,
        repository=None,
    ) -> None:
        self.world = world
        self.prioritizer = prioritizer
        self.dispatcher = dispatcher
        self.router = router
        self.config = config or EngineConfig()
        self.audit = audit or AuditLog()

        # Optional persistence. Deliberately untyped and optional: the engine
        # only ever calls named methods on it and never imports sqlite3, so the
        # storage layer can be swapped without touching this file. With None
        # passed, behaviour is byte-for-byte what it was before persistence
        # existed - which is what keeps the original seven tests honest.
        self.repository = repository

        self.now: float = 0.0
        self.tick_count: int = 0
        # incidents not yet released into the world, keyed by report time
        self._pending_spawns: List[Incident] = []
        # how many incidents the operator has spawned by hand, so injected
        # calls get stable ids (INJ-01, INJ-02, ...) rather than random ones
        self._injected_count: int = 0

    # ------------------------------------------------------------------
    # SETUP
    # ------------------------------------------------------------------

    def schedule_incident(self, incident: Incident) -> None:
        """Queue an incident to appear at its reported_at time."""
        self._pending_spawns.append(incident)
        self._pending_spawns.sort(key=lambda i: i.reported_at)

    def _log(self, component: str, action: str, **kwargs) -> None:
        record = self.audit.log(DecisionRecord(sim_time=self.now,
                                               component=component,
                                               action=action, **kwargs))
        # Every decision in the system funnels through here, so this one line
        # is the whole write path for the audit trail.
        if self.repository is not None:
            self.repository.save_decision(record)

    def _persist_state(self) -> None:
        """Snapshot every incident and unit. Called once per tick, so a run
        that is interrupted still has everything up to the last completed tick."""
        if self.repository is None:
            return
        for incident in self.world.incidents.values():
            self.repository.save_incident(incident, self.now)
        for unit in self.world.units.values():
            self.repository.save_unit_state(unit, self.now)
        self.repository.commit()

    def _persist_event(self, kind: str, **detail) -> None:
        """Record an operator-injected failure separately from decisions, so
        'what did the instructor break' is one query rather than a text search."""
        if self.repository is not None:
            self.repository.save_world_event(self.now, kind, detail)

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    def run(self, until: Optional[float] = None) -> None:
        """Run until everything is finished, or until a given sim time."""
        while self.tick_count < self.config.max_ticks:
            if until is not None and self.now >= until:
                break
            if until is None and self._is_finished():
                break
            self.tick()

    def tick(self) -> None:
        """Advance the world by exactly one tick."""
        self.tick_count += 1
        self.now += self.config.tick_seconds

        self._spawn_due_incidents()
        self._prioritize_and_dispatch()
        self._advance_units()
        self._expire_stale_incidents()
        self._persist_state()

    def _is_finished(self) -> bool:
        """Nothing left to spawn and nothing left in flight."""
        if self._pending_spawns:
            return False
        active = [
            i for i in self.world.incidents.values()
            if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.FAILED)
        ]
        return not active

    # ------------------------------------------------------------------
    # STEP 1 - spawn
    # ------------------------------------------------------------------

    def _spawn_due_incidents(self) -> None:
        while self._pending_spawns and self._pending_spawns[0].reported_at <= self.now:
            incident = self._pending_spawns.pop(0)
            self.world.incidents[incident.incident_id] = incident
            incident.status = IncidentStatus.REPORTED
            self._log("ENGINE", "INCIDENT_REPORTED",
                      incident_id=incident.incident_id,
                      rationale=(f"{incident.incident_type.value} at "
                                 f"{incident.node_id}, {incident.victims} victim(s)."))

    # ------------------------------------------------------------------
    # STEPS 2-4 - prioritize, dispatch, route
    # ------------------------------------------------------------------

    def _waiting_incidents(self) -> List[Incident]:
        return [
            i for i in self.world.incidents.values()
            if i.status in (IncidentStatus.REPORTED, IncidentStatus.QUEUED)
        ]

    def _prioritize_and_dispatch(self) -> None:
        waiting = self._waiting_incidents()
        if not waiting:
            return

        # --- STEP 2: Partner A orders the queue -------------------------
        ordered = self.prioritizer.prioritize(waiting, self.world, self.now)
        self._log("PRIORITIZER", "ORDER_QUEUE",
                  rationale=(f"{len(ordered)} waiting -> " +
                             ", ".join(i.incident_id for i in ordered)),
                  extra={"order": [i.incident_id for i in ordered]})

        # --- STEP 3: Partner B picks a unit for each, in that order -----
        for incident in ordered:
            decision = self.dispatcher.select_unit(
                incident, self.world, self.router, self.now
            )
            self._log(
                "DISPATCHER", "SELECT_UNIT",
                incident_id=incident.incident_id,
                chosen=decision.unit_id,
                rationale=decision.rationale,
                error=decision.error.value,
                considered=[c.__dict__ for c in decision.considered],
                extra={"severity": incident.severity_score,
                       "rank": incident.priority_rank},
            )

            if not decision.ok:
                # Nothing free right now. It stays queued and we try again
                # next tick - this is what produces realistic waiting under
                # the high-demand scenario.
                incident.status = IncidentStatus.QUEUED
                continue

            unit = self.world.units[decision.unit_id]

            # --- STEP 4: Partner C routes it ---------------------------
            route_result = self.router.find_route(
                unit.current_node, incident.node_id, self.world, self.now
            )
            self._log(
                "ROUTER", "FIND_ROUTE",
                incident_id=incident.incident_id,
                unit_id=unit.unit_id,
                chosen=" > ".join(route_result.route.node_path) if route_result.ok else None,
                rationale=route_result.rationale,
                error=route_result.error.value,
                extra={"eta_seconds": route_result.route.total_seconds
                       if route_result.ok else None},
            )

            if not route_result.ok:
                # The unit exists but cannot physically get there. Leave the
                # incident queued so a different unit can be tried next tick.
                incident.status = IncidentStatus.QUEUED
                continue

            self._assign(unit, incident, route_result.route)

    def _assign(self, unit: ResponseUnit, incident: Incident, route) -> None:
        """Apply a dispatch decision. Only the engine does this."""
        unit.status = UnitStatus.EN_ROUTE
        unit.assigned_incident_id = incident.incident_id
        unit.route = route
        unit.seconds_into_route = 0.0

        incident.status = IncidentStatus.ASSIGNED
        incident.assigned_unit_id = unit.unit_id
        incident.assigned_at = self.now

        self._log("ENGINE", "ASSIGNED", incident_id=incident.incident_id,
                  unit_id=unit.unit_id,
                  rationale=(f"{unit.unit_id} dispatched, ETA "
                             f"{route.total_seconds:.0f}s."))

    # ------------------------------------------------------------------
    # STEP 5 - movement
    # ------------------------------------------------------------------

    def _advance_units(self) -> None:
        for unit in list(self.world.units.values()):
            if unit.status in (UnitStatus.EN_ROUTE, UnitStatus.TRANSPORTING,
                               UnitStatus.RETURNING):
                self._move(unit)
                unit.total_busy_seconds += self.config.tick_seconds
            elif unit.status == UnitStatus.ON_SCENE:
                unit.total_busy_seconds += self.config.tick_seconds
                if unit.busy_until is not None and self.now >= unit.busy_until:
                    self._finish_on_scene(unit)

    def _move(self, unit: ResponseUnit) -> None:
        """Advance a unit along its route by one tick of travel."""
        if unit.route is None:
            return

        unit.seconds_into_route += self.config.tick_seconds * unit.speed_factor
        unit.current_node = self._position_on_route(unit)

        if unit.seconds_into_route >= unit.route.total_seconds:
            unit.current_node = unit.route.destination
            self._on_arrival(unit)

    def _position_on_route(self, unit: ResponseUnit) -> str:
        """
        Which node the unit has most recently passed.

        We report position at node granularity: a unit part-way along an edge is
        still reported at the node it left. Good enough for dispatch decisions
        and it keeps re-routing simple, because we always recompute from a real
        node rather than from the middle of a road.
        """
        route = unit.route
        travelled = 0.0
        for i in range(len(route.node_path) - 1):
            edge = self.world.edge_between(route.node_path[i], route.node_path[i + 1])
            step = edge.base_seconds if edge else 0.0
            if travelled + step > unit.seconds_into_route:
                return route.node_path[i]
            travelled += step
        return route.node_path[-1]

    # ------------------------------------------------------------------
    # STEP 6 - arrivals and resolution
    # ------------------------------------------------------------------

    def _on_arrival(self, unit: ResponseUnit) -> None:
        if unit.status == UnitStatus.EN_ROUTE:
            self._arrive_at_incident(unit)
        elif unit.status == UnitStatus.TRANSPORTING:
            self._arrive_at_hospital(unit)
        elif unit.status == UnitStatus.RETURNING:
            unit.status = UnitStatus.AVAILABLE
            unit.route = None
            unit.seconds_into_route = 0.0

    def _arrive_at_incident(self, unit: ResponseUnit) -> None:
        incident = self.world.incidents[unit.assigned_incident_id]
        incident.status = IncidentStatus.ON_SCENE
        incident.arrived_at = self.now

        unit.status = UnitStatus.ON_SCENE
        unit.busy_until = self.now + incident.service_seconds
        unit.route = None
        unit.seconds_into_route = 0.0

        self._log("ENGINE", "ON_SCENE", incident_id=incident.incident_id,
                  unit_id=unit.unit_id,
                  rationale=(f"Arrived after {incident.response_seconds:.0f}s. "
                             f"Working for {incident.service_seconds:.0f}s."))

    def _finish_on_scene(self, unit: ResponseUnit) -> None:
        """On-scene work is done. Either transport a patient or close the call."""
        incident = self.world.incidents[unit.assigned_incident_id]

        if not incident.requires_transport:
            self._resolve(incident, unit)
            return

        # --- ask Partner C where to take the patient -------------------
        decision = self.router.best_destination(
            unit.current_node, self.world, incident.required_capabilities, self.now
        )
        self._log("ROUTER", "BEST_DESTINATION", incident_id=incident.incident_id,
                  unit_id=unit.unit_id, chosen=decision.node_id,
                  rationale=decision.rationale, error=decision.error.value,
                  considered=[c.__dict__ for c in decision.considered])

        if not decision.ok:
            # Every hospital full or unreachable. The call fails, and the log
            # explains exactly why - this is a demo talking point, not a crash.
            incident.failure_reason = decision.rationale
            self._resolve(incident, unit, failed=True)
            return

        hospital = self.world.hospitals[decision.node_id]
        hospital.occupied += 1

        incident.status = IncidentStatus.TRANSPORTING
        incident.destination_hospital = decision.node_id
        unit.status = UnitStatus.TRANSPORTING
        unit.route = decision.route
        unit.seconds_into_route = 0.0
        unit.busy_until = None

    def _arrive_at_hospital(self, unit: ResponseUnit) -> None:
        incident = self.world.incidents[unit.assigned_incident_id]
        self._log("ENGINE", "HANDOVER", incident_id=incident.incident_id,
                  unit_id=unit.unit_id,
                  rationale=(f"Patient delivered to "
                             f"{self.world.hospitals[unit.current_node].name}."))
        self._resolve(incident, unit)

    def _resolve(self, incident: Incident, unit: ResponseUnit,
                 failed: bool = False) -> None:
        incident.status = IncidentStatus.FAILED if failed else IncidentStatus.RESOLVED
        incident.resolved_at = self.now

        unit.assigned_incident_id = None
        unit.busy_until = None
        unit.seconds_into_route = 0.0

        self._log("ENGINE", "FAILED" if failed else "RESOLVED",
                  incident_id=incident.incident_id, unit_id=unit.unit_id,
                  rationale=incident.failure_reason or
                  f"Closed after {self.now - incident.reported_at:.0f}s total.")

        # send the unit home, or free it where it stands
        if self.config.unit_returns_home and unit.current_node != unit.home_station:
            result = self.router.find_route(unit.current_node, unit.home_station,
                                            self.world, self.now)
            if result.ok:
                unit.status = UnitStatus.RETURNING
                unit.route = result.route
                return
        unit.status = UnitStatus.AVAILABLE
        unit.route = None

    # ------------------------------------------------------------------
    # STEP 7 - give up on incidents nobody can serve
    # ------------------------------------------------------------------

    def _expire_stale_incidents(self) -> None:
        for incident in self.world.incidents.values():
            if incident.status != IncidentStatus.QUEUED:
                continue
            waited = self.now - incident.reported_at
            if waited >= self.config.abandon_after_seconds:
                incident.status = IncidentStatus.FAILED
                incident.resolved_at = self.now
                incident.failure_reason = (
                    f"Abandoned after waiting {waited:.0f}s with no unit available."
                )
                self._log("ENGINE", "ABANDONED", incident_id=incident.incident_id,
                          rationale=incident.failure_reason)

    # ------------------------------------------------------------------
    # LIVE FAILURE INJECTION  (the instructor drives these during the demo)
    # ------------------------------------------------------------------

    def inject_close_road(self, a: str, b: str) -> None:
        """Close a road and immediately re-route anyone who was using it."""
        changed = self.world.close_road(a, b)
        self._log("ENGINE", "INJECT_ROAD_CLOSED",
                  rationale=f"Road {a}<->{b} closed by operator.",
                  extra={"edges": changed})
        self._persist_event("ROAD_CLOSED", a=a, b=b, edges=changed)
        self._reroute_affected(changed)

    def inject_restore_road(self, a: str, b: str) -> None:
        """
        Re-open a closed road. Section 9 of the brief asks for a restore
        control alongside the break controls.

        No re-routing is forced here on purpose. Opening a road only ever adds
        options, and any incident that was left QUEUED by the closure is retried
        on the next tick anyway - so the recovery is visible in the log as a
        normal dispatch rather than as a special case.
        """
        changed = self.world.open_road(a, b)
        self._log("ENGINE", "INJECT_ROAD_RESTORED",
                  rationale=(f"Road {a}<->{b} re-opened by operator."
                             if changed else
                             f"Road {a}<->{b} was already open."),
                  extra={"edges": changed})
        self._persist_event("ROAD_RESTORED", a=a, b=b, edges=changed)

    def inject_spawn_incident(
        self,
        node_id: str,
        incident_type,
        required_unit,
        victims: int = 1,
        requires_transport: bool = True,
        service_seconds: float = 300.0,
        incident_id: Optional[str] = None,
    ) -> Incident:
        """
        Create one new emergency while the simulation is running.

        Goes through schedule_incident like every other incident, so it appears
        on the next tick and travels the normal pipeline. Nothing about a
        hand-spawned call is special, which is exactly the point: the demo
        proves the system reacts to new state rather than to a script.
        """
        self._injected_count += 1
        incident = Incident(
            incident_id=incident_id or f"INJ-{self._injected_count:02d}",
            node_id=node_id,
            incident_type=incident_type,
            reported_at=self.now,
            required_unit=required_unit,
            victims=victims,
            requires_transport=requires_transport,
            service_seconds=service_seconds,
        )
        self.schedule_incident(incident)
        self._log("ENGINE", "INJECT_INCIDENT", incident_id=incident.incident_id,
                  rationale=(f"Operator spawned {incident_type.value} at "
                             f"{node_id}, {victims} victim(s)."))
        self._persist_event("INCIDENT_SPAWNED",
                            incident_id=incident.incident_id,
                            node_id=node_id, victims=victims)
        return incident

    def inject_traffic(self, a: str, b: str, multiplier: float) -> None:
        changed = self.world.set_traffic(a, b, multiplier)
        self._log("ENGINE", "INJECT_TRAFFIC",
                  rationale=f"Traffic on {a}<->{b} set to x{multiplier}.",
                  extra={"edges": changed})
        self._persist_event("TRAFFIC", a=a, b=b, multiplier=multiplier,
                            edges=changed)
        self._reroute_affected(changed)

    def inject_fill_hospital(self, node_id: str) -> None:
        ok = self.world.fill_hospital(node_id)
        self._log("ENGINE", "INJECT_HOSPITAL_FULL", chosen=node_id,
                  rationale=("Hospital marked full by operator."
                             if ok else "Unknown hospital id."))
        self._persist_event("HOSPITAL_FULL", node_id=node_id, applied=ok)

    def inject_disable_unit(self, unit_id: str) -> None:
        """Take a unit out of service, releasing its incident back to the queue."""
        unit = self.world.units.get(unit_id)
        if unit is None:
            return
        freed = unit.assigned_incident_id
        if freed:
            incident = self.world.incidents[freed]
            incident.status = IncidentStatus.QUEUED
            incident.assigned_unit_id = None
            incident.assigned_at = None

        unit.status = UnitStatus.OUT_OF_SERVICE
        unit.route = None
        unit.assigned_incident_id = None
        self._log("ENGINE", "INJECT_UNIT_DISABLED", unit_id=unit_id,
                  incident_id=freed,
                  rationale=(f"{unit_id} out of service; "
                             f"{freed or 'no incident'} returned to queue."))
        self._persist_event("UNIT_DISABLED", unit_id=unit_id,
                            released_incident=freed)

    def _reroute_affected(self, changed_edges: List[str]) -> None:
        """
        Any unit whose current route uses a changed edge gets a fresh route from
        wherever it is now. This is the resilience requirement in Section 5.
        """
        changed = set(changed_edges)
        for unit in self.world.units.values():
            if unit.route is None or not (set(unit.route.edge_keys) & changed):
                continue

            destination = unit.route.destination
            result = self.router.find_route(unit.current_node, destination,
                                            self.world, self.now)
            self._log("ROUTER", "REROUTE", unit_id=unit.unit_id,
                      incident_id=unit.assigned_incident_id,
                      chosen=" > ".join(result.route.node_path) if result.ok else None,
                      rationale=result.rationale, error=result.error.value)

            if result.ok:
                unit.route = result.route
                unit.seconds_into_route = 0.0
            else:
                # Cannot reach the destination any more. Release the incident so
                # another unit can be tried, and free this one.
                if unit.assigned_incident_id:
                    incident = self.world.incidents[unit.assigned_incident_id]
                    incident.status = IncidentStatus.QUEUED
                    incident.assigned_unit_id = None
                unit.status = UnitStatus.AVAILABLE
                unit.route = None
                unit.assigned_incident_id = None
