from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(64), default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    group_name: Mapped[str] = mapped_column(String(255), default="")
    source_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stream.position",
    )


class Stream(Base):
    __tablename__ = "streams"
    __table_args__ = (UniqueConstraint("campaign_id", "keitaro_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    keitaro_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    stream_type: Mapped[str] = mapped_column(String(32), default="regular")
    position: Mapped[int] = mapped_column(Integer, default=0)
    accepts_offers: Mapped[bool] = mapped_column(Boolean, default=False)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.position",
    )

    @property
    def dirty(self) -> bool:
        return any(offer.dirty for offer in self.offers)


class StreamOffer(Base):
    """Draft row for an offer inside a stream.

    published_* is the last state confirmed with Keitaro.
    published_status is NULL until the row has been synced at least once.
    """

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"))
    offer_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    position: Mapped[int] = mapped_column(Integer, default=0)
    published_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    published_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_pinned_share: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def dirty(self) -> bool:
        if self.published_status is None:
            return True
        return self.status != self.published_status or self.share != self.published_share

    def mark_published(self) -> None:
        self.published_status = self.status
        self.published_share = self.share
        self.published_pinned = self.pinned
        self.published_pinned_share = self.pinned_share

    def restore_published(self) -> None:
        self.status = self.published_status or "removed"
        self.share = self.published_share or 0
        self.pinned = self.published_pinned
        self.pinned_share = self.published_pinned_share
