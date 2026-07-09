"""Tests for the SDSModel base class."""

import uuid

from spectrumx.models.base import SDSModel


def test_repr_includes_class_name_and_uuid() -> None:
    """SDSModel.__repr__() returns ``<ClassName uuid=…>`` when uuid is set."""

    class MyModel(SDSModel):
        pass

    uid = uuid.uuid4()
    instance = MyModel(uuid=uid)
    # __repr_name__ feeds the class-name component of repr — pin it here so the
    # method stays covered (repr itself inlines __class__.__name__).
    assert instance.__repr_name__() == "MyModel"
    assert instance.__repr__() == f"<MyModel uuid={uid}>"


def test_repr_shows_none_when_uuid_unset() -> None:
    """SDSModel.__repr__() returns ``<ClassName uuid=None>`` when uuid is unset."""

    class MyModel(SDSModel):
        pass

    instance = MyModel()
    assert instance.__repr__() == "<MyModel uuid=None>"
