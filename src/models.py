from typing import List

from sqlalchemy import ForeignKey, Sequence, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Url(Base):
    __tablename__ = "urls"

    key: Mapped[str] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column()
    target: Mapped[str] = mapped_column()

    url_redirect_usages: Mapped[List["UrlRedirectUsage"]] = relationship(
        back_populates="url"
    )

    def __init__(self, owner: str, key: str, target: str):
        super().__init__()
        self.owner = owner
        self.key = key
        self.target = target

    def __repr__(self) -> str:
        return f"Url({self.owner} | {self.key} => {self.target})"

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value, Url):
            return False

        return (
            self.key == value.key and self.key == value.key and self.owner == self.owner
        )


class UrlRedirectUsage(Base):
    __tablename__ = "url_redirect_usages"

    id: Mapped[int] = mapped_column(
        Sequence("url_redirect_usages_id_seq"), primary_key=True
    )
    url_key: Mapped[str] = mapped_column(ForeignKey("urls.key"))
    country: Mapped[str] = mapped_column(server_default="unknown")
    count: Mapped[int] = mapped_column(server_default="1")

    url: Mapped["Url"] = relationship(back_populates="url_redirect_usages")

    __table_args__ = (
        UniqueConstraint(
            "url_key", "country", name="url_redirect_usages_key_country_unique"
        ),
    )


class Webhook(Base):
    __tablename__ = "webhooks"

    user: Mapped[str] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column()
