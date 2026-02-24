# Project Context: Example Web API Service (Demo)

> **This is an example file.** Replace it with your own project context, or run
> `python generate_context.py --project-dir /path/to/your/project` to generate
> it automatically from your source code.

---

## System Overview

This system is a Python-based REST API service that provides product catalog management and order processing for an e-commerce platform. It runs as a long-lived daemon, handling concurrent HTTP requests via an async worker pool.

The service integrates with a PostgreSQL database, a Redis cache, and an external payment provider. It is deployed behind an Nginx reverse proxy and exposes a Prometheus `/metrics` endpoint.

## Architecture

```
nginx → API (FastAPI) → PostgreSQL (primary storage)
                      → Redis      (session cache, rate limiting)
                      → PaymentAPI (external, HTTP)
                      → S3         (file uploads)
```

## Key Components

| Module | Responsibility |
|--------|---------------|
| `src/api/` | FastAPI routers, request validation, response serialisation |
| `src/db/` | SQLAlchemy models, migrations (Alembic), connection pool |
| `src/cache/` | Redis client wrapper, TTL management |
| `src/payments/` | Payment gateway client, retry logic, webhook handling |
| `src/workers/` | Background jobs: order expiry, email notifications |
| `src/auth/` | JWT authentication, rate limiting middleware |

## Log Format

```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL     | module:function:line - message
```

Example lines:
```
2026-01-15 10:23:01.123 | INFO      | api.orders:create:45 - Order 8821 created (user=1042, total=$49.99)
2026-01-15 10:23:01.567 | DEBUG     | db.pool:acquire:12 - Connection acquired (pool_size=8/20)
2026-01-15 10:23:05.890 | WARNING   | payments.client:charge:88 - Retry 1/3 for payment txn_abc123
2026-01-15 10:23:09.001 | ERROR     | workers.expiry:run:33 - Failed to expire order 7799: DB timeout
```

## Normal Operating Metrics

| Metric | Expected Range |
|--------|----------------|
| HTTP 2xx rate | > 98% |
| DB query latency (p95) | < 50 ms |
| Redis hit rate | > 90% |
| Payment success rate | > 97% |
| Background job cycle time | < 30 s |
| Worker pool usage | < 70% |

## Normal vs. Anomalous Behaviour

### Normal (not an issue)
- Occasional `DEBUG` messages about cache misses on cold start
- INFO logs about DB connection pool resizing during load spikes
- Payment retries (up to 3) — these are handled and resolved
- Short-lived 429 (rate-limit) responses from the payment API with automatic back-off

### Anomalous (investigate)
- `ERROR` in `db.pool` — connection exhaustion or DB unreachable
- `ERROR` in `payments.client` after all retries — failed transactions
- HTTP 5xx rate > 1% sustained over 5 minutes
- Redis connection failures — affects session auth for all users
- Memory growth in worker processes not followed by GC

## Critical Business Paths

1. **Order creation** — `POST /orders` → validate → charge payment → persist → notify
2. **User authentication** — JWT validation on every request; Redis session cache
3. **Order expiry worker** — runs every 60 s; must complete within 30 s
