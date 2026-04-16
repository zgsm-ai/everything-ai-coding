"""Tests for ai_resource_eval.api.registry — Generic Registry[T]."""

from __future__ import annotations

import pytest

from ai_resource_eval.api.registry import Registry


# ===================================================================
# Registry[T]
# ===================================================================


class TestRegistry:
    """Tests for the generic Registry class."""

    def test_register_and_get(self):
        """register() stores an instance retrievable via get()."""
        reg: Registry[str] = Registry()
        reg.register("greeting", "hello")
        assert reg.get("greeting") == "hello"

    def test_get_not_found(self):
        """get() raises KeyError for an unregistered name."""
        reg: Registry[int] = Registry()
        with pytest.raises(KeyError, match="no_such_item"):
            reg.get("no_such_item")

    def test_register_duplicate_raises(self):
        """register() raises ValueError when the name is already registered."""
        reg: Registry[int] = Registry()
        reg.register("x", 1)
        with pytest.raises(ValueError, match="x"):
            reg.register("x", 2)

    def test_list_all_returns_copy(self):
        """list_all() returns a dict copy; mutating it doesn't affect the registry."""
        reg: Registry[str] = Registry()
        reg.register("a", "alpha")
        reg.register("b", "beta")

        snapshot = reg.list_all()
        assert snapshot == {"a": "alpha", "b": "beta"}

        # Mutating the returned dict must not affect the internal state.
        snapshot["c"] = "gamma"
        assert "c" not in reg.list_all()

    def test_list_all_empty(self):
        """list_all() returns an empty dict when nothing is registered."""
        reg: Registry[object] = Registry()
        assert reg.list_all() == {}

    def test_multiple_types(self):
        """Registry works with arbitrary types (duck-typing)."""

        class _Dummy:
            def __init__(self, v: int) -> None:
                self.v = v

        reg: Registry[_Dummy] = Registry()
        d1 = _Dummy(1)
        d2 = _Dummy(2)
        reg.register("one", d1)
        reg.register("two", d2)
        assert reg.get("one") is d1
        assert reg.get("two") is d2

    def test_register_preserves_order(self):
        """Registered items appear in insertion order via list_all()."""
        reg: Registry[int] = Registry()
        for i in range(5):
            reg.register(str(i), i)
        assert list(reg.list_all().keys()) == ["0", "1", "2", "3", "4"]
