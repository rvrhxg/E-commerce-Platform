from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Product


def test_cart_persists_and_is_owner_scoped(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'cart.sqlite'}")
    headers = {'Origin': 'http://localhost:8000'}
    credentials = {'email': 'cart@example.test', 'password': 'long-test-password'}
    with app.state.sessions.begin() as session:
        session.add(Product(sku='cart', title='Cup', stock=5, price_kopecks=500))
    with TestClient(app) as client:
        assert client.get('/api/cart').status_code == 401
        assert client.post('/api/auth/register', json=credentials, headers=headers).status_code == 201
        for quantity in [0, -1, 100, True, 1.5, '2']:
            assert client.put('/api/cart/items', json={'product_id': 1, 'quantity': quantity}, headers=headers).status_code == 422
        assert client.put('/api/cart/items', json={'product_id': 1, 'quantity': 6}, headers=headers).status_code == 409
        assert client.put('/api/cart/items', json={'product_id': 999, 'quantity': 1}, headers=headers).status_code == 404
        assert client.put('/api/cart/items', json={'product_id': 1, 'quantity': 2}, headers=headers).status_code == 200
        assert client.put('/api/cart/items', json={'product_id': 1, 'quantity': 3}, headers=headers).status_code == 200
        assert len(client.get('/api/cart').json()['items']) == 1
        client.post('/api/auth/logout', json={}, headers=headers)
        client.post('/api/auth/register', json={**credentials, 'email': 'other@example.test'}, headers=headers)
        assert client.get('/api/cart').json()['items'] == []
        assert client.request('DELETE', '/api/cart/items/1', json={}, headers=headers).status_code == 200
        client.post('/api/auth/logout', json={}, headers=headers)
    app = create_app(f"sqlite:///{tmp_path / 'cart.sqlite'}")
    with TestClient(app) as client:
        assert client.post('/api/auth/login', json=credentials, headers=headers).status_code == 200
        assert client.get('/api/cart').json()['items'][0]['quantity'] == 3
        assert client.get('/api/products').json()[0]['stock'] == 5
        assert client.request('DELETE', '/api/cart/items/1', json={}, headers=headers).status_code == 200
        assert client.get('/api/cart').json()['items'] == []
