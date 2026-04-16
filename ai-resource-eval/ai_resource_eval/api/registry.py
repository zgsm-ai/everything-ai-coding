"""Generic Registry[T] — name-based instance registry.

Pattern borrowed from EleutherAI lm-evaluation-harness.  Used to register
metric implementations and judge providers by name so they can be looked up
at runtime.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """A minimal, generic name→instance registry.

    Type parameter *T* describes what kind of objects the registry holds
    (e.g. ``Registry[BaseMetric]`` or ``Registry[JudgeProvider]``).

    Examples
    --------
    >>> reg: Registry[int] = Registry()
    >>> reg.register("answer", 42)
    >>> reg.get("answer")
    42
    >>> reg.list_all()
    {'answer': 42}
    """

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, instance: T) -> None:
        """Register *instance* under *name*.

        Raises:
            ValueError: If *name* is already registered.
        """
        if name in self._items:
            raise ValueError(
                f"'{name}' is already registered in this registry"
            )
        self._items[name] = instance

    def get(self, name: str) -> T:
        """Return the instance registered under *name*.

        Raises:
            KeyError: If *name* has not been registered.
        """
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"'{name}' is not registered in this registry"
            ) from None

    def list_all(self) -> dict[str, T]:
        """Return a shallow copy of all registered name→instance pairs."""
        return dict(self._items)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __repr__(self) -> str:
        names = ", ".join(sorted(self._items))
        return f"Registry([{names}])"
