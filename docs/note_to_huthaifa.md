# Note for Huthaifa — one-line fix in `severity_scoring/scoring.py`

Faris, 28 Aug. I changed three lines in your module. Telling you rather than
leaving you to find it in a diff.

## What I changed

In `categorize_score`, the lower bounds only:

```diff
 if 0 <= score <= 24:
     return "Low"
-elif 25 <= score <= 49:
+elif 24 <= score <= 49:
     return "Medium"
-elif 50 <= score <= 74:
+elif 49 <= score <= 74:
     return "High"
-elif 75 <= score <= 100:
+elif 74 <= score <= 100:
     return "Critical"
 else:
     raise ValueError("Score must be between 0 and 100.")
```

Nothing else. No logic rewrite, no change to your weights, thresholds or
category names.

## Why

The ranges had gaps. A score of 24.5 is greater than 24 and less than 25, so it
matched no branch and fell through to the `raise`. Same for 49.x and 74.x —
297 of the 10001 values between 0 and 100 raised
`ValueError("Score must be between 0 and 100")` for a score that was, in fact,
between 0 and 100.

Because it's an `elif` chain, overlapping the bounds costs nothing — the first
match wins, so 24 is still "Low", 49 still "Medium", 74 still "High", exactly as
you had it. Out-of-range input is still rejected, which is what the guard is
actually for.

## Why it mattered more than it looks

It wasn't just a noisy log line. Three incidents were stuck in the queue
permanently.

Waiting time is one of your four factors and it caps at ten minutes. A MEDICAL
call with 2 victims scores exactly **49.25** once it has waited that long —
inside a dead band. After ten minutes its inputs stop changing, so it didn't
fail once; it failed on *every* tick from then on. My adapter was scoring those
0.0, which parked them at the bottom of the queue while every new call overtook
them.

So the factor you added to stop old calls being starved was, for those specific
inputs, causing permanent starvation. Genuinely hard to spot — it only shows up
after a call has waited past the cap, and none of our three canned scenarios
happen to produce a score in a band.

## What I fixed on my side

The bug was mine to trip over as much as yours to fix. My adapter turned an
exception into a score of 0.0, which is what actually did the damage — a
failure should never be able to bury an incident. It now degrades to a
mid-scale score so the call still competes, and it tries scoring and
categorising separately, so if only the label lookup fails the real number
survives and ordering is unaffected.

## If you'd rather do it differently

Your module, your call. A cleaner version might use your `CATEGORY_THRESHOLDS`
list in `config.py` — it's already there and unused, and driving the function
from it would make the bands impossible to get out of step with the config.
I didn't do that because you asked for no rewrites and I didn't want to make a
design decision in your file.

Two things still marked TBD that the adapter is currently standing in for, if
you want them back:

- `PEOPLE_AFFECTED_FORMULA` is `None` — I'm using `min(victims / 10, 1)`
- `INCIDENT_TYPE_MAP` is `None` — I'm using medical 0.55, accident 0.70,
  rescue 0.75, fire 0.85, hazmat 1.00

Both apply *your* weights from `config.py`. The moment you fill them in, those
two blocks come out of `resq/adapters/partner_a.py`.

There's also a regression test now — `test_categorize_score_covers_every_value_from_0_to_100`
in `tests/test_adapter_partner_a.py` — that sweeps all 10001 values. If a future
change reopens a gap, CI catches it.
