import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models import Base, Url


class TestUrlTable(unittest.TestCase):
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()

    def setUp(self) -> None:
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)

    def test_id_must_be_unique(self):
        url = Url("1", "https://google.com")
        self.session.add_all([url])
        self.session.commit()

        url = Url("1", "https://google.com")
        self.session.add_all([url])
        with self.assertRaises(IntegrityError):
            self.session.commit()
