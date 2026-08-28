# Individual Contribution — Faris Elzayyat (Partner D, System Core)

Deliverable 9. What I owned, what I integrated, and one technical problem I
solved myself.

---

## 1. What I owned

Architecture, the simulation engine, persistence, the operator UI, the audit
trail, integration, testing and CI. Roughly 55 of the 100 marks pass through
these, but none of them are decision algorithms — my job was the system the
other three plug into.

| Area | What exists | Where |
|---|---|---|
| Integration contract | Shared dataclasses, enums, error codes, three Protocols | `resq/models.py`, `results.py`, `interfaces.py` |
| Simulation engine | Clock, seven-step tick pipeline, movement, arrivals, incident and unit lifecycles | `resq/engine.py` |
| World model | Graph, hospitals, stations, live mutation hooks, sample city | `resq/world.py` |
| Failure injection | All seven controls the brief requires, each with automatic re-routing | `resq/engine.py` |
| Persistence | SQLite via the standard library, five tables, `Repository` class | `resq/storage.py` |
| Audit trail | `DecisionRecord`, `AuditLog`, per-incident chain retrieval | `resq/audit.py` |
| Operator UI | Tk console — live tables, clock, scenario selector, pause/step/speed, injection buttons | `resq/ui.py` |
| Integration | Adapters onto A's and B's modules | `resq/adapters/` |
| Testing and CI | 45 tests, GitHub Actions on every branch | `tests/`, `.github/workflows/ci.yml` |

---

## 2. What I integrated

**Partner A — severity scoring.** Merged `huthaifa/severity-prioritization` and
wired it in through `resq/adapters/partner_a.py`. His module works on a plain
dict in minutes; ours is a dataclass in seconds. Two of his four weighting
factors still have no formula, so rather than drop them and quietly compress
every score, the adapter supplies the normalised value and applies *his* weight.
His validator raises on unrecognised input; our design rules forbid exceptions
for expected conditions, so it is wrapped — a rejected incident scores zero with
a written reason and the tick continues.

**Partner B — dispatch allocation.** Merged `layan/dispatch-allocator` and wired
it in through `resq/adapters/partner_b.py`. Her `capabilities` field holds
incident types; ours is an unrelated enum with the same name, so passing ours
would have matched nothing and dispatched no one. Her `workload` is a small
integer and ours is accumulated seconds, so it is bucketed. Her `created_at` is
a real `datetime` and ours is simulated time, so it is derived from a fixed
epoch rather than `datetime.now()` — otherwise no run would ever reproduce.

Neither teammate was asked to change anything. Every mismatch is absorbed on my
side, where it is visible and covered by tests, and catalogued in
`contract_comparison.md` for the team to settle properly.

**Partner C has not delivered.** Routing runs on the naive stub. The adapter
slot is ready and is one line in `main.py`.

### The judgement call I want to be asked about

Partner B's scorer never measures travel time — it awards points for being on
the same node and otherwise judges only workload. In a real city almost nothing
is on the same node, so most eligible units tie and her function returns
whichever happens to come first in the list.

I did not fold distance into her formula. That would have been rewriting her
graded work and then presenting it as hers. Instead her score stays the primary
key and ties break on the router's travel time, so a unit she scores higher
always wins — there is a test (`test_her_score_always_beats_the_travel_time_tiebreak`)
that fails if that is ever violated. The rationale on every dispatch says which
of the two actually decided it, so the demo can show the seam rather than hide
it.

---

## 3. The technical problem I personally solved

**Proving persistence actually persists.**

The acceptance criterion I set was: run a scenario, exit the process, start
again, and the full decision chain for a given incident is still readable. The
easy version of that test is worthless — write to a database, read from the same
open connection, watch it pass, and learn nothing, because the objects were
still in memory the whole time.

So `test_decision_chain_survives_a_real_restart` launches a **separate Python
interpreter** with `subprocess`, runs the disruption scenario there, lets that
process exit completely, and only then reopens the file in the test process and
asserts the chain is intact — that it reaches a terminal action, and that the
rationales survived the round trip as text rather than as `repr()` output. If
anything were being held in memory rather than written, the child's exit would
destroy it and the test would fail.

Two things fell out of building it that I would not have found otherwise:

1. **The audit log and the database can silently diverge.** I added
   `test_saved_decisions_match_the_in_memory_audit_log`, which compares them
   record by record. If they ever disagree, the audit screen is lying to
   whoever is reading it, and that is the one failure mode this system cannot
   afford.

2. **`considered` has to survive as structured data, not as a string.** JSON
   round-tripping was the risk — flatten the rejected-alternatives list to text
   and the audit screen can still print it, so nothing looks broken, but it can
   no longer be queried or grouped. There is a test asserting it comes back as a
   list.

The engine never imports `sqlite3`. It calls named methods on an object it was
handed, and with `None` passed its behaviour is byte-for-byte unchanged —
asserted by comparing two complete audit logs, which is what lets the original
seven integration tests stay honest.

---

## 4. My depth contribution — measurement

The other three own the algorithmic marks. Mine is proving whether their work
helps. `--stubs` runs the deliberately naive baseline; without it, the real
components. Same scenarios, same seed.

| Scenario | Config | Resolved | Avg response | Worst |
|---|---|---|---|---|
| Normal | baseline | 4/4 | 255s | 420s |
| Normal | **real** | 4/4 | **165s** | **180s** |
| Rush | baseline | 7/8 | 381s | 900s |
| Rush | **real** | 7/8 | 381s | 900s |
| Disruption | baseline | 3/5 | 942s | 1650s |
| Disruption | **real** | **5/5** | **288s** | **930s** |

The disruption row is the headline: two calls the baseline abandoned outright
are now answered, and average response falls 69%.

**The rush row is the more interesting one, and I want to be asked about it.**
The real components change nothing under saturation. That is not a measurement
error and not a bug — when every unit is already committed, the order you queue
work in cannot conjure an ambulance. Prioritization decides *who waits*, not
*how many can be served*. Adding capacity or cutting travel time is what moves
that number, which is the strongest argument I have for why C's routing still
matters and why we should not have concluded "the logic works" from the
disruption row alone.

Being able to say which of our components can and cannot affect a given metric,
and to show it with numbers from a reproducible run, is the part of this project
I would defend most confidently.

---

## 5. Honest limitations

- **C has not delivered**, so routing is fewest-hops and ignores road length and
  traffic. Every travel figure above will move when real routing lands.
- **The integration contract is not agreed.** Three severity representations,
  three time units, and two incompatible meanings for `IN_TRANSIT` are live in
  the repository right now. I catalogued all 59 differences and put the eleven
  that need a decision on one page, but the team has not ruled. The cost is
  currently paid in my adapters.
- **The missing reported-severity field is my mistake.** My contract defined a
  slot for the score A computes and none for the severity a caller reports, so
  A and C each invented their own field. The three-way split is mine, not
  theirs, and the adapter's derived triage level is a placeholder for a field I
  should have defined in the first place.
- **No JSON map loader.** The city is hardcoded in `build_sample_city()`.
- **A paused run is not resumable** across a restart; only completed runs
  persist.
