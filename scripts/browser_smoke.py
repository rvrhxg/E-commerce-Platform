"""Run only against a disposable CI database and local app."""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.database import database
from app.seed import seed_catalog

with tempfile.TemporaryDirectory(prefix="atelier-browser-") as temporary:
    url = "sqlite:///" + str(Path(temporary) / "browser.sqlite").replace("\\", "/")
    engine, sessions = database(url)
    with sessions.begin() as session:
        seed_catalog(session)
    engine.dispose()
    env = {**os.environ, "DATABASE_URL": url, "APP_ORIGIN": "http://127.0.0.1:8000"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000"], env=env)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1)
                break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Store did not start")
        Path("screenshots").mkdir(exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:8000")
            page.locator(".product").first.wait_for()
            page.screenshot(path="screenshots/store-desktop.png", full_page=True)
            page.get_by_role("button", name="Войти", exact=True).click()
            page.get_by_role("button", name="Создать аккаунт", exact=True).click()
            auth = page.locator("#auth-dialog")
            auth.get_by_label("Имя", exact=True).fill("Алексей Морозов")
            auth.get_by_label("Email", exact=True).fill("buyer@example.test")
            auth.get_by_label("Пароль", exact=True).fill("isolated-browser-password")
            auth.get_by_role("button", name="Продолжить", exact=True).click()
            auth.wait_for(state="hidden")
            page.locator(".product").first.get_by_role("button", name="В корзину +", exact=True).click()
            page.get_by_role("button", name="Корзина").click()
            page.get_by_label("Адрес доставки").fill("Демонстрационный адрес доставки")
            page.locator("#cart-dialog").screenshot(path="screenshots/cart.png")
            page.get_by_role("button", name="Оформить заказ", exact=True).click()
            page.locator("#orders").wait_for(state="visible")
            page.get_by_text("Заказ №1 · Оформлен", exact=True).wait_for()
            page.screenshot(path="screenshots/order.png", full_page=True)
            page.get_by_role("button", name="Каталог", exact=True).click()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path="screenshots/store-mobile.png", full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
