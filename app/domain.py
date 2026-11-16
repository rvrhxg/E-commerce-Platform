"""Price and order rules independent of HTTP and storage."""
from dataclasses import dataclass


class ValidationError(ValueError):
    pass


def integer(value: int, *, minimum: int, maximum: int) -> int:
    # bool is an int subclass but is never a valid monetary value or quantity.
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError("Integer outside supported range")
    return value


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    title: str
    unit_price_kopecks: int
    quantity: int

    def __post_init__(self):
        integer(self.product_id, minimum=1, maximum=2**63 - 1)
        integer(self.unit_price_kopecks, minimum=0, maximum=100_000_000)
        integer(self.quantity, minimum=1, maximum=99)
        if not self.title.strip():
            raise ValidationError("Product title required")

    @property
    def subtotal(self) -> int:
        return self.unit_price_kopecks * self.quantity


def order_total(lines: list[OrderLine]) -> int:
    if not lines or len(lines) > 100:
        raise ValidationError("Order must contain 1–100 unique products")
    if len({line.product_id for line in lines}) != len(lines):
        raise ValidationError("Duplicate product lines")
    return sum(line.subtotal for line in lines)


TRANSITIONS = {
    "placed": {"processing", "cancelled"},
    "processing": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def check_transition(current: str, target: str) -> None:
    if current not in TRANSITIONS or target not in TRANSITIONS:
        raise ValidationError("Unknown order status")
    if current != target and target not in TRANSITIONS[current]:
        raise ValidationError("Order status transition is not allowed")
