import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.models import User, LoginSession, Product, Order
from app.security import token_hash

HEADERS = {'Origin': 'http://localhost:8000'}
PRODUCT = dict(sku='secure', title='Cup', price_kopecks=100, stock=100)


@pytest.fixture
def app(tmp_path):
    return create_app(f"sqlite:///{tmp_path / 'auth.sqlite'}")


def register(client, email='buyer@example.test'):
    return client.post('/api/auth/register', json=dict(email=email,password='long-test-password',name='Buyer'),headers=HEADERS)


def test_anonymous_customer_admin_boundaries_and_revoked_session(app):
    with TestClient(app) as client:
        assert client.get('/api/orders').status_code == 401
        assert client.get('/api/admin/orders').status_code == 401
        assert client.post('/api/admin/products',json=PRODUCT,headers=HEADERS).status_code == 401
        assert register(client).status_code == 201
        assert client.get('/api/admin/orders').status_code == 403
        assert client.post('/api/admin/products',json=PRODUCT,headers=HEADERS).status_code == 403
        assert client.patch('/api/admin/orders/999',json={'status':'cancelled'},headers=HEADERS).status_code == 403
        with app.state.sessions.begin() as session:
            session.scalar(select(User)).is_admin = True
        assert client.post('/api/admin/products',json=PRODUCT,headers=HEADERS).status_code == 201
        token = client.cookies.get('session')
        assert client.post('/api/auth/logout',json={},headers=HEADERS).status_code == 200
        client.cookies.set('session',token)
        assert client.get('/api/auth/me').status_code == 401


def test_expired_forged_sessions_invalid_password_and_csrf(app):
    with TestClient(app) as client:
        register(client)
        token = client.cookies.get('session')
        with app.state.sessions.begin() as session:
            session.get(LoginSession,token_hash(token)).expires_at = int(time.time())-1
        assert client.get('/api/orders').status_code == 401
        client.cookies.set('session','f'*64)
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/auth/login',json=dict(email='buyer@example.test',password='wrong-long-password'),headers=HEADERS).status_code == 401
        assert client.post('/api/auth/login',json=dict(email='buyer@example.test',password='long-test-password')).status_code == 403


def test_pagination_stable_pages_owner_scoped_totals_and_validation(app):
    with TestClient(app) as alice, TestClient(app) as bob:
        register(alice)
        register(bob,'other@example.test')
        with app.state.sessions.begin() as session:
            session.add_all([Product(sku=f'p{i}',title=f'Product{i}',price_kopecks=100,stock=1) for i in range(5)])
            for owner in (1,2):
                session.add_all([Order(user_id=owner,idempotency_key=f'key-{owner}-{i}',request_hash='hash',total_kopecks=100,delivery_address='Address') for i in range(5)])
        first = alice.get('/api/products?limit=2&offset=0')
        second = alice.get('/api/products?limit=2&offset=2')
        assert first.headers['x-total-count'] == '5'
        assert {p['id'] for p in first.json()}.isdisjoint(p['id'] for p in second.json())
        orders = alice.get('/api/orders?limit=2')
        assert orders.headers['x-total-count'] == '5'
        assert len(orders.json()) == 2
        assert {o['id'] for o in orders.json()}.isdisjoint(o['id'] for o in bob.get('/api/orders?limit=100').json())
        assert alice.get('/api/orders?offset=99').json() == []
        for query in ('limit=0','limit=101','offset=-1','limit=abc'):
            assert alice.get('/api/products?'+query).status_code == 422
