"""Atomic cart/order contract against SQLite and opt-in real PostgreSQL."""
import os
import uuid
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from app.database import migrate
from app.checkout import checkout, CheckoutConflict
from app.models import Cart, CartItem, Product, User, Order


@pytest.fixture(params=['sqlite', 'postgres'])
def cart_store(request, tmp_path):
    root = None
    schema = 'cart_' + uuid.uuid4().hex
    if request.param == 'postgres':
        if not os.environ.get('TEST_POSTGRES_URL'):
            pytest.skip('PostgreSQL test URL not configured')
        root = create_engine(os.environ['TEST_POSTGRES_URL'])
        with root.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(os.environ['TEST_POSTGRES_URL'], connect_args={'options': f'-csearch_path={schema}'})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'atomic.sqlite'}")
    try:
        migrate(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions.begin() as session:
            user = User(email='atomic@example.test', name='Buyer', password_hash='unused')
            session.add(user)
            session.add_all([Product(sku='one', title='One', stock=10, price_kopecks=100), Product(sku='two', title='Two', stock=0, price_kopecks=200)])
            session.flush()
            cart = Cart(user_id=user.id, revision=1)
            session.add(cart)
            session.flush()
            session.add(CartItem(cart_id=cart.id, product_id=1, quantity=2))
        yield sessions
    finally:
        engine.dispose()
        if root:
            with root.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            root.dispose()


def test_atomic_cleanup_replay_and_new_items(cart_store):
    with cart_store.begin() as session:
        checkout(session, 1, [{'product_id': 1, 'quantity': 2}], 'Test address', 'atomic-success', 1)
    with cart_store.begin() as session:
        assert session.scalar(select(CartItem)) is None
        cart = session.scalar(select(Cart))
        cart.revision += 1
        session.add(CartItem(cart_id=cart.id, product_id=1, quantity=1))
    with cart_store.begin() as session:
        checkout(session, 1, [{'product_id': 1, 'quantity': 2}], 'Test address', 'atomic-success', 1)
        assert session.scalar(select(CartItem)).quantity == 1
        assert session.get(Product, 1).stock == 8


def test_stale_snapshot_preserves_cart(cart_store):
    with cart_store.begin() as session:
        session.scalar(select(Cart)).revision += 1
        session.scalar(select(CartItem)).quantity = 3
    with cart_store.begin() as session:
        checkout(session, 1, [{'product_id': 1, 'quantity': 2}], 'Test address', 'atomic-stale', 1)
        assert session.scalar(select(CartItem)).quantity == 3


def test_failed_order_rolls_back_cart_revision_and_stock(cart_store):
    with pytest.raises(CheckoutConflict), cart_store.begin() as session:
        checkout(session, 1, [{'product_id': 1, 'quantity': 2}, {'product_id': 2, 'quantity': 1}], 'Test address', 'atomic-failed', 1)
    with cart_store() as session:
        assert session.scalar(select(Cart)).revision == 1
        assert session.scalar(select(CartItem)).quantity == 2
        assert session.get(Product, 1).stock == 10
        assert session.scalar(select(Order)) is None
