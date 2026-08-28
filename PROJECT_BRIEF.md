# RESQ — Full Project Brief

Everything about this capstone in one place: what the system is, what the team
must build, who owns what, how it is graded, and where we currently stand.

Repo: `AmSickOfCoding/RESQ`
My branch: `faris/system-core` — all my work lands here, then merges to the
shared branch by pull request.

---

## 1. The problem

RESQ is a simulated emergency-response digital twin. The team models a city
containing roads, incidents, response units, stations, and hospitals. During a
live simulation, emergencies appear and the system must decide how to respond
using only the resources currently available.

It has to answer, continuously and on its own:

- Which incident should be handled first?
- Which unit should respond?
- What route should it take?
- Where should a patient be transported?
- What happens when a road closes, a unit disappears, or five calls arrive at once?

The instructor's framing: the objective is not the longest codebase, it is a
system that behaves like one coherent engineering product. It is explicitly not
a CRUD exercise — the value is in decisions, algorithms, changing state,
integration, failure handling, and being able to justify the engineering.

---

## 2. Technology and AI policy

Any language, framework, database, UI technology, AI model, or tool is allowed.
There is no required stack.

AI use is not penalized. **Unexplained work is.** If a student cannot explain,
trace, modify, test, and defend a component, the instructor may treat it as not
demonstrated by that student. That rule drives how this repo is written: heavy
comments, clear responsibilities, no clever code nobody can trace.

---

## 3. The nine required capabilities

The implementation may look completely different from another team's, but the
final system must demonstrate all nine:

1. **World / city model** — locations, roads, units, stations, hospitals, incidents
2. **Incident lifecycle** — create, receive, prioritize, assign, update, resolve, retain
3. **Resource allocation** — choose an appropriate unit by a team-designed rule,
   algorithm, model, or optimization
4. **Routing / movement** — how a unit travels between locations; a graph
   approach is encouraged, not mandatory
5. **Changing conditions** — react to at least three, such as road closures,
   traffic changes, unavailable units, hospital capacity, new incidents
6. **Persistent data** — results survive beyond one program run
7. **Analytics or intelligence** — at least one decision-support feature beyond
   ordinary CRUD: prediction, prioritization, optimization, recommendation, or
   explainable scoring
8. **Human-readable interface** — usable for operating and observing the system;
   web, desktop, terminal, or map UI, whichever we justify
9. **Auditability** — a reviewer must see *why* a decision occurred: inputs,
   selected unit and route, score or rationale, timestamps, and outcome

---

## 4. The engineering challenge

**"Nearest unit wins" is explicitly not enough.** The decision process must weigh
multiple competing factors. Candidates the brief names: incident severity,
number of people affected, waiting time, travel time, incident type, unit
capability, current unit workload, road availability, hospital capacity,
predicted future demand, and special priority rules.

The instructor deliberately gives no formula. Deciding what matters, how it is
represented, and how trade-offs resolve is itself part of the graded work.

### The scenario the brief uses as its example

| Time | Event | Pressure | Expected reaction |
|---|---|---|---|
| 14:01 | Vehicle collision | 1 critical incident | Prioritize and dispatch |
| 14:03 | Second medical emergency | Fewer free units | Re-evaluate allocation |
| 14:05 | Main road closes | Current route invalid | Re-route or reassign |
| 14:06 | Hospital reaches capacity | Destination unavailable | Select another destination |
| 14:08 | Multiple new incidents | Demand exceeds resources | Queue, score, or optimize |

Our disruption scenario already reproduces this shape.

---

## 5. The team

Four members. Three own decision logic; one owns the system it lives inside.

- **Partner A — AI / Data / Analytics.** Severity scoring, explainable scoring,
  incident prioritization. Decides the *order* incidents are handled in.
- **Partner B — Algorithms.** Resource allocation, unit selection, dispatch
  logic. Decides *which unit* goes.
- **Partner C — Algorithms.** Dynamic graph modelling, routing, destination
  optimization. Decides *how it gets there* and *where the patient goes*.
- **Me, Partner D — Software Engineering + Quality/DevOps.** Architecture,
  simulation engine, persistence, UI, integration, audit trail, testing, CI.

Each of the three writes one class implementing one protocol from
`resq/interfaces.py`, in their own folder, on their own branch. They plug in by
changing one line in `main.py`. Nothing in the engine changes.

---

## 6. Collaboration rules from the brief

- One shared repository.
- Every student needs visible, meaningful contributions. Commit count alone is
  not proof.
- Branches for feature work; do not develop major features on the stable branch.
- Pull requests and review before merging significant work.
- Resolve real integration conflicts as a team. Disconnected demos are not
  acceptable.
- Document interfaces so a teammate can use them.
- No secrets, binaries, virtual environments, or large temp files in version
  control.
- **No component receives full credit solely for working in isolation.**

---

## 7. The integration contract

The brief requires the team to agree, before deep implementation, on: what an
incident record contains, what a unit record contains, how status changes are
represented, how components exchange data, how errors are reported, how time is
represented, what is persisted, and how a decision is explained afterwards.

Ours is already written in code:

- `resq/models.py` — the incident and unit records, all enums, the world objects
- `resq/results.py` — the error codes and decision result objects
- `resq/interfaces.py` — the three protocols and the rules binding all of us
- `resq/audit.py` — how a decision is explained after the fact

Shared conventions: node IDs are short uppercase strings (`N01`, `ST1`, `H1`);
time is simulation seconds as floats; every travel cost is in seconds, never
metres or hop counts.

---

## 8. The three required simulation modes

1. **Normal Operations** — low-to-moderate volume, resources generally available
2. **High-Demand / Rush** — several incidents compete for limited units
3. **Disruption** — at least two infrastructure or resource failures

All three exist in `resq/scenarios.py` and run today.

---

## 9. Instructor failure injection

During the demo the instructor changes the world while it runs. The controls are
ours to design, but must cover: close a road, make a unit unavailable, fill or
disable a hospital, create one critical incident, generate multiple incidents
quickly, change traffic cost, and restore a failed resource.

The stated purpose is to prove the system reacts to state changes rather than
following a scripted demo. Perfect visuals are explicitly not the goal.

Engine methods already implemented: `inject_close_road`, `inject_traffic`,
`inject_fill_hospital`, `inject_disable_unit`, each with automatic re-routing of
affected units. Still missing: restore-a-resource, spawn-incident, and the UI
controls that drive them.

---

## 10. Minimum deliverables

1. Working integrated product
2. Source repository with meaningful history and collaboration evidence
3. README — problem, architecture, setup, run instructions, roles, design
   decisions, limitations
4. Architecture diagram
5. Data model / schema documentation
6. Decision logic documentation explaining how prioritization, routing and
   allocation work and why we chose them
7. Meaningful automated tests, including failure cases
8. The three simulation modes
9. Individual contribution summary per student: what they owned, what they
   integrated, and one technical problem they personally solved

---

## 11. Milestones

| Milestone | Goal | Exit condition |
|---|---|---|
| M1 Design | Problem model, roles, interfaces, repo, architecture | Team can explain how components connect |
| M2 Vertical slice | One incident through the whole system | create → decide → dispatch → persist → display |
| M3 Intelligence | Decision, routing and AI features on realistic data | At least one non-trivial decision feature integrated |
| M4 Stress & failure | Dynamic scenarios and failure injection | System reacts with no manual code changes |
| M5 Finalization | Tests, docs, cleanup, reproducible setup | A new machine can run it from the README |
| M6 Demonstration | Live integrated presentation and individual defence | Every student demonstrates understanding |

**Where we are:** M1 is done. M2 is done except persistence — the vertical slice
runs end to end with stubs, but nothing is stored yet. That makes persistence
the immediate priority, since it is the only thing standing between us and a
completed M2.

---

## 12. Assessment rubric

| Category | Points |
|---|---|
| Integrated system functionality | 20 |
| Decision quality and technical depth | 20 |
| Architecture and code quality | 15 |
| Data and persistence | 10 |
| Resilience and dynamic behaviour | 10 |
| Testing and engineering discipline | 10 |
| Collaboration and Git workflow | 10 |
| Final demonstration and individual defence | 5 |

Visual polish helps but cannot replace correctness, reasoning, integration, or
understanding.

---

## 13. Individual demonstration rule

The instructor may ask any member to explain or operate **any** part of the
system. Expect to: explain why a component exists, trace a new incident through
to a dispatch decision, change one input and predict the result before running
it, explain a data structure or algorithm, show a failure case and how it is
handled, and identify AI-assisted code and explain how it was verified.

This is why the code is commented the way it is, and why I need to understand
every file in this repo — not just the ones I wrote.

---

## 14. Current state of the code

```
resq/models.py       shared dataclasses and enums — the contract
resq/results.py      ErrorCode and the decision result objects
resq/world.py        city graph, failure injection hooks, sample city
resq/interfaces.py   the three Protocols A, B and C implement
resq/engine.py       clock, tick pipeline, movement, arrivals, injection
resq/audit.py        DecisionRecord and AuditLog
resq/scenarios.py    the three required modes plus the metrics collector
resq/stubs/naive.py  deliberately weak stand-ins for A, B and C
main.py              console runner and component wiring
tests/test_integration.py   7 integration tests, all passing
pyproject.toml       pytest config
.github/workflows/ci.yml    CI
```

Verify with `pytest tests/ -v` and `python main.py disruption --log`.

### The tick pipeline

1. release incidents whose report time has arrived
2. **A** orders the waiting queue
3. **B** picks a unit for each waiting incident, in that order
4. **C** routes each newly assigned unit
5. advance every moving unit along its route
6. handle arrivals: on-scene work, hospital transport, resolution
7. write every decision to the audit log

### The stubs

`resq/stubs/naive.py` holds intentionally weak implementations — FIFO ordering,
first-free unit selection, fewest-hops routing. They exist so the pipeline runs
before teammates deliver, and they double as the baseline the real logic must
beat in the metrics comparison. **Do not improve them.**

---

## 15. What the project still needs

**Mine (Partner D):**

1. Persistence — SQLite schema and repository layer. Completes M2.
2. Operator UI — live view, scenario selector, clock, pause/step/resume.
3. Failure injection controls in the UI, calling real engine methods.
4. Audit screen — pick an incident, see its full decision chain.
5. Metrics and comparison mode — same scenario, two configurations, side by
   side. This is my depth contribution and my individual-defence answer.
6. CI on pull requests.
7. Architecture diagram, data model docs, decision logic writeup.
8. Engine hardening — JSON map loader, seeded randomness, restore-resource and
   spawn-incident injection.

**Theirs:**

- A — real severity scoring with explainability
- B — real multi-factor dispatch
- C — real Dijkstra/A* routing with alternatives and destination optimization

**Team-level, unassigned so far:** the architecture diagram owner, who writes
the decision-logic documentation, and rehearsing the eight-step demo.

---

## 16. Non-negotiable design rules

1. **The engine is the only thing that mutates the world.** Components read
   state and return a decision object; the engine applies it. This keeps the
   audit trail truthful.
2. **No exceptions for expected conditions.** Return the result object with the
   matching `ErrorCode`. Exceptions are for real bugs.
3. **Every decision carries a `rationale` and a `considered` list.** "Picked A3"
   scores nothing; "picked A3 over A1 because A1 covers the only northern
   station" is where the 20 decision-quality marks come from.
4. **Determinism.** Scenarios must reproduce exactly or the comparison proves
   nothing.
5. **Components plug in through the constructor.** Adding a real implementation
   must never require editing `engine.py`.
6. **Do not touch `resq/stubs/naive.py`.**
7. **Do not write code in `partner_a/`, `partner_b/`, `partner_c/`.**
8. **No new dependencies.** The core stays dependency-free; pytest only, for
   testing.

---

## 17. How I want you to work with me

- Incremental delivery. One feature at a time, verified before moving on.
- Comment code properly — why, not just what. Teammates read this to understand
  the contract, and I have to defend it individually.
- Numbered steps when giving me instructions.
- Run the tests after every change and tell me the count. Seven pass now.
- Prefer a GUI where a real choice exists.
- Push back when I ask for something wrong. I would rather hear it now than in
  the demo.
