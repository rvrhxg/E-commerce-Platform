from scripts.recording import recording_enabled, recording_options, pause, finish_recording
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
from app.models import Product, Order
from playwright.sync_api import expect

with tempfile.TemporaryDirectory(prefix="atelier-browser-") as temporary:
    url = "sqlite:///" + str(Path(temporary) / "browser.sqlite").replace("\\", "/")
    engine, sessions = database(url)
    with sessions.begin() as session:
        seed_catalog(session)
    engine.dispose()
    env = {**os.environ, "DATABASE_URL": url, "APP_ORIGIN": "http://127.0.0.1:8000"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory","--no-access-log", "--host", "127.0.0.1", "--port", "8000"], env=env)
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
            browser = playwright.chromium.launch(slow_mo=200 if recording_enabled() else 0)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, **recording_options())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:8000")
            page.locator(".product").first.wait_for()
            pause(page)
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
            pause(page)
            page.locator("#cart-dialog").screenshot(path="screenshots/cart.png")
            page.get_by_role("button", name="Оформить заказ", exact=True).click()
            page.locator("#orders").wait_for(state="visible")
            page.get_by_text("Заказ №1 · Оформлен", exact=True).wait_for()
            pause(page)
            page.screenshot(path="screenshots/order.png", full_page=True)
            page.get_by_role("button", name="Каталог", exact=True).click()
            page.set_viewport_size({"width": 390, "height": 844})
            pause(page)
            page.screenshot(path="screenshots/store-mobile.png", full_page=True)
            page.get_by_role("button",name="Выйти",exact=True).click()
            page.get_by_role("button",name="Войти",exact=True).click()
            page.get_by_role("button",name="Создать аккаунт",exact=True).click()
            auth.get_by_label("Email",exact=True).fill("buyer@example.test")
            auth.get_by_label("Пароль",exact=True).fill("isolated-browser-password")
            auth.get_by_role("button",name="Продолжить",exact=True).click()
            auth.wait_for(state="hidden")
            if not recording_enabled():
                # Add disposable records only after the portfolio screenshots.
                engine, sessions = database(url)
                with sessions.begin() as session:
                    session.add_all([Product(sku=f'PAGE-{i}',title=f'Pagination {i}',price_kopecks=100,stock=1) for i in range(25)])
                    session.add_all([Order(user_id=1,idempotency_key=f'page-key-{i}',request_hash='hash',total_kopecks=100,delivery_address='Test address') for i in range(25)])
                engine.dispose()
                page.reload()
                expect(page.locator('.product')).to_have_count(24)
                page.locator('#more-products').click()
                expect(page.locator('.product')).to_have_count(31)
                page.locator('#search').fill('Pagination 24')
                expect(page.locator('.product')).to_have_count(1)
                expect(page.locator('.product h3')).to_have_text('Pagination 24')
                page.locator('#category').select_option('decor')
                expect(page.locator('.product')).to_have_count(0)
                page.locator('#category').select_option('')
                expect(page.locator('.product')).to_have_count(1)
                page.locator('#search').fill('')
                expect(page.locator('.product')).to_have_count(24)
                page.locator('#orders-nav').click()
                expect(page.locator('#order-list .order')).to_have_count(24)
                page.get_by_role('button',name='Далее →',exact=True).click()
                expect(page.locator('#order-list .order')).to_have_count(2)
                page.get_by_role('button',name='← Назад',exact=True).click()
                expect(page.locator('#order-list .order')).to_have_count(24)
            assert not errors, errors
            finish_recording(page,'atelier')
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
