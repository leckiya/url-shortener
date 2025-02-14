from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Url(Base):
    __tablename__ = "urls"

    key: Mapped[str] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column()
    target: Mapped[str] = mapped_column()

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
