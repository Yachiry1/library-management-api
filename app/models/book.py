from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPkMixin

if TYPE_CHECKING:
    from app.models.author import Author


class Book(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(
            "publication_year IS NULL OR publication_year > 0", name="publication_year_positive"
        ),
        Index("ix_books_author_id", "author_id"),
        Index("ix_books_publication_year", "publication_year"),
        Index("ix_books_normalized_title", "normalized_title"),
        Index("ix_books_created_at", "created_at"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    isbn: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    author_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("authors.id", ondelete="RESTRICT", name="fk_books_author_id_authors"),
        nullable=False,
    )

    author: Mapped[Author] = relationship(back_populates="books", lazy="joined")
