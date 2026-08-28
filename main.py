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
import os
import sys

from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.scenarios import ALL_SCENARIOS, collect_metrics
from resq.storage import Repository

DEFAULT_DB = "resq.db"

# --- COMPONENT WIRING ------------------------------------------------------
# One line each, exactly as designed. A teammate delivers, their adapter goes
# in resq/adapters/, and the line below changes. Nothing in the engine moves.
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher

from resq.adapters.partner_a import SeverityPrioritizer      # DONE(A)
from resq.adapters.partner_b import AllocationDispatcher     # DONE(B)
# from resq.adapters.partner_c import DijkstraRouter         # TODO(C)

# The real implementations, used by default.
PRIORITIZER = SeverityPrioritizer()
DISPATCHER = AllocationDispatcher()
ROUTER = BfsRouter()                 # TODO(C): still the stub - C has not shipped

# The deliberately weak baseline. --stubs swaps all three back, which is what
# makes the before/after metrics comparison possible.
STUB_PRIORITIZER = FifoPrioritizer()
STUB_DISPATCHER = FirstFreeDispatcher()
STUB_ROUTER = BfsRouter()
# ---------------------------------------------------------------------------


def components(use_stubs: bool = False):
    """Which three components this run uses."""
    if use_stubs:
        return STUB_PRIORITIZER, STUB_DISPATCHER, STUB_ROUTER
    return PRIORITIZER, DISPATCHER, ROUTER


def run(scenario_key: str, verbose: bool, save: bool = False,
        db_path: str = DEFAULT_DB, use_stubs: bool = False) -> int:
    if scenario_key not in ALL_SCENARIOS:
        print(f"Unknown scenario '{scenario_key}'. "
              f"Choose one of: {', '.join(ALL_SCENARIOS)}")
        return 1

    scenario = ALL_SCENARIOS[scenario_key]()
    audit = AuditLog(echo=verbose)
    prioritizer, dispatcher, router = components(use_stubs)

    # Persistence is opt-in. Without --save the engine gets None and behaves
    # exactly as it did before storage.py existed.
    repository = None
    if save:
        repository = Repository(db_path)
        repository.start_run(
            scenario=scenario_key,
            prioritizer=prioritizer.name,
            dispatcher=dispatcher.name,
            router=router.name,
            tick_seconds=30.0,
        )

    engine = Engine(
        world=scenario.world,
        prioritizer=prioritizer,
        dispatcher=dispatcher,
        router=router,
        config=EngineConfig(tick_seconds=30.0),
        audit=audit,
        repository=repository,
    )

    for incident in scenario.incidents:
        engine.schedule_incident(incident)

    print("=" * 72)
    print(f"RESQ  |  {scenario.name}")
    print(f"        {scenario.description}")
    print(f"        prioritizer={prioritizer.name}")
    print(f"        dispatcher={dispatcher.name}")
    print(f"        router={router.name}")
    print("=" * 72)

    # Run tick by tick so timed failure injections fire at the right moment.
    pending_events = sorted(scenario.events, key=lambda e: e[0])
    while not engine._is_finished() and engine.tick_count < engine.config.max_ticks:
        while pending_events and pending_events[0][0] <= engine.now:
            _, action = pending_events.pop(0)
            action(engine)
        engine.tick()

    print("-" * 72)
    metrics = collect_metrics(engine, scenario.name)
    print(metrics.as_text())
    print("-" * 72)

    if repository is not None:
        repository.finish_run(
            sim_seconds=engine.now,
            ticks=engine.tick_count,
            resolved=metrics.resolved,
            failed=metrics.failed,
        )
        run_id = repository.run_id
        repository.close()
        print(f"Saved as run {run_id} in {db_path}. "
              f"List past runs with:  python main.py --runs")

    if not verbose:
        print("Run again with --log to see every decision, "
              "or --explain INC-01 for one incident's chain.")
    return 0


def list_runs(db_path: str = DEFAULT_DB) -> int:
    """Show what is already in the database. Proves persistence at a glance."""
    if not os.path.exists(db_path):
        print(f"No database at {db_path}. "
              f"Run a scenario with --save first.")
        return 1

    repository = Repository(db_path)
    runs = repository.list_runs()
    if not runs:
        print(f"{db_path} exists but holds no runs yet.")
        repository.close()
        return 0

    print(f"{'RUN':>4}  {'SCENARIO':<12} {'STARTED (UTC)':<21} "
          f"{'SIM':>7}  {'TICKS':>5}  {'OK':>3} {'FAIL':>4}  COMPONENTS")
    print("-" * 96)
    for row in runs:
        started = (row["started_at"] or "").replace("T", " ").replace("+00:00", "")
        components = "/".join(
            filter(None, [row["prioritizer"], row["dispatcher"], row["router"]])
        )
        sim = f"{row['sim_seconds']:.0f}s" if row["sim_seconds"] else "-"
        print(f"{row['run_id']:>4}  {row['scenario']:<12} {started:<21} "
              f"{sim:>7}  {str(row['ticks'] or '-'):>5}  "
              f"{str(row['resolved'] or 0):>3} {str(row['failed'] or 0):>4}  "
              f"{components}")

    latest = runs[0]
    chain = repository.load_run(latest["run_id"])
    print("-" * 96)
    print(f"Run {latest['run_id']} holds {len(chain['incidents'])} incidents, "
          f"{len(chain['units'])} units and {len(chain['events'])} injected "
          f"events.")
    print(f"Read one incident's full decision chain with:  "
          f"python main.py --chain {latest['run_id']}:<INCIDENT_ID>")
    repository.close()
    return 0


def show_chain(spec: str, db_path: str = DEFAULT_DB) -> int:
    """Print a stored decision chain, read straight back off the disk.

    This is the persistence acceptance check in human form: the process that
    produced these decisions has long since exited.
    """
    if ":" not in spec:
        print("Use --chain RUN_ID:INCIDENT_ID, for example --chain 1:INC-01")
        return 1
    run_part, incident_id = spec.split(":", 1)

    if not os.path.exists(db_path):
        print(f"No database at {db_path}. Run a scenario with --save first.")
        return 1

    repository = Repository(db_path)
    records = repository.decisions_for_incident(int(run_part), incident_id)
    if not records:
        print(f"No stored decisions for {incident_id} in run {run_part}.")
        repository.close()
        return 1

    print(f"Stored decision chain for {incident_id} (run {run_part})")
    print("=" * 78)
    for record in records:
        stamp = f"[{record['sim_time']:8.0f}s]"
        tail = record["rationale"] or record["error"]
        print(f"{stamp} {record['component']:<11} {record['action']:<18} {tail}")
        for candidate in record["considered"]:
            print(f"{'':>13}   rejected {candidate.get('option_id')}: "
                  f"{candidate.get('reason')}")
    repository.close()
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
    parser.add_argument("--save", action="store_true",
                        help="persist this run to the database")
    parser.add_argument("--runs", action="store_true",
                        help="list runs already stored in the database")
    parser.add_argument("--chain", metavar="RUN_ID:INCIDENT_ID",
                        help="read one stored decision chain back off the disk")
    parser.add_argument("--db", default=DEFAULT_DB, metavar="PATH",
                        help=f"database file (default: {DEFAULT_DB})")
    parser.add_argument("--stubs", action="store_true",
                        help="run the naive baseline instead of the real "
                             "components, for the before/after comparison")
    parser.add_argument("--ui", action="store_true",
                        help="open the operator console (Tk desktop window)")
    args = parser.parse_args()

    if args.ui:
        # Imported here, not at module scope: the console runner and CI must
        # keep working on machines with no display and no Tk.
        from resq.ui import launch
        launch(repository=Repository(args.db) if args.save else None)
        sys.exit(0)
    if args.runs:
        sys.exit(list_runs(args.db))
    if args.chain:
        sys.exit(show_chain(args.chain, args.db))
    if args.explain:
        sys.exit(explain(args.scenario, args.explain))
    sys.exit(run(args.scenario, args.log, save=args.save, db_path=args.db,
                 use_stubs=args.stubs))
