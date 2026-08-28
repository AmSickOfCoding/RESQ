# Decision Logic

Deliverable 6: how prioritization, allocation and routing actually work in this
repository, and why they are built that way.

> **This document describes the code as it runs today.** An earlier version of
> this file specified Dijkstra/A* routing and a three-weight dispatch formula.
> Neither was ever implemented — they were a design sketch written before anyone
> had built anything, and the code went a different way. Everything below has
> been checked against the source, and each section names the file it describes.
> The gap between the two is exactly the failure mode `contract_comparison.md`
> exists to prevent, so this file is now written from the code, not ahead of it.

Three decisions are made every tick, by three different people's code, in a
fixed order.

| # | Decision | Owner | Implemented in |
|---|---|---|---|
| 1 | Which incident is handled first | Huthaifa (A) | `severity_scoring/`, via `resq/adapters/partner_a.py` |
| 2 | Which unit is sent | Layan (B) | `allocation.py`, via `resq/adapters/partner_b.py` |
| 3 | What route it takes, and which hospital | Saif (C) | **not delivered** — `resq/stubs/naive.py` |

---

## 1. Prioritization — which incident goes first

**Runs:** `severity_scoring/scoring.py` and `config.py`, called through
`SeverityPrioritizer`.

Every waiting incident is scored on four weighted factors. The weights are
Huthaifa's, in `severity_scoring/config.py`:

$$\text{score}_{0..1} = 0.40 \cdot S + 0.25 \cdot P + 0.20 \cdot W + 0.15 \cdot T$$

The result is multiplied by 100 and rounded to two decimals, then bucketed into
a category.

| Symbol | Factor | How it is normalised to 0–1 |
|---|---|---|
| $S$ | Reported severity | Direct lookup: Low 0.10, Medium 0.40, High 0.70, Critical 1.00 |
| $P$ | People affected | $\min(\text{victims} / 10,\ 1)$ |
| $W$ | Waiting time | $\min(\text{minutes} / 10,\ 1)$ — capped at ten minutes |
| $T$ | Incident type | Medical 0.55, Accident 0.70, Rescue 0.75, Fire 0.85, Hazmat 1.00 |

Categories: 0–24 Low, 25–49 Medium, 50–74 High, 75–100 Critical.

Incidents are then sorted by score descending. **Ties break on report time, then
on incident id** — not arbitrarily, because the whole before/after comparison
depends on two identical runs producing identical results.

### What the adapter contributes, and why

Three of these details are not in Huthaifa's module and are supplied by the
adapter. They are listed here rather than buried, because they are the parts a
reviewer would otherwise wrongly credit to him:

- **$S$ has no source field.** The shared contract has a slot for the score A
  *computes* and no field for the severity a caller *reports*. That is a gap in
  the contract — see `contract_agenda.md` item 3 — so the adapter derives a
  triage level from incident type and victim count as a placeholder: a baseline
  per type, escalated one step at 3 victims and two steps at 5.
- **$P$ and $T$ have no formula yet.** `PEOPLE_AFFECTED_FORMULA` and
  `INCIDENT_TYPE_MAP` are both `None` in his config. Rather than drop two
  factors — which would silently compress every score into a 0–60 band — the
  adapter supplies the normalised value above and applies *his* weight to it.
- **Units.** His module documents minutes; the engine records seconds. Converted
  at the boundary (`contract_agenda.md` item 2).

### Why this beats the baseline

The stub it replaces (`FifoPrioritizer`) sorts by report time and ignores
severity entirely, so a cardiac arrest reported at t=100 waits behind a fender
bender reported at t=90. The scored version fixes that, and the waiting-time
factor prevents the opposite failure: a low-severity call cannot starve forever,
because $W$ climbs until it overtakes fresher, more severe work.

---

## 2. Allocation — which unit is sent

**Runs:** `allocation.py::calculate_resource_score`, called through
`AllocationDispatcher`.

Three hard gates first. Failing any of them scores −1 and the unit is out:

1. status must be available
2. unit type must equal the incident's required type
3. the incident's type must be in the unit's capability set

Surviving units are scored:

$$\text{score} = 50 \cdot [\text{same node}] + \max(0,\ 20 - 5 \cdot \text{workload}) + 10 \cdot [\text{workload} = 0]$$

So an idle unit standing on the incident's own node scores 80; an idle unit
elsewhere scores 30; a unit with workload 4 or more scores 0. Workload is
bucketed by the adapter at one point per ten simulated minutes of accumulated
busy time.

### The tie-break, and why it is separate

This formula **never measures travel time.** It awards 50 points for being on
the incident's exact node and otherwise judges only workload. In a twelve-node
city almost nothing is ever on the same node, so in practice most eligible units
tie on 30 and `allocate_resource` returns whichever comes first in the list.

The adapter therefore breaks ties on the router's travel time — and only ties. A
unit Layan's formula scores higher always wins, and
`test_her_score_always_beats_the_travel_time_tiebreak` fails if that is ever
violated. The distinction matters for marking: the score is her work, the
tie-break is the integration layer's, and every dispatch rationale states which
of the two decided it, in words:

> Tied on allocation score 30 with 2 other unit(s); A2 chosen as the closest at 60s.

versus

> A2 had the highest allocation score (80), 0s away.

### Failure, not exceptions

When nothing is eligible the dispatcher returns a decision carrying
`NO_UNIT_AVAILABLE` (nothing free at all) or `NO_SUITABLE_UNIT` (free units
exist, none match), plus the list of every unit rejected and why. The incident
stays `QUEUED` and is retried next tick. Nothing raises — that is what lets the
rush scenario produce realistic waiting instead of a crash.

---

## 3. Routing and destination — currently a stub

**Runs:** `resq/stubs/naive.py::BfsRouter`. **Partner C has not delivered.**

### Path finding

Breadth-first search for the path with the **fewest hops**. It respects closed
roads — `world.neighbours()` only returns neighbours reachable through an open
edge — but it **ignores `traffic_multiplier` entirely** when choosing the path.

The cost it then reports *is* correct: `total_seconds` sums
`base_seconds × traffic_multiplier` over the chosen path. So the ETA is honest;
the choice of path is not optimal. A gridlocked two-hop road beats a clear
four-hop detour, and the route's own reported cost will say so.

This is the single largest weakness in the system, and it is the reason the
travel-time figures in the README are hop-count driven.

### Destination selection

For patient transport, every hospital is examined in turn and rejected with a
stated reason:

| Rejection | Recorded as |
|---|---|
| No free beds | `at full capacity` |
| Lacks a required capability | `missing capability: TRAUMA` |
| No open road to it | `unreachable` |

Survivors are ranked by travel time and the nearest wins. If none survive, the
result carries `NO_DESTINATION_AVAILABLE` and the incident is marked `FAILED`
with the reason preserved — which is how the "hospital full" demo step produces
a visible, explainable outcome rather than an error.

### What replacing this should change

Dijkstra or A* over `Edge.cost_seconds` — which already exists as a property and
already returns infinity for a closed road, so the graph needs no changes.
`Route.alternatives` is in the contract and unused; populating it is what would
let the audit view show rejected paths the way it already shows rejected units.

---

## 4. Rules that constrain all three

These are not implementation details; they are why the decisions can be trusted.

**Components never mutate anything.** A, B and C read the world and return a
decision object. The engine applies it. If the audit log says a unit was
dispatched at 14:03, the world changed at 14:03, in the same call that wrote the
record. `test_the_adapter_mutates_nothing` enforces this at the boundary.

**No exceptions for expected conditions.** "No unit free", "no route", "every
hospital full" are ordinary events in a simulation designed to be broken live.
Each returns a result carrying an `ErrorCode` and a sentence. Huthaifa's
validator does raise, so the adapter wraps it: a rejected input scores zero with
a written reason and the tick continues.

**Every decision carries `rationale` and `considered`.** A chosen option with no
rejected alternatives is unfalsifiable. "Picked A3" is worth nothing; "picked A3
over A1 and A7 because both were the wrong type" is the evidence.

**Determinism.** Same scenario, same result, every time — enforced by sorted
candidate lists, explicit tie-breaks, and a fixed epoch instead of
`datetime.now()`. Two tests assert it. Without it the comparison below is
meaningless.

---

## 5. Does any of it help?

Same scenarios, same seed. `--stubs` runs the naive baseline.

| Scenario | Config | Resolved | Avg response | Worst |
|---|---|---|---|---|
| Normal | baseline | 4/4 | 255s | 420s |
| Normal | **real** | 4/4 | **165s** | **180s** |
| Rush | baseline | 7/8 | 381s | 900s |
| Rush | **real** | 7/8 | 381s | 900s |
| Disruption | baseline | 3/5 | 942s | 1650s |
| Disruption | **real** | **5/5** | **288s** | **930s** |

Under **disruption**, decisively yes — two calls the baseline abandoned outright
are answered, and average response falls 69%.

Under **rush**, no: the real components change nothing. When every unit is
already committed, the order you queue work in cannot conjure an ambulance.
Prioritization decides *who waits*, not *how many can be served*. That is a real
limit of what decision 1 can do, not a defect, and it is the strongest argument
for why decision 3 — real routing — still matters: cutting travel time is what
frees capacity, and capacity is what that row is short of.

Reproduce with `python main.py <scenario> [--stubs]`.
