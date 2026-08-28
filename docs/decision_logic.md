# Decision Logic & Algorithm Specifications

This document outlines the mathematical models, pathfinding formulas, and dispatch scoring metrics used by the RESQ decision engine.

## 1. Pathfinding & Effective Travel Time
Effective travel time $T_e(e)$ across graph edge $e = (u, v)$ is calculated dynamically as:

$$T_e(e) = \begin{cases} \infty & \text{if } \text{is\_closed}(e) = \text{true} \\ T_{\text{base}}(e) \times \mu(e) & \text{otherwise} \end{cases}$$

Where:
- $T_{\text{base}}(e)$: Nominal baseline travel time.
- $\mu(e) \ge 1.0$: Dynamic speed penalty multiplier representing traffic congestion.

## 2. Dispatch Scoring Function
Candidate response units are evaluated using a multi-factor score:

$$\text{Score} = (w_1 \times \text{TravelTime}) + (w_2 \times \text{UnitWorkload}) + (w_3 \times \text{SeverityMatchPenalty})$$

Where:
- $\text{TravelTime}$: Minimum travel time calculated via Dijkstra/A* pathfinding.
- $\text{UnitWorkload}$: Cumulative duty metric / incidents handled by candidate unit.
- $\text{SeverityMatchPenalty}$: Penalty factor applied if unit capability deviates from incident severity.
- $w_1, w_2, w_3$: Configurable engine weights ($w_1 = 1.0, w_2 = 0.5, w_3 = 2.0$).

## 3. Severity Scoring & Incident Prioritization

The Severity Scoring module calculates an incident priority score from 0 to 100 using four weighted factors:

| Factor | Weight | Method |
|---|---:|---|
| Incident Severity | 40% | Direct Mapping |
| People Affected | 25% | Logarithmic Scaling |
| Waiting Time | 20% | Normalization |
| Incident Type | 15% | Direct Mapping |

### 3.1 Incident Severity

Incident severity is represented as an integer from 1 to 5.

| Severity | Normalized Value |
|---|---:|
| 1 | 0.10 |
| 2 | 0.325 |
| 3 | 0.55 |
| 4 | 0.775 |
| 5 | 1.00 |

The severity contribution is calculated using a 40% weight.

### 3.2 People Affected

People affected is normalized using logarithmic scaling with a reference value of 100 people.

Formula:

$$
NormalizedPeopleAffected =
\min\left(
\frac{\log(people\_affected + 1)}
{\log(101)}, 1
\right)
$$

The normalized value is multiplied by the 25% weight.

### 3.3 Waiting Time

Waiting time is normalized using a 10-minute reference value.

Formula:

$$
NormalizedWaitingTime =
\min\left(\frac{waiting\_time}{10}, 1\right)
$$

The normalized value is multiplied by the 20% weight.

### 3.4 Incident Type

Incident type uses direct mapping:

| Incident Type | Normalized Value |
|---|---:|
| MEDICAL | 1.00 |
| FIRE | 0.90 |
| POLICE | 0.80 |
| OTHER | 0.70 |

The normalized value is multiplied by the 15% weight.

### 3.5 Final Score

The final normalized score is calculated by summing the weighted contributions:

$$
FinalScore =
SeverityContribution +
PeopleAffectedContribution +
WaitingTimeContribution +
IncidentTypeContribution
$$

The result is converted to a 0–100 score.

### 3.6 Score Categories

| Score Range | Category |
|---|---|
| 0–24 | Low |
| 25–49 | Medium |
| 50–74 | High |
| 75–100 | Critical |

### 3.7 Explainability

The system provides a breakdown of the contribution of each scoring factor, together with the final score and category, to make the prioritization decision transparent and reviewable.