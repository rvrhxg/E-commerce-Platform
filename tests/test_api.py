from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Product


def test_api_checkout_replay_owner_isolation_logout_and_strict_inputs(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'api.sqlite'}")
    with app.state.sessions.begin() as session:
        session.add(Product(sku="CUP", title="Cup", price_kopecks=123450, stock=3))
    headers = {"Origin": "http://localhost:8000"}
    with TestClient(app) as alice, TestClient(app) as bob:
        credentials = {"email": "alice@example.test", "password": "long-test-password", "name": "Alice", "is_admin": True}
        response = alice.post("/api/auth/register", json=credentials, headers=headers)
        assert response.status_code == 201
        assert response.json()["is_admin"] is False
        assert "HttpOnly" in response.headers["set-cookie"]
        credentials["email"] = "bob@example.test"
        assert bob.post("/api/auth/register", json=credentials, headers=headers).status_code == 201
        payload = {"items": [{"product_id": 1, "quantity": 2}], "address": "Demo delivery address", "idempotency_key": "api-checkout-1"}
        first = alice.post("/api/orders", json=payload, headers=headers)
        assert first.status_code == 201, first.text
        assert first.json()["total_kopecks"] == 246900
        repeated = alice.post("/api/orders", json=payload, headers=headers)
        assert repeated.json()["id"] == first.json()["id"]
        assert bob.get("/api/orders").json() == []
        assert alice.get("/api/products").json()[0]["stock"] == 1
        changed = {**payload, "address": "Different delivery address"}
        assert alice.post("/api/orders", json=changed, headers=headers).status_code == 409
        invalid = {**payload, "items": [{"product_id": 1, "quantity": True}]}
        assert alice.post("/api/orders", json=invalid, headers=headers).status_code == 422
        assert alice.post("/api/orders", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
        assert alice.post("/api/orders", content="x" * 65537, headers={**headers, "Content-Type": "application/json"}).status_code == 413
        assert alice.post("/api/auth/logout", json={}, headers=headers).status_code == 200
        assert alice.get("/api/orders").status_code == 401
        assert alice.post("/api/auth/login",json={"email":"alice@example.test","password":"long-test-password","name":""},headers=headers).status_code == 200