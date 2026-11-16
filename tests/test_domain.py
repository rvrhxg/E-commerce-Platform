import unittest
from app.domain import OrderLine, ValidationError, check_transition, order_total


class OrderRulesTests(unittest.TestCase):
    def test_money_stays_exact_and_snapshot_is_immutable(self):
        line = OrderLine(1, "Керамическая чашка", 129950, 3)
        self.assertEqual(order_total([line]), 389850)
        with self.assertRaises(AttributeError):
            line.unit_price_kopecks = 1

    def test_rejects_float_boolean_negative_and_duplicate_inputs(self):
        for value in [True, 1.5, -1, 100_000_001]:
            with self.assertRaises(ValidationError):
                OrderLine(1, "Cup", value, 1)
        line = OrderLine(1, "Cup", 100, 1)
        with self.assertRaises(ValidationError):
            order_total([line, line])
        with self.assertRaises(ValidationError):
            order_total([])

    def test_shipping_and_cancellation_follow_order_lifecycle(self):
        check_transition("placed", "processing")
        check_transition("processing", "cancelled")
        check_transition("delivered", "delivered")
        for current, target in [("placed", "delivered"), ("shipped", "cancelled"), ("cancelled", "processing")]:
            with self.assertRaises(ValidationError):
                check_transition(current, target)
