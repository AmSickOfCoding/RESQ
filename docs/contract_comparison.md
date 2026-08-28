# Contract Reconciliation — Three Contracts, One Incident Record

**RESQ · Integration contract · 28 August 2026**

The System Core code, Saif's `docs/integration_contract.md`, and Huthaifa's
already-pushed `severity_scoring/` each define the shared objects differently.
This is every field, enum and event laid side by side, classified, with a
recommended resolution per conflict. Nothing has been merged, moved or
committed.

## Where each column comes from

| Column | Owner | Source |
|---|---|---|
| **D** | System Core (Faris) | `models.py`, `results.py`, `interfaces.py`, `world.py`, `audit.py`, `engine.py` |
| **C** | Saif | `docs/integration_contract.md`, `docs/decision_logic.md` (on `origin/main`) |
| **A** | Huthaifa | `severity_scoring/` — `config.py`, `scoring.py`, `validation.py` (commit `37b5a69`) |

> **A's module is already on the remote and belongs to neither layout.** It sits
> at the repo root as `severity_scoring/`, outside both `src/` and the core
> package, and it takes a plain `dict` rather than an `Incident`. It conflicts
> with C's document on its own, independently of the System Core — so it is a
> third column here, not a footnote.

## The count

| Verdict | Rows |
|---|---|
| Identical | 3 |
| Naming only | 9 |
| Genuine difference | 47 |
| **Total** | **59** |

**How to read the verdicts**

- **Identical** — same meaning, same shape.
- **Naming** — same concept, different label; a rename resolves it.
- **Genuine** — the models disagree, or one side has no answer.

Most of the 47 are gaps rather than head-on collisions: C's document describes
eight fields for an incident where the code carries nineteen. Gaps are cheap to
close. The eleven true collisions — where both sides define the same thing and
mean different things — are the ones that will pass code review and fail in the
demo, and they are called out in the recommendations. They also have their own
one-page agenda in `docs/contract_agenda.md`.

---

## Entity: Incident

D's `Incident` dataclass carries nineteen fields across three ownership zones: A
writes three, the engine writes the rest, and nobody else writes anything.

| Concept | D — models.py | C — contract doc | A — severity_scoring | Verdict |
|---|---|---|---|---|
| Identity | `incident_id: str` | `incident_id` (string) | `incident_id` required | Identical |
| Location | `node_id: str` | `location_node_id` | absent | Naming |
| What happened | `incident_type: IncidentType` — MEDICAL / FIRE / ACCIDENT / HAZMAT / RESCUE | no such field; collapsed into `required_unit_type` | `incident_type`, `INCIDENT_TYPE_MAP = None` (TBD) | Genuine |
| What's needed | `required_unit: UnitType` | `required_unit_type` | absent | Naming — field name only; values differ, see Enums |
| Report time | `reported_at: float`, simulation **seconds** | `reported_at` (float), "simulation **tick** timestamp" | absent | Genuine |
| Waiting time | derived: `now - reported_at`, seconds | absent | `waiting_time` required, "a number in **minutes**", ref = 10 | Genuine |
| People affected | `victims: int = 1` | absent | `people_affected`, int ≥ 0 | Naming — D↔A rename; C has no field |
| Reported severity *(input)* | **no field exists — gap on D's side.** The contract carries a slot for A's computed output and none for the severity that arrives with the call | `severity: integer 1–5` | `incident_severity` — "Low" / "Medium" / "High" / "Critical" | Genuine — D's omission; C and A both had a field here and the contract did not |
| Computed score *(output)* | `severity_score: float`, unbounded, higher = worse | absent | float 0–100 plus category string | Genuine |
| Ordering | `priority_rank: Optional[int]`, 1 = handled first | absent | implied by score, not stored | Genuine |
| Explanation | `severity_rationale: str` | absent | `explainability.py` — 0 bytes, empty file | Genuine |
| Capability need | `required_capabilities: Set[Capability]` | absent | absent | Genuine |
| Transport flag | `requires_transport: bool` — drives the hospital leg | absent | absent | Genuine |
| On-scene work | `service_seconds: float = 300.0` | absent | absent | Genuine |
| Status | `IncidentStatus` — 7 values | `status` enum — 6 values | absent | Genuine — see Enums, the IN_TRANSIT collision |
| Assignment trail | `assigned_unit_id`, `assigned_at`, `arrived_at`, `resolved_at`, `destination_hospital` | absent | absent | Genuine — five fields the audit screen reads |
| Failure record | `failure_reason: str` | absent | absent | Genuine |
| Headline metric | `response_seconds` derived — `arrived_at − reported_at` | absent | absent | Genuine |

---

## Entity: Response unit

The closest agreement in the whole comparison — five of ten rows are pure
renames. A has no opinion here at all.

| Concept | D — models.py | C — contract doc | Verdict |
|---|---|---|---|
| Identity | `unit_id: str` | `unit_id` (string) | Identical |
| Type | `unit_type: UnitType` | `unit_type` enum | Naming — field only; values collide, see Enums |
| Home base | `home_station: str` | `base_station_id` | Naming |
| Position | `current_node: str` | `current_node_id` | Naming |
| Status | `UnitStatus` — 6 values | `status` enum — 4 values | Genuine — see Enums |
| Capabilities | `capabilities: Set[Capability]` | absent | Genuine — B's capability match has nothing to read |
| Speed | `speed_factor: float = 1.0` | absent | Genuine |
| Workload | `total_busy_seconds: float` | `UnitWorkload` — used in `decision_logic.md` §2 but declared in no schema | Naming — the field exists; C's doc just never declares it |
| Live assignment | `assigned_incident_id`, `route`, `seconds_into_route`, `busy_until` | absent | Genuine |
| Availability | `is_free` derived from status | `IDLE` status value | Naming |

---

## Entities: World, hospital, route

C's document defines no world objects at all — only the IDs that appear inside
event payloads. The one exact match in this section is the travel-cost formula,
which is worth noting: independently written, character for character the same
idea.

| Concept | D — models.py / world.py | C — contract + decision_logic | Verdict |
|---|---|---|---|
| Travel cost | `cost_seconds` = inf if closed, else `base_seconds × traffic_multiplier` | `Tₑ(e)` = ∞ if closed, else `T_base(e) × μ(e)` | Identical — same formula; C's doc never states the unit |
| Node | `Node(node_id, name, kind: NodeKind, x, y)` | bare `string` IDs, no object, no kind | Genuine |
| Edge identity | `"N01->N02"` — two Edge objects per road, so one direction can close alone | `edge_id` (string), directionality unspecified | Genuine |
| Hospital | `capacity` + `occupied` stored; `free_beds`, `has_space` derived; `capabilities` set | `available_beds` stored and written directly; no capabilities | Genuine — C makes a derived count writable state |
| Station | `Station(node_id, name)` | only `base_station_id` on the unit | Genuine |
| Route | `Route(node_path, total_seconds, computed_at, alternatives, notes)` | no route object | Genuine — C owns routing and has not declared its own output shape |

---

## Enums

Nine enums, none of them agreeing. Both codebases declare their enums as `str`
subclasses, so a mismatched value compares `False` silently instead of raising —
which is why these rows matter more than their size suggests.

| Enum | D | C | A | Verdict |
|---|---|---|---|---|
| Incident status | `REPORTED, QUEUED, ASSIGNED, ON_SCENE, TRANSPORTING, RESOLVED, FAILED` | `REPORTED, QUEUED, ASSIGNED, IN_TRANSIT, ON_SCENE, RESOLVED` | absent | Genuine — two problems, see Decision 1 |
| Unit status | `AVAILABLE, EN_ROUTE, ON_SCENE, TRANSPORTING, RETURNING, OUT_OF_SERVICE` | `IDLE, EN_ROUTE, ON_SCENE, OFFLINE` | absent | Genuine — IDLE/AVAILABLE and OFFLINE/OUT_OF_SERVICE are renames; TRANSPORTING and RETURNING are missing outright |
| Unit type | `AMBULANCE, FIRE_TRUCK, RESCUE_VAN, HAZMAT_TEAM` | `AMBULANCE, FIRE, POLICE` | absent | Genuine — POLICE has no unit, capability or incident type anywhere |
| Incident type | `MEDICAL, FIRE, ACCIDENT, HAZMAT, RESCUE` | no such enum | `INCIDENT_TYPE_MAP = None` | Genuine |
| Node kind | `INTERSECTION, STATION, HOSPITAL` | absent | absent | Genuine |
| Capability | `TRAUMA, BURN, CARDIAC, PEDIATRIC, HEAVY_LIFT, CHEMICAL` | absent | absent | Genuine — C's own `best_destination` signature takes these |
| Error code | `NONE, NO_UNIT_AVAILABLE, NO_SUITABLE_UNIT, NO_ROUTE, NO_DESTINATION_AVAILABLE, UNIT_UNREACHABLE` | no error concept at all | raises `SeverityValidationError` | Genuine |
| Severity scale | `float`, unbounded | `integer 1–5` | `str` in → `float 0–100` out | Genuine — three scales, three types |
| Score category | no such concept | absent | `Low, Medium, High, Critical` | Genuine — a fourth enum in no contract |

> **Bug found while reading, unrelated to the merge:** `categorize_score` in
> `severity_scoring/scoring.py` tests `0 ≤ s < 24` then `25 ≤ s < 49`, so a score
> of 24.0, 49.5 or 74.2 matches no branch and raises
> `ValueError("Score must be between 0 and 100")` for a score that plainly is.
> Three dead bands. Worth telling Huthaifa whatever the team decides about the
> contract.

---

## Events: failure injection

The brief requires seven controls. C's document defines three, the engine
implements four, and the two lists disagree about who is allowed to change state.

| Control | D — engine.py / world.py | C — contract doc §3 | Verdict |
|---|---|---|---|
| Close a road | `inject_close_road(a, b)` — returns changed edge keys so the engine can invalidate live routes | `ROAD_CLOSURE {edge_id, is_closed}` | Genuine — payload writes state; no direction |
| Restore a road | `world.open_road()` exists, no `inject_` wrapper | absent | Genuine — missing both sides; brief §9 requires it |
| Change traffic | `inject_traffic(a, b, multiplier)` | no event, though `decision_logic.md` §1 defines the μ it would set | Genuine |
| Disable a unit | `inject_disable_unit(unit_id)` — also returns that unit's incident to the queue | `UNIT_OFFLINE {unit_id, status: "OFFLINE"}` | Genuine — caller-set status skips the requeue |
| Fill a hospital | `inject_fill_hospital(node_id)` — sets occupied = capacity | `HOSPITAL_CAPACITY_UPDATE {hospital_id, available_beds}` | Genuine — writes a derived number |
| Spawn incident / burst | not implemented | absent | Genuine — missing both sides; brief §9 requires both |

---

## Cross-cutting conventions and rules

These rows are not fields. They are the assumptions underneath every field, and
they are where the expensive disagreements live.

| Convention | D | C | A | Verdict |
|---|---|---|---|---|
| Time unit | simulation **seconds**, float | simulation **ticks**, float | **minutes** | Genuine — see Decision 2 |
| Travel cost unit | always seconds; never metres or hops | never stated | n/a | Genuine — by omission; the cheapest to fix, the most expensive to discover late |
| Node ID format | `N01` / `ST1` / `H1`, short uppercase | "string", unconstrained | n/a | Naming — compatible; C simply doesn't constrain it |
| Expected failures | return a result carrying an `ErrorCode`; never raise | no concept | raises on an unknown severity string | Genuine |
| Explainability | `rationale` + `considered: List[Candidate]` on every decision | nowhere in either doc | `explainability.py` is empty | Genuine — 20 rubric marks ride on this |
| Who mutates state | the engine, only — components read and return | event payloads carry state writes | n/a | Genuine |
| How the contract is expressed | stdlib dataclasses, zero dependencies | `requirements.txt` pins pydantic, fastapi, uvicorn | plain `dict` with required keys | Genuine |
| Source of truth | code — `models.py` is the contract | prose — `docs/*.md`, no code behind it | code | Genuine |
| Determinism | required; randomness takes a seeded `Random` from the engine | unstated | pure functions — compatible | Genuine — unstated, not contradicted |
| Who owns dispatch scoring | `select_unit()` sits on the `Dispatcher` protocol — Partner B | `decision_logic.md` §2 defines the dispatch score with fixed weights | n/a | Genuine — ownership, not data |

---

## Flagged decisions

### Decision 1 — `IN_TRANSIT` and `TRANSPORTING` name opposite legs of the journey

In C's document `IN_TRANSIT` sits between `ASSIGNED` and `ON_SCENE`: the unit is
driving *to* the incident. In the code `TRANSPORTING` sits after `ON_SCENE`: the
unit is driving a patient *away* to a hospital. Same grammatical shape, adjacent
vocabulary, opposite halves of the call.

The engine already distinguishes both legs, just not with a second incident
status. At `engine.py:204–209` dispatch sets the unit to `EN_ROUTE` and the
incident to `ASSIGNED`; at `engine.py:320–322` the hospital leg sets both to
`TRANSPORTING`. So the outbound leg is observable today — it is `ASSIGNED` on the
incident and `EN_ROUTE` on the unit. C's `IN_TRANSIT` is not a missing state; it
is a second name for `ASSIGNED` that happens to collide with the name of the
opposite leg.

> **Keep the code's seven values. Delete `IN_TRANSIT` from the document and ban
> the token outright.**

This is the single most dangerous row in the comparison, and the reason is that
it will not fail loudly. `IncidentStatus` is a `str` enum, so anything comparing
against the string `"IN_TRANSIT"` evaluates `False` and moves on. No exception,
no failing test. The visible symptom is an audit screen that reports a unit
taking a patient to hospital during the minutes it was actually driving to the
scene — which is exactly the sort of thing the instructor asks about, and exactly
the sort of thing nobody can explain live.

If the team decides the incident record should name the outbound leg explicitly,
the honest fix is to rename `ASSIGNED` to `EN_ROUTE_TO_SCENE`, not to add
`IN_TRANSIT` alongside `TRANSPORTING`. I would not: it costs edits to seven
passing tests and buys no behaviour. The `FAILED` value in the same enum is
separate and not negotiable — without it an unservable incident has no terminal
state, and the resilience marks depend on showing exactly that case.

### Decision 2 — time is in ticks, seconds and minutes across three people

C's document stamps `reported_at` as a "simulation tick timestamp". A's
`normalize_waiting_time` divides by a reference of 10 that `config.py` labels
minutes. The code uses simulation seconds as floats throughout. Three units, one
field.

> **Simulation seconds, as a float, everywhere. No exceptions, and the unit goes
> in the field name.**

Seconds wins on evidence rather than preference. It is already load-bearing in
code that runs: `Edge.base_seconds`, `Route.total_seconds`,
`Incident.service_seconds`, `response_seconds`, `total_busy_seconds`,
`DecisionRecord.sim_time`. The other two units exist in a prose document and in
one normalizer constant.

Ticks are the actively harmful option, and not merely because they are coarse. A
tick is a configuration knob — 30 seconds today. If anyone ever tunes it, every
timestamp already written to the database silently changes meaning, and no test
catches it because every number still looks reasonable. That breaks the
persistence requirement and the determinism requirement in the same stroke, and
it breaks them retroactively, across runs that were already recorded. Ticks are a
rendering choice for the UI clock; they should never reach a stored field.

A's fix is genuinely one line: keep the normalizer, change the reference from 10
to 600 and the label from minutes to seconds. The conversion is worth doing at
A's boundary rather than the engine's, because the engine already holds the
authoritative `now` and `reported_at` in seconds and should not be reformatting
them for one consumer.

The durable half of this recommendation is the naming rule: **no unit-free time
names**. `waiting_time` becomes `waiting_seconds`. A name that carries its unit
makes the next mismatch a review-time catch instead of a demo-time one — and with
four people writing against one contract, there will be a next one.

---

## Recommended resolutions

One per genuine difference or cluster of them, in the order I would take them to
the team. Every one of these is a proposal — nothing here has been written to a
file.

**1. Split reported severity from computed score — my gap to close.** *(D)*
Recommend: I add `reported_severity` to the incident record as an input field;
`severity_score: float` stays as A's output; the 1–5 scale is dropped in favour
of A's vocabulary.
Because: this row is not a naming fight and it is not C's mistake. C's `1–5` and
A's `"High"` are both *inputs* — what the caller reported. `severity_score` is
A's *output* — what the system computed. My contract defined the output slot and
no input slot at all, so both of them filled the hole themselves, in different
ways, and the resulting three-way split is mine. A's score currently has nowhere
to come from. A's 0–100 scale should stay: it exists, it works, and it lands in a
float field unchanged.

**2. Keep `incident_type` and `required_unit` as two fields.** *(C)*
Recommend: reject the merge into a single `required_unit_type`.
Because: they answer different questions and different people read them. A scores
on what happened; B matches on what is needed. Collapsing them forces A to reason
about fleet composition, which is B's job. It is also not expressible: `ACCIDENT`
is documented as possibly needing both medical and fire, and a single field
cannot say that.

**3. Adopt the four-value unit type enum.** *(C)*
Recommend: `AMBULANCE, FIRE_TRUCK, RESCUE_VAN, HAZMAT_TEAM`. Drop `POLICE` unless
someone wants to own it.
Because: `POLICE` has no unit in the sample fleet, no matching incident type and
no capability — nothing in the brief requires it, and an enum value with no
implementation behind it is a trap for whoever writes B. `FIRE` versus
`FIRE_TRUCK` is worse than it looks: both enums subclass `str`, so the mismatch
compares `False` instead of raising. If the team does want police, it is an
additive change to one enum plus one fleet entry, not a contract renegotiation.

**4. Adopt the six-value unit status enum.** *(C)*
Recommend: `IDLE` → `AVAILABLE`, `OFFLINE` → `OUT_OF_SERVICE`, and add
`TRANSPORTING` and `RETURNING`.
Because: the first two are free renames. The other two are real state: without
`RETURNING` a unit either teleports home or is shown as free while still driving,
which corrupts the utilisation metric; without `TRANSPORTING` the UI cannot show
the hospital leg it is meant to demonstrate.

**5. Adopt `ErrorCode`; keep validation exceptions inside A's module.** *(A + C)*
Recommend: no component raises across an interface boundary. A's
`SeverityValidationError` stays internal; a bad input becomes a low score plus a
rationale saying why.
Because: "unknown severity string" stops being a programmer error the moment real
scenario data flows through it — it is an expected condition, and an exception at
that boundary takes down the whole tick instead of degrading one incident. This
is also the rule the instructor is most likely to probe, because the resilience
marks are explicitly about not falling over.

**6. Make `rationale` and `considered` mandatory in the written contract.** *(A + B + C)*
Recommend: every decision returns both. A fills `severity_rationale`; C fills
`Route.alternatives` and the `considered` list on `DestinationDecision`.
Because: neither of C's documents mentions explainability anywhere, and A's
`explainability.py` is an empty file. This is 20 rubric marks and the entire
point of the audit screen — a dispatch score that returns a number and discards
what it rejected cannot be defended in the demo, however good the number is.

**7. Failure events name an intent, never a state write.** *(C)*
Recommend: `UNIT_OFFLINE {unit_id}`, not `{unit_id, status: "OFFLINE"}`. Same for
the hospital event.
Because: disabling a unit is not one write. `engine.py:411` also returns that
unit's incident to the queue — which is the behaviour the whole failure-injection
demo is meant to show. A payload that carries the target status invites a caller
to set it directly and skip the requeue, and then the audit log describes a world
that does not exist.

**8. Keep `capacity` + `occupied`; derive free beds.** *(C)*
Recommend: the hospital event sets `occupied`. `free_beds` stays a computed
property.
Because: two independently writable numbers that must agree will stop agreeing.
Deriving one of them makes that impossible rather than merely unlikely.

**9. Adopt directional edge keys.** *(C)*
Recommend: `"N01->N02"`, two edge objects per road, and say so in the document.
Because: C's `edge_id` does not say whether an edge is one road or one direction,
and the two readings produce different behaviour on the same call. Directional is
also the better demo: closing one direction forces a genuine detour rather than
severing the graph.

**10. Add the missing capability and transport fields to the document.** *(C)*
Recommend: document `Capability`, `required_capabilities`, unit `capabilities`,
`requires_transport`, and the `Route` object.
Because: C's own
`best_destination(from_node, world, required: Optional[Set[Capability]], now)`
signature already takes capabilities. The concept is in the interface he is
implementing against; it is just absent from the document he wrote.

**11. Move the dispatch scoring function out of C's document.** *(B + C)*
Recommend: `decision_logic.md` §2 belongs to Layan. C keeps §1, the travel-cost
model, which is his.
Because: this is the folder-ownership problem in written form. C has specified
B's weights before B has started — and if B implements something different, the
documentation and the code disagree in a document the instructor reads. C's §1
formula, by contrast, matches `Edge.cost_seconds` exactly and should stay.

**12. Add the three missing injection controls.** *(D)*
Recommend: restore-a-resource, spawn-one-incident, spawn-a-burst. Mine to build,
not a conflict.
Because: brief §9 lists seven controls; between them the two contracts cover
four. `world.open_road()` already exists and just needs an `inject_` wrapper.

**13. Keep the core dependency-free.** *(C)*
Recommend: stdlib dataclasses. `requirements.txt` drops pydantic, fastapi and
uvicorn until the UI decision is actually made.
Because: the contract objects are pure data and gain nothing from validation
models, teammates can clone and run with no setup, and pinning a web framework in
advance quietly decides the UI question before anyone has discussed it.

**14. Code is the contract; the document points at it.** *(Team)*
Recommend: `models.py`, `results.py` and `interfaces.py` are authoritative.
`docs/integration_contract.md` is rewritten to describe them and cite them, not
to define in parallel.
Because: the 47 rows above are what parallel definition produces in three days of
work. Prose that restates a schema drifts from it silently; prose that explains a
schema and names the file stays useful. The document still matters — deliverable
5 asks for data-model documentation — it just cannot be a second source of truth.

**15. State the determinism rule in the shared document.** *(C)*
Recommend: carry `interfaces.py` rule 4 across: no unseeded randomness anywhere.
Because: unstated rather than contradicted, and A's code happens to comply. But
the whole metrics comparison rests on two runs of one scenario being identical,
and a rule that lives only in a file A and C have not read is not a rule yet.

**16. Adopt the pure renames without discussion.** *(Team)*
Recommend: the nine naming rows — `location_node_id` → `node_id`,
`base_station_id` → `home_station`, `current_node_id` → `current_node`,
`people_affected` → `victims`, `IDLE` → `AVAILABLE`, `OFFLINE` →
`OUT_OF_SERVICE`, `UnitWorkload` → `total_busy_seconds`, and the two enum-value
renames — go to the code's spelling.
Because: not because the code's names are better, but because they are the ones
with tests behind them. Renaming in the direction of the running implementation
costs nothing; renaming the other way costs seven passing tests. Clearing these
nine leaves the meeting free for the eleven rows that are actually arguments.

---

## Still open — not mine to decide

Three things this comparison surfaced that the team has to settle rather than me:

**Where A's module lives.** `severity_scoring/` is at the repo root, in neither
proposed layout, and takes a `dict` rather than an `Incident`. Whatever the
merged tree looks like, it needs a home and an adapter — and Huthaifa should be
in that conversation before anything moves.

**Whether `src/engine/` survives.** The folder holds routing, dispatch scoring
and audit together, which is three owners in one directory. That was already
flagged and is unresolved; the ownership row in the cross-cutting table is the
same problem seen from the contract side.

**Who owns the written contract afterwards.** If recommendation 14 carries,
someone has to keep `docs/` honest as the code moves. Unassigned today.

---

Compiled from the System Core sources (15 files, read in full), `origin/main` at
`796eef3`, and `origin/huthaifa/severity-prioritization` at `37b5a69`. No files
were moved, edited or committed to produce it.
