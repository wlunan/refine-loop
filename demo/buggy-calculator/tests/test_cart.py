import pytest

from src.cart import calculate_total


def test_calculates_total_without_discount():
    assert calculate_total([(12.5, 2), (5.0, 1)]) == 30.0


def test_applies_percentage_discount():
    assert calculate_total([(100.0, 1), (50.0, 1)], discount_percent=10) == 135.0


def test_empty_cart_is_zero():
    assert calculate_total([]) == 0.0


@pytest.mark.parametrize("discount", [-1, 101])
def test_rejects_invalid_discount(discount):
    with pytest.raises(ValueError, match="discount_percent"):
        calculate_total([(10.0, 1)], discount_percent=discount)


def test_rejects_non_positive_quantity():
    with pytest.raises(ValueError, match="quantity"):
        calculate_total([(10.0, 0)])
