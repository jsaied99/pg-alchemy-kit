from pg_alchemy_kit.PGUtils import PGUtils, get_engine_url
from .AsyncPGUtilsORM import AsyncPGUtilsORM
from .AsyncPGUtilsBase import AsyncPGUtilsBase

from sqlalchemy.orm.session import Session
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import DeclarativeMeta
import sqlalchemy
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, List, Iterator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy import text


def get_async_engine(url, **kwargs):
    pool_size = kwargs.get("pool_size", 5)
    max_overflow = kwargs.get("max_overflow", 0)
    pool_pre_ping = kwargs.get("pool_pre_ping", True)
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        **kwargs,
    )


class AsyncPG:
    def initialize(
        self,
        url: str = None,
        logger: logging.Logger = None,
        single_transaction: bool = False,
        pgUtils: AsyncPGUtilsBase = PGUtils,
        **kwargs,
    ):
        pg_utils_kwargs = kwargs.pop("pg_utils_kwargs", {})
        session_maker_kwargs = kwargs.pop("session_maker_kwargs", {})
        async_engine_kwargs = kwargs.pop("async_engine_kwargs", {})

        self.url = url or get_engine_url(connection_type="postgresql+asyncpg")
        self.engine: AsyncEngine = get_async_engine(self.url, **async_engine_kwargs)
        self.SessionLocal = sessionmaker(
            self.engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
            **session_maker_kwargs,
        )
        self.logger = logger

        if self.logger is None:
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)
            logger.addHandler(logging.StreamHandler())
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            for handler in logger.handlers:
                handler.setFormatter(formatter)

            self.logger = logger

        self.utils: AsyncPGUtilsBase = pgUtils(
            self.logger, single_transaction, **pg_utils_kwargs
        )

        self.logger.info(f"Initialized {self.__class__.__name__}")

    async def create_tables(
        self, Bases: List[DeclarativeMeta], schemas: List[str] = ["public"]
    ):
        """
        Creates tables for all the models in the list of Bases
        """
        if type(Bases) != list:
            Bases = [Bases]

        if type(schemas) != list:
            schemas = [schemas]

        async with self.engine.begin() as conn:
            for Base, schema in zip(Bases, schemas):
                try:
                    if schema not in self.inspector.get_schema_names():
                        await conn.execute(sqlalchemy.schema.CreateSchema(schema))
                    await conn.run_sync(Base.metadata.create_all)
                except Exception as e:
                    self.logger.info(f"Error in create_tables: {e}")

    @asynccontextmanager
    async def get_session_ctx(self) -> AsyncGenerator[Session, None]:
        async with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
            finally:
                await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Session, None]:
        async with self.SessionLocal() as session:
            try:
                self.utils.initialize(session)
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            finally:
                await session.close()

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

    async def close(self):
        await self.engine.dispose()


db = AsyncPG()


async def main():
    db.initialize(url="postgresql+asyncpg://postgres:postgres@localhost:25060/postgres")

    # async with db.get_session_ctx() as session:
    async with db.transaction() as session:
        async with session.begin():
            # result = await session.execute(text("SELECT * FROM test_table"))
            # result = result.mappings().all()
            # print(result)

            # insert to test_table
            #             CREATE TABLE test_table (
            #     id SERIAL PRIMARY KEY,
            #     name character varying,
            #     age integer,
            #     country_id integer NOT NULL REFERENCES country_table(id),
            #     created_at timestamp without time zone
            # );
            await session.execute(
                text(
                    "INSERT INTO test_table (name, age, country_id, created_at) VALUES ('test', 1, 1, NOW())"
                )
            )

    await db.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
