"""Database setup — PostgreSQL via SQLAlchemy."""

import os
from sqlalchemy import create_engine, Column, Text, Integer, Float, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Render uses postgres:// but SQLAlchemy 2.x needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None

Base = declarative_base()


class ResearchHistory(Base):
    __tablename__ = "research_history"

    id = Column(Text, primary_key=True)
    saved_at = Column(DateTime, nullable=False)
    topic = Column(Text, nullable=False)
    layer_count = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    total_sources = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    report = Column(JSONB, nullable=False)


def init_db():
    """Create tables if they don't exist."""
    if engine:
        Base.metadata.create_all(engine)
