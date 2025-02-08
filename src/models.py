from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Url(Base):
    __tablename__ = "urls"

    key: Mapped[str] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column()

    def __init__(self, key: str, target: str):
        super().__init__()
        self.key = key
        self.target = target
