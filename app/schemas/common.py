from pydantic import BaseModel


class Page[T](BaseModel):
    """One page of a list endpoint."""

    items: list[T]
    total: int
    page: int
    limit: int
