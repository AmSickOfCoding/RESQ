# CLAUDE.md — RESQ

Standing context for this repository. Read this before touching anything.

Repo: `AmSickOfCoding/RESQ`
My branch: `faris/system-core` — all my work happens here, then merges to the
shared branch by pull request. Never commit directly to the shared branch.

**Also read `PROJECT_BRIEF.md` at the repo root before your first task in a
session.** It holds the full capstone requirements: the nine required
capabilities, the collaboration rules, the three simulation modes, failure
injection, all nine deliverables, the six milestones, the grading rubric, and
the individual defence rule. This file is the short version; that one is the
source of truth for what the project must do.

---

## 1. What the system is

RESQ is a simulated emergency-response digital twin, built as a university
capstone by a four-person team.

A city is modelled as a graph of nodes and roads. Emergencies appear over
simulated time. For each one the system must decide, live: which incident to
handle first, which response unit to send, what route that unit takes, and where
to transport a patient. Then the world changes underneath it — roads close,
traffic builds, hospitals fill, units break down — and the system has to adapt
without anyone editing code.

During the demo the instructor drives those failures himself, from the running
UI, and asks the system to justify its decisions after the fact.

### Grading weights

These drive design decisions, so they are worth knowing:

- Integrated functionality — 20
- Decision quality — 20
- Architecture and code structure — 15
- Data and persistence — 10
- Resilience and failure handling — 10
- Testing — 10
- Collaboration and repository practice — 10
- Documentation and demo — 5

### Two rules from the brief that shape everything

1. **"Nearest unit wins" is explicitly not enough.** Every decision must weigh
   multiple competing factors, and the reasoning must be recoverable later.
2. **No component gets full credit for working in isolation.** Integration is
   itself a graded deliverable.

---

## 2. The team and my role

Four members. Three own decision logic; I own the system it lives inside.

- **Partner A** — severity scoring, explainable scoring, incident prioritization
- **Partner B** — resource allocation, unit selection, dispatch logic
- **Partner C** — dynamic graph modelling, routing, destination optimization
- **Me, Partner D — System Core:** architecture, simulation engine, persistence,
  UI, integration, audit, testing and CI

My three teammates each write one class implementing one protocol from
`resq/interfaces.py`, in their own folder, on their own branch. They plug in by
changing one line in `main.py`. Nothing in the engine changes.

---

## 3. Stack and conventions

Python 3.9+. The core is dependency-free and I want it to stay that way so
teammates can clone and run with zero setup. Persistence will use SQLite from
the standard library.

- **Node IDs** — short uppercase strings. `N01` intersections, `ST1` stations,
  `H1` hospitals. Locations are never referred to by name or list index.
- **Time** — simulation seconds as floats. Default tick is 30s.
- **Cost** — every travel figure is in seconds. Never metres, never hop counts.
- **Errors** — one shared `ErrorCode` enum in `resq/results.py`.

---

## 4. What already exists and passes

```
resq/models.py       shared dataclasses and enums — the integration contract
resq/results.py      ErrorCode, DispatchDecision, RouteResult, DestinationDecision
resq/world.py        city graph, live mutation hooks, sample city builder
resq/interfaces.py   the three Protocols A, B and C implement
resq/engine.py       clock, tick pipeline, movement, arrivals, failure injection
resq/audit.py        DecisionRecord and AuditLog
resq/scenarios.py    the three required modes plus the metrics collector
resq/stubs/naive.py  deliberately weak stand-ins for A, B and C
main.py              console runner and component wiring
tests/test_integration.py   7 integration tests, all passing
```

Verify before changing anything:

```bash
python tests/test_integration.py     # expect 7 passed, 0 failed
python main.py disruption --log
```

### The tick pipeline

Every tick the engine runs the same sequence:

1. release incidents whose report time has arrived
2. **Partner A** orders the waiting queue
3. **Partner B** picks a unit for each waiting incident, in that order
4. **Partner C** routes each newly assigned unit
5. advance every moving unit along its route
6. handle arrivals: on-scene work, hospital transport, resolution
7. write every decision to the audit log

---

## 5. Non-negotiable design rules

Do not violate these even when a shortcut looks cleaner.

1. **The engine is the only thing that mutates the world.** Components read
   state and return a decision object; the engine applies it. This is what keeps
   the audit trail truthful, and the audit trail is graded.
2. **No exceptions for expected conditions.** No free unit, no path, no hospital
   with space — return the result object carrying the matching `ErrorCode`.
   Exceptions are for real bugs only.
3. **Every decision carries a `rationale` string and a `considered` list.**
   "Picked A3" is worth nothing. "Picked A3 over A1 because A1 covers the only
   northern station" is where the 20 decision-quality marks come from.
4. **Determinism.** The three scenarios must reproduce exactly, or the
   before/after metrics comparison proves nothing. Randomness takes a seeded
   `Random` from the engine.
5. **Components plug in through the constructor.** Adding a real implementation
   must never require editing `engine.py`. If it does, the abstraction is wrong.
6. **Do not improve the stubs in `resq/stubs/naive.py`.** They are intentionally
   naive — FIFO ordering, first-free unit, fewest-hops routing. They are the
   baseline the real implementations must beat, and improving them means doing
   my teammates' graded work.
7. **Do not write code in `partner_a/`, `partner_b/`, `partner_c/`.** If
   something there is broken or missing, tell me and I will raise it with them.

---

## 6. MY WORK — the System Core breakdown

Seven areas. Roughly 55 of the 100 marks run through these.

### 6.1 Architecture

Owned, largely done, but ongoing.

- The integration contract in `models.py`, `results.py`, `interfaces.py` — one
  definition of every shared object, no local redefinitions anywhere.
- Dependency injection: engine receives A, B and C as constructor arguments.
- Keep the core dependency-free.
- Remaining: architecture diagram, data model documentation, and a written
  explanation of why the contract is shaped the way it is.

### 6.2 Simulation engine

Owned, working, needs hardening.

- Clock, tick loop, and the seven-step pipeline above — done.
- Movement along routes at node granularity — done.
- Incident lifecycle: REPORTED → QUEUED → ASSIGNED → ON_SCENE → TRANSPORTING →
  RESOLVED / FAILED — done.
- Unit lifecycle including return-to-station — done.
- Failure injection: `inject_close_road`, `inject_traffic`,
  `inject_fill_hospital`, `inject_disable_unit`, with automatic re-routing of
  affected units — done.
- Still to do: replace the hardcoded sample city with a JSON map loader, add a
  configurable seed, and support pause/step/resume so the demo can be driven
  interactively rather than only run to completion.

### 6.3 Persistence — NEXT INCREMENT

Nothing exists yet. Worth 10 marks.

- `resq/storage.py`, SQLite via the standard library, no ORM.
- Tables: runs, incidents, units, decision records, world events.
- A `Repository` class with a narrow API: `start_run`, `save_incident`,
  `save_unit_state`, `save_decision`, `finish_run`, plus `list_runs`,
  `load_run`, `decisions_for_incident`.
- The engine takes an optional repository. With none passed, behaviour is
  identical to today. The engine must never import sqlite3 directly.
- `--save` and `--runs` flags on main.py.
- Acceptance: run a scenario, exit the process, restart, and the full decision
  chain for a given incident is still readable from the database.

### 6.4 Operator UI

Nothing exists yet. Feeds both the functionality and documentation marks.

- Live view: map or node list, active incidents with status, unit states, the
  waiting queue, the simulation clock.
- Scenario selector for the three required modes.
- Failure injection controls — close/restore a road, set traffic, disable a
  unit, fill a hospital, spawn one critical incident, spawn a burst. These call
  the real engine methods. They never fake the display.
- Pause, step, resume, and speed control.
- Must be usable by someone who has never seen the code, because the instructor
  will drive it.
- I prefer a GUI over a terminal interface. Decide the approach with me before
  building — I do not want a web framework dragged in without discussion.

### 6.5 Audit and explainability

Partly built. This is what protects me in the live demo.

- `DecisionRecord` and `AuditLog` — done.
- Every decision already logs component, action, chosen option, rationale,
  error code and rejected alternatives.
- Still to do: an audit screen where you pick any incident and see its complete
  decision chain — timestamps, inputs, what was chosen, why, and what was
  rejected and why. When the instructor asks "why did it send that unit", we
  open a screen instead of scrolling through code.
- Also to do: export a single incident's chain as readable text for the report.

### 6.6 Integration

Ongoing, and the highest-risk part of the project.

- The stubs let the full pipeline run today, so nobody is blocked.
- When a teammate delivers, merge **one at a time** — A, run the full suite,
  confirm green, then B, then C. Never all three at once, or a failure cannot be
  attributed.
- Every merge adds at least one integration test.
- Their real implementations must satisfy the same tests the stubs do. If a
  teammate needs the engine changed to accommodate them, that is a contract
  conversation, not a quiet edit.
- Watch specifically for B computing distance itself instead of calling C's
  router. If those two disagree, the demo contradicts itself.

### 6.7 Testing and CI

7 integration tests pass. Worth 10 marks plus part of collaboration.

- Existing coverage: end-to-end resolution, audit completeness, reroute on road
  closure, clean NO_ROUTE handling, unit disabling returning its incident to the
  queue, full-hospital diversion, and all three scenarios completing.
- To add: persistence tests, determinism tests (same scenario twice, identical
  results), and a test per teammate merge.
- GitHub Actions running the suite on every pull request to the shared branch.
- The seven existing tests must keep passing **unchanged**. If new work requires
  editing them, the design is leaking and I want to know.

### 6.8 My depth contribution — metrics and comparison

Important for my individual defence. The other three own the algorithmic marks;
this is mine.

- Run the same scenario under two configurations and report side by side:
  average response time, worst response time, resolution rate, failure reasons,
  unit utilization.
- Concretely: stubs versus real implementations, proving the team's logic
  actually improves outcomes rather than just existing.
- This turns my contribution from plumbing into measurement, which is what I
  will be asked about individually.

---

## 7. Delivery order

1. Persistence ← current
2. Operator UI
3. Failure injection controls in the UI
4. Audit screen
5. Metrics and comparison mode
6. CI on pull requests
7. Documentation: README, architecture diagram, data model, decision-logic
   writeup

Do not jump ahead. Each one gets reviewed before the next starts.

---

## 8. How I want you to work with me

- **Incremental delivery.** One feature at a time, verified working before
  moving on. Do not build three things and hand me a pile.
- **Comment code properly.** Explain why, not just what. My teammates read this
  code to understand the contract, and I learn from the comments.
- **Numbered steps** when giving me instructions.
- **Run the tests after every change.** Seven pass now; that number only goes up.
- **Prefer a GUI** where a real choice exists.
- **Push back on me.** If something I ask for is a bad idea, say so now rather
  than letting me find out during the demo.
