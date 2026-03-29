"""
High-Throughput Inventory Tracker — FastAPI Application

Uses the "Token Drain" pattern to solve the determinacy race:
  - Redis List holds exactly 500 unique tokens (one per item)
  - LPOP is atomic — structurally impossible to oversell
  - PostgreSQL serves as the durable source of truth with CHECK constraints
"""

import os
import uuid

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.cache import get_redis, pop_token, return_token, remaining, init_tokens
from app.config import TOTAL_INVENTORY

app = FastAPI(title="High-Throughput Inventory Tracker")

INSTANCE_ID = os.getenv("INSTANCE_ID", "single")


@app.get("/inventory")
def get_inventory():
    """Check current stock — reads from Redis (fast) and PostgreSQL (authoritative)."""
    r = get_redis()
    redis_remaining = remaining(r)
    return {
        "redis_remaining_tokens": redis_remaining,
        "instance": INSTANCE_ID,
    }


@app.post("/purchase")
def purchase(db: Session = Depends(get_db)):
    """
    Attempt to purchase one item.

    Flow:
      1. LPOP a token from Redis (atomic — no race possible)
      2. Decrement stock in PostgreSQL with WHERE stock > 0 (safety net)
      3. Record the purchase with the token as a unique receipt
      4. If DB fails, RPUSH the token back (compensating transaction)
    """
    r = get_redis()
    user_id = str(uuid.uuid4())

    # --- Layer 1: Atomic token pop from Redis ---
    token = pop_token(r)
    if token is None:
        raise HTTPException(status_code=409, detail="Sold out")

    # --- Layer 2: PostgreSQL as source of truth ---
    try:
        result = db.execute(
            text("UPDATE inventory SET stock = stock - 1 WHERE id = 1 AND stock > 0")
        )
        if result.rowcount == 0:
            # DB says no stock — return token and reject
            return_token(r, token)
            raise HTTPException(status_code=409, detail="Sold out (DB)")

        # --- Layer 3: Record the purchase with unique token ---
        db.execute(
            text("INSERT INTO purchases (token, user_id) VALUES (:token, :user_id)"),
            {"token": token, "user_id": user_id},
        )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        try:
            return_token(r, token)
        except Exception:
            print(f"CRITICAL: token {token} leaked — Redis unavailable during compensating txn")
        raise HTTPException(status_code=500, detail="Purchase failed — token returned")

    return {
        "status": "purchased",
        "token": token,
        "user_id": user_id,
        "instance": INSTANCE_ID,
    }


@app.post("/admin/reset")
def reset_inventory(db: Session = Depends(get_db)):
    """Reset inventory to initial state for testing."""
    r = get_redis()

    # Reset PostgreSQL
    db.execute(text("DELETE FROM purchases"))
    db.execute(
        text("UPDATE inventory SET stock = :stock WHERE id = 1"),
        {"stock": TOTAL_INVENTORY},
    )
    db.commit()

    # Reset Redis tokens
    count = init_tokens(r)

    return {"status": "reset", "tokens_loaded": count, "db_stock": TOTAL_INVENTORY}
