"""Explicit demo catalog and optional administrator, no built-in credentials."""
import argparse
import getpass
from sqlalchemy import func, select
from .database import database
from .models import Product, User
from .security import hash_password

CATALOG = [
    ("CUP-01", "Чашка Тёплый песок", "Керамика ручной формы, 300 мл.", "ceramics", 129000, 12),
    ("BOWL-01", "Глубокая тарелка", "Матовая глазурь и лаконичная форма.", "ceramics", 189000, 8),
    ("VASE-01", "Ваза Тихий берег", "Небольшая ваза для сухоцветов.", "decor", 249000, 5),
    ("LINEN-01", "Льняная салфетка", "Натуральный лён, 40 × 40 см.", "textiles", 79000, 20),
    ("TRAY-01", "Поднос из дерева", "Массив дерева с масляной отделкой.", "decor", 329000, 6),
    ("PLATE-01", "Тарелка Светлый день", "Сервировочная тарелка, 24 см.", "ceramics", 159000, 10),
]


def seed_catalog(session):
    if session.scalar(select(func.count()).select_from(Product)):
        raise ValueError("Catalog must be empty; existing products will not be changed")
    for sku, title, description, category, price, stock in CATALOG:
        session.add(Product(sku=sku, title=title, description=description, category=category, price_kopecks=price, stock=stock))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--admin-email")
    args = parser.parse_args()
    if not args.catalog and not args.admin_email:
        parser.error("Choose --catalog and/or --admin-email")
    password_hash = hash_password(getpass.getpass("New administrator password: ")) if args.admin_email else None
    engine, sessions = database()
    try:
        with sessions.begin() as session:
            if args.catalog:
                seed_catalog(session)
            if args.admin_email:
                email = args.admin_email.strip().lower()
                if "@" not in email or len(email) > 254:
                    raise ValueError("Invalid administrator email")
                if session.scalar(select(User).where(User.email == email)):
                    raise ValueError("Account already exists; no promotion performed")
                session.add(User(email=email, name="Администратор", password_hash=password_hash, is_admin=True))
        print("Requested setup completed")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
