import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from alembic import command
from alembic.config import Config


def database(url=None, initialize=True):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///atelier.sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 3}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function('lower', 1, lambda value: value.lower() if value else value, deterministic=True)
    if initialize:
        migrate(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def migrate(engine):
    """Explicit versioned upgrade, also used by the single-process demo startup."""
    config = Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
