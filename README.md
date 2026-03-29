# High-Throughput Inventory Tracker

A flash-sale inventory system designed to handle thousands of concurrent purchase attempts on a limited stock of 500 items — without overselling.

## Architecture

```
                         +──────────────+
      2000+ users ──────>│    Nginx     │
       concurrent        │    :8080     │
                         +──────┬───────+
                                │ round-robin
                     +──────────┼──────────+
                     v          v          v
               +──────────+──────────+──────────+
               │ FastAPI  │ FastAPI  │ FastAPI  │
               │  :8001   │  :8002   │  :8003   │
               +────┬─────+────┬─────+────┬─────+
                    │          │          │
                    v          v          v
               +─────────────────────────────────+
               │          Redis :6379             │
               │  inventory:tokens [List of 500]  │
               +───────────────┬─────────────────+
                               │
                               v
               +─────────────────────────────────+
               │     PostgreSQL :5433 (local)      │
               │  inventory + purchases tables    │
               +─────────────────────────────────+
```

**Three independent FastAPI processes** share no memory — they coordinate entirely through Redis and PostgreSQL, proving this is a truly distributed solution.

## The Determinacy Race Problem

In a naive implementation, concurrent users can oversell:

```
Thread A: READ stock = 1
Thread B: READ stock = 1        <-- stale read
Thread A: stock > 0? YES -> DECR -> stock = 0   (correct)
Thread B: stock > 0? YES -> DECR -> stock = -1  (OVERSOLD!)
```

The root cause is the **check-then-act** pattern: separating the read from the write creates a window where concurrent operations make decisions on stale data.

## The Solution: Token Drain Pattern

Instead of managing a counter (which requires careful synchronization), we model the inventory as a **finite pool of unique tokens** stored in a Redis List:

```
Initialization:  RPUSH inventory:tokens tok-0001 tok-0002 ... tok-0500

Purchase:        LPOP inventory:tokens
                 -> got a token? You may buy.
                 -> got nil?     Sold out.
```

### Why this eliminates the race entirely

| Counter-based (DECR)               | Token Drain (LPOP)                    |
|------------------------------------|---------------------------------------|
| Read -> Check -> Write (3 steps)   | Pop (1 atomic step)                   |
| Can go negative without Lua guard  | Can't pop from empty list             |
| Race lives in the gap between ops  | No gap — single atomic operation      |
| Needs explicit bounds checking     | Structure IS the constraint           |

`LPOP` on a Redis List is **atomic** and **bounded by the list's contents**. You cannot pop what doesn't exist. There are exactly 500 tokens, so exactly 500 purchases can succeed.

### Layered Defense

| Layer | Mechanism | Protects Against |
|-------|-----------|-----------------|
| L1: Redis LPOP | Atomic pop from finite list | Race conditions |
| L2: PostgreSQL WHERE | `UPDATE ... SET stock = stock - 1 WHERE stock > 0` | Redis failure |
| L3: DB CHECK | `CHECK (stock >= 0)` on inventory table | Any bug bypassing L2 |
| L4: UNIQUE token | `purchases.token` is UNIQUE | Replay/double-spend |
| Compensating txn | If DB fails -> RPUSH token back | Leaked tokens |

## Purchase Flow

```
1. Client -> POST /purchase
2. Server -> LPOP inventory:tokens (Redis, atomic)
3. If nil -> 409 "Sold Out"
4. If token received:
   a. UPDATE inventory SET stock = stock - 1 WHERE id=1 AND stock > 0
   b. If rows_affected = 0 -> RPUSH token back -> 409
   c. INSERT INTO purchases (token, user_id)
   d. COMMIT -> 200 with receipt token
5. If any DB error -> RPUSH token back -> 500
```

## Prerequisites

- Python 3.10+
- Redis server
- PostgreSQL (installed, but **not** using your system instance — a project-local one is created)
- Nginx

On macOS with Homebrew:
```bash
brew install redis nginx postgresql@14
```

## Setup and Run

The project creates its own **self-contained PostgreSQL instance** inside the `pgdata/` folder (port 5433, user: `postgres`, password: `CIS2026`). This does not touch your system PostgreSQL.

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize project-local PostgreSQL (only needed once)
initdb -D pgdata -U postgres --auth=password --pwfile=<(echo "CIS2026")
# Edit pgdata/postgresql.conf: set port = 5433

# 4. Start the local PostgreSQL instance
pg_ctl -D pgdata -l pgdata/logfile start

# 5. Initialize database (creates DB, tables, seeds 500 items)
python -m scripts.init_db

# 6. Load 500 tokens into Redis
python -m scripts.init_cache

# 7. Start 3 FastAPI instances
INSTANCE_ID=app-1 uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level warning &
INSTANCE_ID=app-2 uvicorn app.main:app --host 127.0.0.1 --port 8002 --log-level warning &
INSTANCE_ID=app-3 uvicorn app.main:app --host 127.0.0.1 --port 8003 --log-level warning &

# 8. Start Nginx load balancer
nginx -c "$(pwd)/nginx/nginx.conf"

# 9. Run the load test (2000 concurrent users)
python -m scripts.load_test
```

Or use the all-in-one script:
```bash
./run_servers.sh
# Then in another terminal:
python -m scripts.load_test
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/purchase` | Attempt to buy one item |
| `GET` | `/inventory` | Check remaining stock |
| `POST` | `/admin/reset` | Reset inventory for re-testing |

## Load Test Results

```
=== Load Test: 2000 concurrent users ===
Target: http://localhost:8080/purchase

Firing 2000 concurrent purchase requests...

Completed in 0.68s
  Throughput: 2920 requests/sec

=== Results ===
  200 (purchased): 500
  409 (sold out):  1500

=== Verification ===
  [PASS] Exactly 500 purchases succeeded
  [PASS] Exactly 1500 correctly rejected
  [PASS] Redis token pool is empty

*** ALL CHECKS PASSED — No overselling detected! ***
```

PostgreSQL verification:
```
 stock = 0
 total_purchases = 500
 unique_tokens = 500
```

## Project Structure

```
.
├── pgdata/                # Project-local PostgreSQL data (port 5433, auto-created)
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app with /purchase, /inventory, /admin/reset
│   ├── config.py          # Redis & PostgreSQL connection settings
│   ├── database.py        # SQLAlchemy engine and session
│   ├── models.py          # Inventory and Purchase table models
│   └── cache.py           # Redis Token Drain operations
├── nginx/
│   └── nginx.conf         # Load balancer (round-robin, 3 backends)
├── scripts/
│   ├── __init__.py
│   ├── init_db.py         # Create database, tables, seed inventory
│   ├── init_cache.py      # Push 500 tokens into Redis
│   └── load_test.py       # Concurrent load test with verification
├── requirements.txt
├── run_servers.sh          # All-in-one startup script
└── README.md
```

## Key Design Decisions

1. **Token Drain over DECR**: A Redis List of unique tokens is structurally bounded — LPOP can't oversell because you can't pop from an empty list. This is fundamentally safer than a counter.

2. **Compensating transactions**: If PostgreSQL fails after a token is popped, we push the token back. This prevents token leaks.

3. **Three independent processes**: No shared memory between app instances proves the solution works in a distributed setting.

4. **PostgreSQL as source of truth**: Redis is fast but volatile. PostgreSQL with CHECK constraints provides the durable guarantee.
# High-Throughput-Inventory-Tracker
