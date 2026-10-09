# dragonfly-limiter-pool

Seat `bot-01-systems-backend`. Graph `ut-mv10s1se-50878383`. Linear SPE-9294.

One shared Redis pool, a 150 ms rate-limit budget, the existing `CircuitBreaker`, and one Lua `SCRIPT LOAD`. An unreachable or slow Dragonfly answers from the local token bucket. `/health` stays `ok`.

Commands and the unverified list are in `dragonfly-limiter-pool.json`. `approved_by` is empty until Lead or a human stamps it. Greptile is not 5/5 on this revision.
