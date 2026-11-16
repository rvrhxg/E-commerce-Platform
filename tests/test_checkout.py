import pytest
from sqlalchemy import func, select
from app.checkout import CheckoutConflict, checkout
from app.database import database
from app.models import Order, OrderItem, Product, User


@pytest.fixture
def store(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'shop.sqlite'}")
    with sessions.begin() as session:
        session.add(User(email="customer@example.test", name="Customer", password_hash="unused"))
        session.add_all([
            Product(sku="CUP", title="Cup", price_kopecks=129950, stock=3),
            Product(sku="BOWL", title="Bowl", price_kopecks=200000, stock=0),
        ])
    yield sessions
    engine.dispose()


def test_replay_does_not_decrement_stock_and_prices_are_snapshots(store):
    with store.begin() as session:
        order = checkout(session, 1, [{"product_id": 1, "quantity": 2}], "Demo address", "checkout-001")
        order_id = order.id
        assert order.total_kopecks == 259900
    with store.begin() as session:
        session.get(Product, 1).price_kopecks = 1
    with store.begin() as session:
        repeated = checkout(session, 1, [{"product_id": 1, "quantity": 2}], "Demo address", "checkout-001")
        assert repeated.id == order_id
        assert repeated.total_kopecks == 259900
        assert session.get(Product, 1).stock == 1
        assert session.scalar(select(OrderItem)).unit_price_kopecks == 129950
    with pytest.raises(CheckoutConflict), store.begin() as session:
        checkout(session, 1, [{"product_id": 1, "quantity": 1}], "Demo address", "checkout-001")


def test_later_stock_failure_rolls_back_all_prior_decrements(store):
    with pytest.raises(CheckoutConflict), store.begin() as session:
        checkout(session, 1, [{"product_id": 1, "quantity": 1}, {"product_id": 2, "quantity": 1}], "Demo address", "checkout-002")
    with store() as session:
        assert session.get(Product, 1).stock == 3
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_overselling_rejected_after_successful_order(store):
    with store.begin() as session:
        checkout(session, 1, [{"product_id": 1, "quantity": 3}], "Demo address", "checkout-003")
    with pytest.raises(CheckoutConflict), store.begin() as session:
        checkout(session, 1, [{"product_id": 1, "quantity": 1}], "Demo address", "checkout-004")
    with store() as session:
        assert session.get(Product, 1).stock == 0
        assert session.scalar(select(func.count()).select_from(Order)) == 1
