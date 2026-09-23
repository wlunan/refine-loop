"""Shopping cart price calculation used by the RefineLoop demo."""


def calculate_total(items: list[tuple[float, int]], discount_percent: float = 0) -> float:
    """Return the cart total after applying a percentage discount."""
    subtotal = sum(price * quantity for price, quantity in items)
    return round(subtotal - discount_percent, 2)
