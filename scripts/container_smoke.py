"""Linux CI smoke: disposable schema on service PostgreSQL, isolated container."""
import os
import subprocess
import time
import uuid
from urllib.parse import quote
import httpx
from sqlalchemy import create_engine, text
from app.database import database
from app.seed import seed_catalog

schema = "container_" + uuid.uuid4().hex
name = "atelier-ci-" + uuid.uuid4().hex
root = create_engine(os.environ["TEST_POSTGRES_URL"])
created = False


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def ready():
    for _ in range(60):
        try:
            if httpx.get("http://127.0.0.1:8000/api/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.25)
    raise RuntimeError("Container not ready")


with root.begin() as connection:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
url = os.environ["TEST_POSTGRES_URL"] + "?options=" + quote(f"-csearch_path={schema}")
try:
    engine, sessions = database(url)
    with sessions.begin() as session:
        seed_catalog(session)
    engine.dispose()
    docker("run", "-d", "--name", name, "--network", "host", "-e", f"DATABASE_URL={url}", "-e", "APP_ORIGIN=http://127.0.0.1:8000", "atelier-test")
    created = True
    ready()
    with httpx.Client(base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"}) as client:
        credentials = {"email": "container@example.test", "password": uuid.uuid4().hex}
        assert client.post("/api/auth/register", json=credentials).status_code == 201
        payload = {"items": [{"product_id": 1, "quantity": 1}], "address": "Container demo address", "idempotency_key": "container-order-1"}
        order = client.post("/api/orders", json=payload)
        assert order.status_code == 201, order.text
        docker("restart", name)
        ready()
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        history = client.get("/api/orders").json()
        assert history[0]["id"] == order.json()["id"]
        assert docker("exec", name, "id", "-u") == "1000"
    print("Docker PostgreSQL order persistence and non-root checks passed")
except Exception:
    if created:
        print(docker("logs", name))
    raise
finally:
    if created:
        docker("rm", "-f", name)
    with root.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    root.dispose()
