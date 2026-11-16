from .observability import install_observability
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from .database import database
from .models import User, LoginSession, Product, Order, OrderItem
from .security import hash_password, verify_password, new_token, token_hash
from .checkout import checkout, CheckoutConflict, change_order_status
from .domain import ValidationError
from .catalog import Cursor, scope_for


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="Customer", max_length=100)


class BasketItem(BaseModel):
    product_id: StrictInt = Field(gt=0)
    quantity: StrictInt = Field(ge=1, le=99)


class CheckoutInput(BaseModel):
    items: list[BasketItem] = Field(min_length=1, max_length=100)
    address: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=80)


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="home", min_length=1, max_length=80)
    price_kopecks: StrictInt = Field(ge=0, le=100_000_000)
    stock: StrictInt = Field(ge=0, le=1_000_000)


class StatusInput(BaseModel):
    status: str = Field(min_length=1, max_length=20)


def create_app(url=None, origin=None):
    origin = origin or os.environ.get("APP_ORIGIN", "http://localhost:8000")
    secure = os.environ.get("ENVIRONMENT") == "production"
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("APP_ORIGIN must be an HTTP(S) origin without path or credentials")
    if secure and not origin.startswith("https://"):
        raise ValueError("Production requires HTTPS APP_ORIGIN")
    engine, sessions = database(url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="Atelier Commerce API", lifespan=lifespan)
    app.state.sessions = sessions
    attempts = {}
    dummy = hash_password("dummy-password-value")

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != origin:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Origin rejected"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path in {"/", "/app.js", "/style.css"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def identity(request, session):
        token = request.cookies.get("session", "")
        login = session.get(LoginSession, token_hash(token)) if len(token) == 64 else None
        if not login or login.expires_at <= int(time.time()):
            raise HTTPException(401, "Authentication required")
        return session.get(User, login.user_id)

    def profile(user):
        return {"id": user.id, "name": user.name, "email": user.email, "is_admin": user.is_admin}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with sessions.begin() as session:
            identity(request, session)
            session.delete(session.get(LoginSession, token_hash(request.cookies["session"])))
        response.delete_cookie("session", httponly=True, secure=secure, samesite="strict")
        return {"ok": True}

    @app.post("/api/auth/{action}")
    def auth(action: str, data: Credentials, request: Request, response: Response):
        if action not in {"login", "register"}:
            raise HTTPException(404)
        now = int(time.time())
        for key in list(attempts):
            if attempts[key][1] < now:
                del attempts[key]
        key = request.client.host
        count, until = attempts.get(key, (0, now + 60))
        attempts[key] = (count + 1, until)
        if count >= 15:
            raise HTTPException(429, "Try again later")
        with sessions.begin() as session:
            email = data.email.strip().lower()
            user = session.scalar(select(User).where(User.email == email))
            if action == "register":
                if not data.name.strip():
                    raise HTTPException(400,"Name required")
                if user:
                    raise HTTPException(409, "Email unavailable")
                user = User(email=email, name=data.name.strip(), password_hash=hash_password(data.password))
                session.add(user)
                try:
                    session.flush()
                except IntegrityError:
                    raise HTTPException(409, "Email unavailable")
                response.status_code = 201
            elif not verify_password(data.password, user.password_hash if user else dummy) or not user:
                raise HTTPException(401, "Invalid credentials")
            token = new_token()
            session.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=now+86400))
            response.set_cookie("session", token, httponly=True, secure=secure, samesite="strict", max_age=86400)
            return profile(user)

    @app.get("/api/auth/me")
    def me(request: Request):
        with sessions() as session:
            return profile(identity(request, session))

    @app.get("/api/products")
    def products(response: Response, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100)):
        with sessions() as session:
            from sqlalchemy import func
            response.headers['X-Total-Count'] = str(session.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))))
            return [{"id": p.id, "title": p.title, "description": p.description, "category": p.category, "price_kopecks": p.price_kopecks, "stock": p.stock} for p in session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id).offset(offset).limit(limit))]

    @app.get('/api/catalog')
    def catalog(q: str = Query('', max_length=100), category: str = Query('', max_length=80),
                min_price: int = Query(0, ge=0), max_price: int = Query(100_000_000, ge=0, le=100_000_000),
                in_stock: bool = False, limit: int = Query(24, ge=1, le=100), cursor: str = Query('', max_length=512)):
        if min_price > max_price:
            raise HTTPException(422, 'Invalid price range')
        q = q.strip().lower()
        scope = scope_for((q, category, min_price, max_price, in_stock))
        with sessions() as session:
            try:
                position = Cursor.decode(cursor, scope) if cursor else Cursor(0, session.scalar(select(func.max(Product.id))) or 0, scope)
            except ValueError as error:
                raise HTTPException(400, str(error))
            conditions = [Product.active.is_(True), Product.id > position.after, Product.id <= position.ceiling,
                          Product.price_kopecks >= min_price, Product.price_kopecks <= max_price]
            if q:
                conditions.append(or_(func.lower(Product.title).contains(q, autoescape=True), func.lower(Product.description).contains(q, autoescape=True)))
            if category:
                conditions.append(Product.category == category)
            if in_stock:
                conditions.append(Product.stock > 0)
            rows = list(session.scalars(select(Product).where(*conditions).order_by(Product.id).limit(limit + 1)))
            page = rows[:limit]
            return {'items': [{'id': p.id, 'title': p.title, 'description': p.description, 'category': p.category,
                               'price_kopecks': p.price_kopecks, 'stock': p.stock} for p in page],
                    'next_cursor': Cursor(page[-1].id, position.ceiling, scope).encode() if len(rows) > limit else None}

    def order_data(session, order):
        return {"id": order.id, "status": order.status, "total_kopecks": order.total_kopecks, "created_at": order.created_at, "items": [{"product_id": i.product_id, "title": i.title, "unit_price_kopecks": i.unit_price_kopecks, "quantity": i.quantity} for i in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))]}

    @app.post("/api/orders", status_code=201)
    def place(data: CheckoutInput, request: Request):
        try:
            with sessions.begin() as session:
                user = identity(request, session)
                order = checkout(session, user.id, [i.model_dump() for i in data.items], data.address, data.idempotency_key)
                return order_data(session, order)
        except (CheckoutConflict, IntegrityError):
            raise HTTPException(409, "Stock or idempotency conflict; retry the same request")
        except ValidationError as error:
            raise HTTPException(400, str(error))

    @app.get("/api/orders")
    def orders(request: Request, response: Response, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100)):
        with sessions() as session:
            user = identity(request, session)
            from sqlalchemy import func
            response.headers['X-Total-Count'] = str(session.scalar(select(func.count()).select_from(Order).where(Order.user_id == user.id)))
            return [order_data(session, o) for o in session.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).offset(offset).limit(limit))]

    def admin(request, session):
        user = identity(request, session)
        if not user.is_admin:
            raise HTTPException(403, "Administrator required")
        return user

    @app.post("/api/admin/products", status_code=201)
    def add_product(data: ProductInput, request: Request):
        try:
            with sessions.begin() as session:
                admin(request, session)
                product = Product(**data.model_dump())
                session.add(product)
                session.flush()
                return {"id": product.id, **data.model_dump()}
        except IntegrityError:
            raise HTTPException(409, "SKU unavailable")

    @app.get("/api/admin/orders")
    def all_orders(request: Request, response: Response, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100)):
        with sessions() as session:
            admin(request, session)
            from sqlalchemy import func
            response.headers['X-Total-Count'] = str(session.scalar(select(func.count()).select_from(Order)))
            return [order_data(session, o) for o in session.scalars(select(Order).order_by(Order.id.desc()).offset(offset).limit(limit))]

    @app.patch("/api/admin/orders/{order_id}")
    def status(order_id: int, data: StatusInput, request: Request):
        try:
            with sessions.begin() as session:
                admin(request, session)
                return order_data(session, change_order_status(session, order_id, data.status))
        except CheckoutConflict:
            raise HTTPException(404, "Order not found")
        except ValidationError as error:
            raise HTTPException(409, str(error))

    def database_probe():
        from sqlalchemy import text
        with engine.connect() as connection:
            if connection.execute(text('SELECT version_num FROM alembic_version LIMIT 1')).first() is None:
                raise RuntimeError('Schema is not initialized')

    install_observability(app, database_probe)

    static = Path(__file__).resolve().parent.parent / "public"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="storefront")
    return app
