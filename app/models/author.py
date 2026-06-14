from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPkMixin

if TYPE_CHECKING:
    from app.models.book import Book


class Author(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (
        UniqueConstraint(
            "normalized_first_name",
            "normalized_last_name",
            name="uq_authors_normalized_first_last",
        ),
    )

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_first_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_last_name: Mapped[str] = mapped_column(Text, nullable=False)

    books: Mapped[list[Book]] = relationship(back_populates="author", passive_deletes=True)
