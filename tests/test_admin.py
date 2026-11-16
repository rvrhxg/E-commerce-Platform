from fastapi.testclient import TestClient
from app.main import create_app
from app.models import User
from sqlalchemy import select


def test_product_and_order_admin_routes_require_server_side_role(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'admin.sqlite'}")
    headers = {"Origin": "http://localhost:8000"}
    with TestClient(app) as client:
        client.post("/api/auth/register", headers=headers, json={"email": "admin@example.test", "password": "long-test-password"})
        data = {"sku": "TEST", "title": "Product", "price_kopecks": 10000, "stock": 4}
        assert client.post("/api/admin/products", headers=headers, json=data).status_code == 403
        assert client.get("/api/admin/orders").status_code == 403
        assert client.patch("/api/admin/orders/1", headers=headers, json={"status": "cancelled"}).status_code == 403
        with app.state.sessions.begin() as session:
            session.scalar(select(User)).is_admin = True
        response = client.post("/api/admin/products", headers=headers, json=data)
        assert response.status_code == 201
        assert client.post("/api/admin/products", headers=headers, json=data).status_code == 409
        assert client.get("/api/products").json()[0]["stock"] == 4
        assert client.post("/api/orders", headers=headers, json={"items": [{"product_id": response.json()["id"], "quantity": 1}], "address": "Demo address", "idempotency_key": "admin-order-1"}).status_code == 201
        assert client.patch("/api/admin/orders/1", headers=headers, json={"status": "cancelled"}).status_code == 200
        assert client.patch("/api/admin/orders/1", headers=headers, json={"status": "cancelled"}).status_code == 200
        assert client.get("/api/products").json()[0]["stock"] == 4
