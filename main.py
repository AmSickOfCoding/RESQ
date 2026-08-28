"""
RESQ - Console runner.

OWNER: Partner D (System Core).

    python main.py                 # normal operations, quiet
    python main.py rush --log      # high demand, printing every decision
    python main.py disruption --log

THIS IS THE ONLY FILE A, B AND C NEED TO EDIT TO PLUG IN.
When your component is ready, import it and swap the one line below. Nothing in
the engine changes.
"""

from __future__ import annotations

import argparse
import sys

from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.scenarios import ALL_SCENARIOS, collect_metrics

# --- COMPONENT WIRING ------------------------------------------------------
# Replace a stub with the real class when its owner delivers. One line each.
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher

# from partner_a.severity import SeverityPrioritizer      # TODO(A)
# from partner_b.dispatch import MultiFactorDispatcher    # TODO(B)
# from partner_c.routing import DijkstraRouter            # TODO(C)

PRIORITIZER = FifoPrioritizer()      # TODO(A): -> SeverityPrioritizer()
DISPATCHER = FirstFreeDispatcher()   # TODO(B): -> MultiFactorDispatcher()
ROUTER = BfsRouter()                 # TODO(C): -> DijkstraRouter()
# ---------------------------------------------------------------------------


def run(scenario_key: str, verbose: bool) -> int:
    if scenario_key not in ALL_SCENARIOS:
        print(f"Unknown scenario '{scenario_key}'. "
              f"Choose one of: {', '.join(ALL_SCENARIOS)}")
        return 1

    scenario = ALL_SCENARIOS[scenario_key]()
    audit = AuditLog(echo=verbose)

    engine = Engine(
        world=scenario.world,
        prioritizer=PRIORITIZER,
        dispatcher=DISPATCHER,
        router=ROUTER,
        config=EngineConfig(tick_seconds=30.0),
        audit=audit,
    )

    for incident in scenario.incidents:
        engine.schedule_incident(incident)

    print("=" * 72)
    print(f"RESQ  |  {scenario.name}")
    print(f"        {scenario.description}")
    print(f"        prioritizer={PRIORITIZER.name}  dispatcher={DISPATCHER.name}")
    print(f"        router={ROUTER.name}")
    print("=" * 72)

    # Run tick by tick so timed failure injections fire at the right moment.
    pending_events = sorted(scenario.events, key=lambda e: e[0])
    while not engine._is_finished() and engine.tick_count < engine.config.max_ticks:
        while pending_events and pending_events[0][0] <= engine.now:
            _, action = pending_events.pop(0)
            action(engine)
        engine.tick()

    print("-" * 72)
    print(collect_metrics(engine, scenario.name).as_text())
    print("-" * 72)

    if not verbose:
        print("Run again with --log to see every decision, "
              "or --explain INC-01 for one incident's chain.")
    return 0


def explain(scenario_key: str, incident_id: str) -> int:
    """Print the full decision chain for one incident - the audit view in text
    form, before the real UI exists."""
    scenario = ALL_SCENARIOS[scenario_key]()
    engine = Engine(scenario.world, PRIORITIZER, DISPATCHER, ROUTER,
                    audit=AuditLog(echo=False))
    for incident in scenario.incidents:
        engine.schedule_incident(incident)

    pending_events = sorted(scenario.events, key=lambda e: e[0])
    while not engine._is_finished() and engine.tick_count < engine.config.max_ticks:
        while pending_events and pending_events[0][0] <= engine.now:
            _, action = pending_events.pop(0)
            action(engine)
        engine.tick()

    records = engine.audit.for_incident(incident_id)
    if not records:
        print(f"No records for {incident_id}.")
        return 1

    print(f"Decision chain for {incident_id}")
    print("=" * 72)
    for record in records:
        print(record.as_line())
        for candidate in record.considered:
            print(f"{'':>13}   rejected {candidate['option_id']}: "
                  f"{candidate['reason']}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RESQ simulation runner")
    parser.add_argument("scenario", nargs="?", default="normal",
                        choices=list(ALL_SCENARIOS))
    parser.add_argument("--log", action="store_true",
                        help="print every decision as it happens")
    parser.add_argument("--explain", metavar="INCIDENT_ID",
                        help="show the full decision chain for one incident")
    args = parser.parse_args()

    if args.explain:
        sys.exit(explain(args.scenario, args.explain))
    sys.exit(run(args.scenario, args.log))
