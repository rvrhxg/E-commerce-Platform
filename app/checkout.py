import hashlib
import json
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from .domain import OrderLine, ValidationError, integer, order_total, check_transition
from .models import Order, OrderItem, Product, Cart, CartItem


class CheckoutConflict(ValueError):
    pass


def checkout(session: Session, user_id: int, items: list[dict], address: str, key: str, cart_revision: int | None = None) -> Order:
    """Caller owns transaction; any failure must roll back stock and order together."""
    if not isinstance(address, str) or not 5 <= len(address.strip()) <= 500:
        raise ValidationError("Delivery address required")
    if not isinstance(key, str) or not 8 <= len(key) <= 80:
        raise ValidationError("Idempotency key must contain 8–80 characters")
    if not items or len(items) > 100:
        raise ValidationError("Order must contain 1–100 products")
    normalized = sorted((integer(i["product_id"], minimum=1, maximum=2**31-1), integer(i["quantity"], minimum=1, maximum=99)) for i in items)
    if len({p for p, _ in normalized}) != len(normalized):
        raise ValidationError("Duplicate products")
    digest = hashlib.sha256(json.dumps([normalized, address.strip()], ensure_ascii=False).encode()).hexdigest()
    previous = session.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))
    if previous:
        if previous.request_hash != digest:
            raise CheckoutConflict("Idempotency key already used with different contents")
        return previous
    # Serialize cart edits before product locks; replay above never touches a new cart.
    cart = session.scalar(select(Cart).where(Cart.user_id == user_id).with_for_update()) if cart_revision is not None else None
    claimed_cart = None
    if cart:
        changed = session.execute(update(Cart).where(Cart.id == cart.id, Cart.revision == cart_revision).values(revision=Cart.revision + 1))
        if changed.rowcount == 1:
            claimed_cart = cart.id
    lines = []
    for product_id, quantity in normalized:
        product = session.scalar(select(Product).where(Product.id == product_id, Product.active.is_(True)).with_for_update())
        if not product:
            raise CheckoutConflict("Product unavailable")
        changed = session.execute(update(Product).where(Product.id == product_id, Product.stock >= quantity).values(stock=Product.stock-quantity))
        if changed.rowcount != 1:
            raise CheckoutConflict("Not enough stock")
        lines.append(OrderLine(product.id, product.title, product.price_kopecks, quantity))
    order = Order(user_id=user_id, idempotency_key=key, request_hash=digest, total_kopecks=order_total(lines), delivery_address=address.strip())
    session.add(order)
    session.flush()
    session.add_all(OrderItem(order_id=order.id, product_id=line.product_id, title=line.title, unit_price_kopecks=line.unit_price_kopecks, quantity=line.quantity) for line in lines)
    session.flush()
    if claimed_cart is not None:
        for product_id, quantity in normalized:
            session.execute(delete(CartItem).where(CartItem.cart_id == claimed_cart, CartItem.product_id == product_id, CartItem.quantity == quantity))
    return order


def change_order_status(session: Session, order_id: int, target: str) -> Order:
    order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise CheckoutConflict("Order not found")
    check_transition(order.status, target)
    if order.status == target:
        return order
    if target == "cancelled":
        for item in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.product_id)):
            session.execute(update(Product).where(Product.id == item.product_id).values(stock=Product.stock+item.quantity))
    order.status = target
    session.flush()
    return order
