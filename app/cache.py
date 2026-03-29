"""Redis cache operations for the Token Drain pattern."""

import redis

from app.config import REDIS_HOST, REDIS_PORT, REDIS_TOKENS_KEY, TOTAL_INVENTORY

pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=pool)


def init_tokens(r: redis.Redis | None = None):
    """Push TOTAL_INVENTORY unique tokens into the Redis list (idempotent)."""
    if r is None:
        r = get_redis()
    r.delete(REDIS_TOKENS_KEY)
    tokens = [f"tok-{i:04d}" for i in range(1, TOTAL_INVENTORY + 1)]
    r.rpush(REDIS_TOKENS_KEY, *tokens)
    return len(tokens)


def pop_token(r: redis.Redis) -> str | None:
    """Atomically pop one token. Returns token string or None if sold out."""
    return r.lpop(REDIS_TOKENS_KEY)


def return_token(r: redis.Redis, token: str):
    """Return a token to the pool (compensating transaction on DB failure)."""
    r.rpush(REDIS_TOKENS_KEY, token)


def remaining(r: redis.Redis) -> int:
    """How many tokens remain in the pool."""
    return r.llen(REDIS_TOKENS_KEY)
