#!/bin/bash
# Launch all services for the flash-sale simulation.
# Usage: ./run_servers.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PGDATA="$PROJECT_DIR/pgdata"
NGINX_CONF="$PROJECT_DIR/nginx/nginx.conf"

echo "=== High-Throughput Inventory Tracker ==="
echo ""

# 1. Start project-local PostgreSQL (port 5433)
echo "[1/5] Starting project-local PostgreSQL on :5433..."
if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA" -l "$PGDATA/logfile" start
fi

# 2. Start Redis (if not already running)
echo "[2/5] Ensuring Redis is running on :6379..."
redis-cli ping >/dev/null 2>&1 || {
    redis-server --daemonize yes
    until redis-cli ping >/dev/null 2>&1; do sleep 0.1; done
}

# 3. Initialize database and cache
echo "[3/5] Initializing database and loading tokens..."
python -m scripts.init_db
python -m scripts.init_cache

# 4. Start 3 FastAPI instances
echo "[4/5] Starting 3 FastAPI instances..."
INSTANCE_ID=app-1 uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level warning &
INSTANCE_ID=app-2 uvicorn app.main:app --host 127.0.0.1 --port 8002 --log-level warning &
INSTANCE_ID=app-3 uvicorn app.main:app --host 127.0.0.1 --port 8003 --log-level warning &

# Wait for all instances to be ready
for port in 8001 8002 8003; do
    until curl -s "http://127.0.0.1:$port/inventory" >/dev/null 2>&1; do
        sleep 0.2
    done
done
echo "  All instances ready on :8001, :8002, :8003"

# 5. Start Nginx
echo "[5/5] Starting Nginx load balancer on :8080..."
nginx -c "$NGINX_CONF"

echo ""
echo "=== All systems ready ==="
echo "  PostgreSQL:    localhost:5433 (project-local, data in ./pgdata)"
echo "  Redis:         localhost:6379"
echo "  Load balancer: http://localhost:8080"
echo "  Direct access: http://localhost:8001, :8002, :8003"
echo ""
echo "Press Ctrl+C to stop all services."

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    nginx -s stop 2>/dev/null || true
    kill $(jobs -p) 2>/dev/null || true
    pg_ctl -D "$PGDATA" stop 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT

wait
