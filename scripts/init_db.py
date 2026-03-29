"""Create the database, tables, and seed the inventory with 500 items."""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.config import (
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST,
    POSTGRES_PORT, POSTGRES_DB, TOTAL_INVENTORY,
)
from app.database import engine, Base
from app.models import Inventory  # noqa: F401 — registers the model


def create_database():
    conn = psycopg2.connect(
        dbname="postgres",
        user=POSTGRES_USER, password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST, port=POSTGRES_PORT,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{POSTGRES_DB}'")
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {POSTGRES_DB}")
        print(f"Database '{POSTGRES_DB}' created.")
    else:
        print(f"Database '{POSTGRES_DB}' already exists.")
    cur.close()
    conn.close()


def create_tables_and_seed():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Tables created.")

    from sqlalchemy.orm import Session
    with Session(engine) as session:
        item = Inventory(id=1, item_name="Flash Sale Item", stock=TOTAL_INVENTORY)
        session.add(item)
        session.commit()
        print(f"Seeded inventory: {TOTAL_INVENTORY} items.")


if __name__ == "__main__":
    create_database()
    create_tables_and_seed()
