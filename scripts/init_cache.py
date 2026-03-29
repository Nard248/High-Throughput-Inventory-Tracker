"""Push 500 unique tokens into the Redis list."""

from app.cache import init_tokens, get_redis, remaining


if __name__ == "__main__":
    r = get_redis()
    count = init_tokens(r)
    print(f"Loaded {count} tokens into Redis. Remaining: {remaining(r)}")
