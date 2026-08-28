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
