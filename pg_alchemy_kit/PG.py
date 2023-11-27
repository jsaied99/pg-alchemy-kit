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

from sqlalchemy import orm


class PG:
    def initialize(
        cls,
        url: str = None,
        logger: logging.Logger = None,
        single_transaction: bool = False,
        pgUtils: PGUtilsBase = PGUtils,
        **kwargs,
    ):
        pg_utils_kwargs = kwargs.pop("pg_utils_kwargs", {})
        session_maker_kwargs = kwargs.pop("session_maker_kwargs", {})

        url = url or get_engine_url()
        cls.engine: Engine = get_engine(url, **kwargs)
        cls.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine, **session_maker_kwargs
        )
        cls.inspector = inspect(cls.engine)
        cls.logger = logger

        if cls.logger is None:
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)
            logger.addHandler(logging.StreamHandler())
            cls.logger = logger

        cls.utils = pgUtils(cls.logger, single_transaction, **pg_utils_kwargs)

        cls.logger.info("Initialized PG")

    def create_tables(
        cls, Bases: List[DeclarativeMeta], schemas: List[str] = ["public"]
    ):
        """
        Creates tables for all the models in the list of Bases
        """
        if type(Bases) != list:
            Bases = [Bases]

        if type(schemas) != list:
            schemas = [schemas]

        with cls.engine.begin() as conn:
            for Base, schema in zip(Bases, schemas):
                try:
                    if schema not in cls.inspector.get_schema_names():
                        conn.execute(sqlalchemy.schema.CreateSchema(schema))
                    Base.metadata.create_all(cls.engine)
                except Exception as e:
                    cls.logger.info(f"Error in create_tables: {e}")

    @contextmanager
    def get_session_ctx(cls) -> Iterator[Session]:
        with cls.SessionLocal() as session:
            try:
                cls.utils.initialize(session)
                yield session
            finally:
                session.close()

    @contextmanager
    def transaction(cls) -> Iterator[Session]:
        with cls.SessionLocal() as session:
            try:
                cls.utils.initialize(session)
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

    def get_session(cls) -> Iterator[Session]:
        with cls.SessionLocal() as session:
            try:
                cls.utils.initialize(session)
                yield session
            finally:
                session.close()

    def get_transactional_session(cls) -> Iterator[Session]:
        with cls.SessionLocal() as session:
            try:
                cls.utils.initialize(session)
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

    def get_session_scoped(cls) -> scoped_session:
        return scoped_session(cls.SessionLocal)

    def close(cls):
        cls.engine.dispose()


db = PG()
