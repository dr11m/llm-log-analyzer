# Analysis Rules: Example Web API Service (Demo)

> **This is an example file.** Replace it with your own rules, or run
> `python generate_context.py --project-dir /path/to/your/project` to generate
> them automatically.

---

## CRITICAL (system cannot operate normally)

**Criteria:**
- `ERROR` or `CRITICAL` level logs in core modules (`db.pool`, `auth`, `workers`)
- Database connection pool exhausted — all requests blocked
- Redis unavailable — authentication broken for all users
- Payment service unreachable after all retries — revenue loss
- Worker process crash — background jobs not running

**Why critical:**
- Direct user impact: requests fail or hang
- Possible data loss (uncommitted transactions)
- Revenue loss (failed payments)

**Example patterns:**
```
ERROR     | db.pool:acquire - Max connections reached (20/20), request dropped
ERROR     | cache.client:get - Redis connection refused (host=redis:6379)
ERROR     | payments.client:charge - All retries exhausted for txn_abc123
CRITICAL  | workers.expiry:run - Unhandled exception, worker stopped
```

---

## MEDIUM (degraded performance, monitoring required)

**Criteria:**
- DB query latency p95 > 200 ms (sustained > 5 min)
- HTTP 5xx rate between 1% and 5%
- Redis hit rate drops below 75%
- Payment retry rate > 10% of transactions
- Worker cycle time > 60 s (expected < 30 s)

**Example patterns:**
```
WARNING   | db.pool:acquire - Slow connection acquire: 350ms (threshold=50ms)
WARNING   | api.middleware:rate_limit - 429 rate for user 1042: 12 req/min
WARNING   | payments.client:charge - Retry 2/3 for txn_xyz (service latency: 8s)
WARNING   | workers.expiry:run - Cycle took 75s (expected <30s)
```

---

## LOW (cosmetic / noise, log for visibility only)

**Criteria:**
- Single failed request that did not recur
- `DEBUG` messages about internal state transitions
- Transient cache miss immediately followed by DB fetch (< 5 ms penalty)

**Example patterns:**
```
DEBUG     | cache.client:get - Miss for key=session:1042, fetching from DB
DEBUG     | db.pool:release - Connection returned to pool (pool_size=7/20)
```

---

## NOT an issue (expected behaviour)

**Criteria:**
- Payment retries that ultimately succeed
- Cache expiry and re-population under normal load
- Worker starting/stopping on schedule
- DB pool scaling on traffic spikes (within limits)
- INFO-level audit logs (order created, user logged in, etc.)

**Example patterns:**
```
INFO      | api.orders:create - Order 9901 created (user=2201, total=$12.50)
INFO      | auth.middleware:validate - JWT valid for user 2201
INFO      | workers.expiry:run - Cycle complete: 14 orders expired in 4.2s
```
