"""Configuration for Redis and PostgreSQL connections."""

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_TOKENS_KEY = "inventory:tokens"

POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "CIS2026"
POSTGRES_HOST = "127.0.0.1"
POSTGRES_PORT = 5433
POSTGRES_DB = "inventory_tracker"

DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

TOTAL_INVENTORY = 500
