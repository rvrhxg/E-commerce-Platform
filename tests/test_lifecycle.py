import pytest
from sqlalchemy import select
from app.checkout import checkout, change_order_status
from app.database import database
from app.domain import ValidationError
from app.models import Product, User


def test_cancellation_restocks_once_and_terminal_order_stays_closed(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'lifecycle.sqlite'}")
    try:
        with sessions.begin() as session:
            session.add(User(email="buyer@example.test", name="Buyer", password_hash="unused"))
            session.add(Product(sku="PLATE", title="Plate", stock=5, price_kopecks=90000))
        with sessions.begin() as session:
            order = checkout(session, 1, [{"product_id": 1, "quantity": 2}], "Demo address", "lifecycle-1")
            order_id = order.id
        with sessions.begin() as session:
            change_order_status(session, order_id, "cancelled")
        with sessions.begin() as session:
            change_order_status(session, order_id, "cancelled")
            assert session.scalar(select(Product)).stock == 5
        with pytest.raises(ValidationError), sessions.begin() as session:
            change_order_status(session, order_id, "processing")
    finally:
        engine.dispose()
