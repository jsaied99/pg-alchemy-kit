from pg_alchemy_kit.PGUtils import PGUtils, get_engine, get_engine_url
from pg_alchemy_kit.PGUtilsORM import PGUtilsORM
from pg_alchemy_kit.PGUtilsBase import PGUtilsBase

from sqlalchemy.orm.session import Session
from sqlalchemy import inspect
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import DeclarativeMeta
import sqlalchemy
import logging
from contextlib import contextmanager
from typing import List, Iterator


class PG:
    def initialize(
        self,
        url: str = None,
        logger: logging.Logger = None,
        single_transaction: bool = False,
        pgUtils: PGUtilsBase = PGUtils,
        **kwargs,
    ):
        pg_utils_kwargs = kwargs.pop("pg_utils_kwargs", {})
        session_maker_kwargs = kwargs.pop("session_maker_kwargs", {})

        self.url = url or get_engine_url()
        self.engine: Engine = get_engine(self.url, **kwargs)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, **session_maker_kwargs
        )
        self.inspector = inspect(self.engine)
        self.logger = logger

        if self.logger is None:
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)
            logger.addHandler(logging.StreamHandler())
            self.logger = logger

        self.utils: PGUtilsBase = pgUtils(
            self.logger, single_transaction, **pg_utils_kwargs
        )

        self.logger.info("Initialized PG")

    def create_tables(
        self, Bases: List[DeclarativeMeta], schemas: List[str] = ["public"]
    ):
        """
        Creates tables for all the models in the list of Bases
        """
        if type(Bases) != list:
            Bases = [Bases]

        if type(schemas) != list:
            schemas = [schemas]

        with self.engine.begin() as conn:
            for Base, schema in zip(Bases, schemas):
                try:
                    if schema not in self.inspector.get_schema_names():
                        conn.execute(sqlalchemy.schema.CreateSchema(schema))
                    Base.metadata.create_all(self.engine)
                except Exception as e:
                    self.logger.info(f"Error in create_tables: {e}")

    @contextmanager
    def get_session_ctx(self) -> Iterator[Session]:
        with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
            finally:
                session.close()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

    def get_session(self) -> Iterator[Session]:
        with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
            finally:
                session.close()

    def get_transactional_session(self) -> Iterator[Session]:
        with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

    def get_session_scoped(self) -> scoped_session:
        return scoped_session(self.SessionLocal)

    def close(self):
        self.engine.dispose()


db = PG()
