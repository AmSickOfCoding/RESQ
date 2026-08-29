# RESQ — Emergency Response Digital Twin

A simulated city where emergencies appear over time and the system must decide,
live and without anyone editing code: which incident to handle first, which unit
to send, what route it takes, and where to take a patient. Then roads close,
traffic builds, hospitals fill and units break down, and it has to keep working.

Built as a four-person university capstone.

---

## 1. The problem

A city is modelled as a graph of nodes joined by roads. Response units sit at
stations. Emergencies are reported at nodes over simulated time. Every tick, the
system has to answer four questions, and afterwards it has to be able to explain
why it answered them that way.

The brief is explicit that **"nearest unit wins" is not enough**. Decisions must
weigh several competing factors, and the reasoning has to be recoverable after
the fact — which is why every decision in this system carries a written
rationale and the list of options it rejected.

---

## 2. Quick start

No dependencies. Python 3.9 or newer, nothing to install.

```bash
git clone https://github.com/AmSickOfCoding/RESQ.git
cd RESQ

python main.py disruption          # run a scenario
python main.py --ui                # open the operator console
python -m pytest tests/ -q         # 45 tests
```

`pytest` is the only extra, and only for the tests:

```bash
pip install pytest
```

### Every command

| Command | What it does |
|---|---|
| `python main.py [normal\|rush\|disruption]` | Run one of the three required scenarios |
| `python main.py disruption --log` | Print every decision as it happens |
| `python main.py disruption --stubs` | Run the naive baseline instead of the real components |
| `python main.py rush --save` | Persist the run to `resq.db` |
| `python main.py --runs` | List runs already in the database |
| `python main.py --chain 1:DIS-01` | Read one incident's stored decision chain back off the disk |
| `python main.py normal --explain N-01` | Same, without saving |
| `python main.py --ui` | Operator console (add `--save` to record what you do) |

### The operator console

Two tabs under the live tables:

- **Decision log** — every audit record as it happens.
- **Audit: why did it do that?** — pick any incident, or double-click one in the
  table above, and see its complete decision chain: who decided what, when, on
  what grounds, and which options were rejected and why. `Export as text` saves
  it for the report.

The **Components** selector switches between the real implementations and the
naive baseline and reloads, so the before/after comparison can be shown live
rather than quoted from a table.

---

## 3. Architecture

Full diagram and data model: [docs/architecture.md](docs/architecture.md).
How the three decisions actually work: [docs/decision_logic.md](docs/decision_logic.md).

```
                     ┌──────────────────────────┐
   operator ────────▶│        Engine            │◀──── scenarios
   (UI / CLI)        │  owns the clock          │
                     │  owns ALL mutation       │
                     └───┬──────────────────┬───┘
                         │ asks             │ writes
          ┌──────────────┼──────────────┐   │
          ▼              ▼              ▼   ▼
    Prioritizer    Dispatcher       Router  │
      (A)             (B)             (C)   │
          │              │              │   │
          └──────────────┴──────────────┘   │
                  return decisions          │
                                            ▼
                              World ──▶ AuditLog ──▶ Repository
                                                      (SQLite)
```

Four ideas hold it together:

**The engine is the only thing that mutates the world.** Components read state
and return a decision object; the engine applies it. That is what makes the
audit trail truthful — if the log says a unit was dispatched, it was.

**Components arrive through the constructor.** Each teammate implements one
Protocol from `resq/interfaces.py`. Swapping a stub for a real implementation is
one line in `main.py`; `engine.py` never changes.

**Nothing raises for an expected condition.** No free unit, no route, every
hospital full — all return a result object carrying an `ErrorCode`. Exceptions
are reserved for genuine bugs. A simulation whose whole point is to be broken
live cannot fall over when it is.

**Every decision explains itself.** `rationale` says why in one sentence,
`considered` lists what was rejected and why. This is what the audit screen
reads and what makes the system defensible.

### Layout

```
resq/models.py         shared dataclasses and enums — the integration contract
resq/results.py        ErrorCode and the decision result objects
resq/world.py          city graph, mutation hooks, sample city
resq/interfaces.py     the three Protocols A, B and C implement
resq/engine.py         clock, tick pipeline, movement, arrivals, injection
resq/audit.py          DecisionRecord and AuditLog
resq/storage.py        SQLite persistence
resq/scenarios.py      the three required modes and the metrics collector
resq/ui.py             Tk operator console
resq/stubs/naive.py    deliberately weak baselines
resq/adapters/         thin translation layers onto teammates' modules
severity_scoring/      Partner A's module, merged unchanged
allocation.py etc.     Partner B's module, merged unchanged
```

### The tick pipeline

Every tick runs the same seven steps:

1. release incidents whose report time has arrived
2. **A** orders the waiting queue
3. **B** picks a unit for each waiting incident, in that order
4. **C** routes each newly assigned unit
5. advance every moving unit along its route
6. handle arrivals: on-scene work, hospital transport, resolution
7. write every decision to the audit log and the database

---

## 4. Team and roles

| | Member | Owns | Where |
|---|---|---|---|
| **A** | Huthaifa | Severity scoring, prioritization | `severity_scoring/` |
| **B** | Layan | Resource allocation, dispatch | `allocation.py`, `dispatch.py` |
| **C** | Saif | Routing, graph, destinations | not yet delivered |
| **D** | Faris | Architecture, engine, persistence, UI, audit, integration, testing, CI | `resq/` |

A and B are integrated and running. C has not delivered, so routing currently
uses the naive fewest-hops stub — see Limitations.

---

## 5. Design decisions

**SQLite from the standard library, no ORM.** Persistence is worth 10 marks and
had to be defensible in a viva. `resq/storage.py` is a `Repository` class the
engine calls by name; the engine never imports `sqlite3`. Incidents and units
are upserted so those tables answer "how did the run end"; decisions and world
events are append-only so they answer "how did it get there".

**A Tk desktop UI, not a web app.** Tk ships with Python, so the operator
console adds no dependency and the repository still runs from a clone with
nothing installed. Every button calls a real engine method and the screen then
redraws from the world — nothing is faked for display, so the tables and the log
can never disagree.

**Adapters instead of asking teammates to rewrite.** A's and B's modules were
written against different field names, different units and different types. The
mismatches are absorbed in `resq/adapters/`, where they are visible and tested,
rather than by editing four people's code the night before a deadline. Every
difference is catalogued in
[docs/contract_comparison.md](docs/contract_comparison.md); the eleven that need
a team decision are in [docs/contract_agenda.md](docs/contract_agenda.md).

**Determinism everywhere.** Same scenario, same result, every time. Without it
the before/after comparison below would prove nothing. Two tests assert it.

**The stubs are deliberately bad and stay that way.** FIFO ordering, first-free
unit, fewest-hops routing. They exist so the pipeline runs before teammates
deliver, and they are the baseline the real work is measured against.

---

## 6. Does the team's logic actually help?

Same scenarios, same seed, `--stubs` against the real components:

| Scenario | Config | Resolved | Avg response | Worst |
|---|---|---|---|---|
| Normal | baseline | 4/4 | 255s | 420s |
| Normal | **real** | 4/4 | **165s** | **180s** |
| Rush | baseline | 7/8 | 381s | 900s |
| Rush | **real** | 7/8 | 381s | 900s |
| Disruption | baseline | 3/5 | 942s | 1650s |
| Disruption | **real** | **5/5** | **288s** | **930s** |

Two honest readings of that table:

- Under **disruption** the real components are decisively better — two calls
  that the baseline abandoned entirely now get answered, and average response
  time falls by 69%.
- Under **rush** they change nothing at all. When every unit is already
  committed, the order you queue work in cannot conjure an ambulance. That is a
  real limit of prioritization, not a bug, and it is the clearest argument for
  why C's routing still matters.

Reproduce with `python main.py <scenario> [--stubs]`.

---

## 7. Testing and CI

45 tests, `python -m pytest tests/ -q`.

| File | Covers |
|---|---|
| `test_integration.py` | End-to-end resolution, audit completeness, reroute on closure, clean `NO_ROUTE`, unit disabling, hospital diversion, all three scenarios |
| `test_persistence.py` | The five tables, and a restart proof that writes in a child process and reads back here |
| `test_injection.py` | All seven failure-injection controls |
| `test_adapter_partner_a.py` | A's translation, scoring behaviour, determinism |
| `test_adapter_partner_b.py` | B's translation, that the adapter mutates nothing, that her score is never overridden |

CI (`.github/workflows/ci.yml`) runs on every branch, fails loudly if the suite
collects nothing, and smoke-runs all three scenarios after the tests.

---

## 8. Limitations

**Partner C has not delivered.** Routing is still the naive fewest-hops stub, so
routes ignore road length and traffic — they only respect closures. Travel-time
figures above are therefore hop-count driven and will change when real routing
lands. The adapter slot is ready in `main.py`.

**The integration contract is not agreed.** A, B and the shared code define
incidents differently — three severity representations, three time units, two
incompatible meanings for `IN_TRANSIT`. Nothing is resolved; it is all absorbed
in the adapters and documented for the team to rule on.

**Incident severity is inferred, not reported.** The shared contract has a field
for the score A computes and none for the severity a caller reports, so the
adapter derives a triage level from incident type and victim count. That is a
gap in the contract, not in A's module.

**Units move at node granularity.** A unit part-way along a road is reported at
the node it left. This keeps re-routing simple, because a new route is always
computed from a real node.

**The map is hardcoded.** `build_sample_city()` builds a 4×3 grid with three
stations and two hospitals. A JSON map loader is not written yet.

**No pause across process restart.** The UI pauses and steps, but a paused
simulation is not resumable after closing the window; only completed runs
persist.
