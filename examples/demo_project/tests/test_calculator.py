from calculator import add, multiply


def test_adds_positive_numbers():
    assert add(2, 3) == 5


def test_adds_negative_numbers():
    assert add(-4, -6) == -10


def test_multiplies_numbers():
    assert multiply(4, 5) == 20

