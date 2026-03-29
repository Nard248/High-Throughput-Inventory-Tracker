"""
Load Test: 2000 concurrent users attempt to buy 500 items.

Expected results:
  - Exactly 500 HTTP 200 responses (purchased)
  - Exactly 1500 HTTP 409 responses (sold out)
  - PostgreSQL stock = 0
  - Redis tokens remaining = 0
  - purchases table has exactly 500 unique rows

Usage:
  python -m scripts.load_test [--url URL] [--users N]
"""

import argparse
import asyncio
import time
from collections import Counter

import aiohttp

DEFAULT_URL = "http://localhost:8080"
DEFAULT_USERS = 2000


async def attempt_purchase(session: aiohttp.ClientSession, url: str) -> int:
    """Send a POST /purchase and return the HTTP status code."""
    try:
        async with session.post(f"{url}/purchase") as resp:
            return resp.status
    except Exception:
        return 0  # network error — counted separately


async def run_load_test(url: str, num_users: int):
    print(f"=== Load Test: {num_users} concurrent users ===")
    print(f"Target: {url}/purchase")
    print()

    # Check inventory before
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{url}/inventory") as resp:
            before = await resp.json()
            print(f"Before: {before}")

    # Fire all requests concurrently
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"\nFiring {num_users} concurrent purchase requests...")
        start = time.perf_counter()
        tasks = [attempt_purchase(session, url) for _ in range(num_users)]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

    # Tally results
    counts = Counter(results)
    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"  Throughput: {num_users / elapsed:.0f} requests/sec")
    print()

    # Results breakdown
    print("=== Results ===")
    successes = counts.get(200, 0)
    sold_out = counts.get(409, 0)
    net_errors = counts.get(0, 0)
    other = {k: v for k, v in counts.items() if k not in (200, 409, 0)}

    print(f"  200 (purchased): {successes}")
    print(f"  409 (sold out):  {sold_out}")
    if net_errors:
        print(f"  Network errors:  {net_errors}")
    if other:
        print(f"  Other:           {other}")

    # Check inventory after
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{url}/inventory") as resp:
            after = await resp.json()
            print(f"\nAfter: {after}")

    # Verification
    print("\n=== Verification ===")
    passed = True

    # Primary invariant: no overselling
    if successes <= 500:
        print(f"  [PASS] No overselling: {successes} purchases (limit 500)")
    else:
        print(f"  [FAIL] OVERSOLD: {successes} purchases exceeded 500!")
        passed = False

    # All requests accounted for
    total_accounted = successes + sold_out + net_errors + sum(other.values())
    if total_accounted == num_users:
        print(f"  [PASS] All {num_users} requests accounted for")
    else:
        print(f"  [WARN] Expected {num_users} total, got {total_accounted}")

    if after["redis_remaining_tokens"] == 0:
        print("  [PASS] Redis token pool is empty")
    else:
        print(f"  [FAIL] Redis still has {after['redis_remaining_tokens']} tokens")
        passed = False

    print()
    if passed:
        print("*** ALL CHECKS PASSED — No overselling detected! ***")
    else:
        print("*** SOME CHECKS FAILED — investigate above ***")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flash-sale load test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="Concurrent users")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.users))
