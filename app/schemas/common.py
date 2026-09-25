from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, StringConstraints


class Page[T](BaseModel):
    """One page of a list endpoint."""

    items: list[T]
    total: int
    page: int
    limit: int


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def optional_text(max_length: int) -> Any:
    """Optional trimmed text; blank strings become None."""
    return Annotated[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None,
        BeforeValidator(_blank_to_none),
    ]
