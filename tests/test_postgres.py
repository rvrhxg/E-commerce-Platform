"""Opt-in real PostgreSQL race test. Uses a unique schema, never resets public data."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import Base, Product, User
from app.checkout import checkout, CheckoutConflict


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="PostgreSQL test URL not configured")
def test_concurrent_checkout_cannot_oversell():
    schema = "test_" + uuid.uuid4().hex
    root = create_engine(os.environ["TEST_POSTGRES_URL"])
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(os.environ["TEST_POSTGRES_URL"], connect_args={"options": f"-csearch_path={schema}"})
    sessions = sessionmaker(engine, expire_on_commit=False)
    try:
        Base.metadata.create_all(engine)
        with sessions.begin() as session:
            session.add(User(email="race@example.test", name="Race", password_hash="unused"))
            session.add(Product(sku="LAST", title="Last item", price_kopecks=10000, stock=1))
        barrier = Barrier(2)
        def purchase(index):
            barrier.wait(timeout=10)
            try:
                with sessions.begin() as session:
                    checkout(session, 1, [{"product_id": 1, "quantity": 1}], "Race address", f"race-key-{index}")
                return "success"
            except CheckoutConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(purchase, [1, 2]))
        assert sorted(results) == ["conflict", "success"]
        with sessions() as session:
            assert session.get(Product, 1).stock == 0
    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()
