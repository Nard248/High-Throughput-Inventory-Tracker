"""SQLAlchemy models for inventory and purchases."""

from sqlalchemy import Column, Integer, String, DateTime, CheckConstraint, func

from app.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    item_name = Column(String, nullable=False)
    stock = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("stock >= 0", name="stock_non_negative"),
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String, unique=True, nullable=False)
    user_id = Column(String, nullable=False)
    purchased_at = Column(DateTime, server_default=func.now())
