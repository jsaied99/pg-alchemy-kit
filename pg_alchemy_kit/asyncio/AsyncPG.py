from pg_alchemy_kit.PGUtils import PGUtils, get_engine_url
from .AsyncPGUtilsORM import AsyncPGUtilsORM
from .AsyncPGUtilsBase import AsyncPGUtilsBase

from sqlalchemy.orm.session import Session
from sqlalchemy.orm import DeclarativeMeta
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
    async_scoped_session,
)
from asyncio import current_task
from sqlalchemy.pool import NullPool


def get_async_engine(url, **kwargs):

    pool_pre_ping = kwargs.pop("pool_pre_ping", True)
    echo = kwargs.pop("echo", True)
    if kwargs.get("poolclass") == NullPool:
        return create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=pool_pre_ping,
            **kwargs,
        )

    pool_size = kwargs.pop("pool_size", 5)
    max_overflow = kwargs.pop("max_overflow", 0)
    return create_async_engine(
        url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        **kwargs,
    )


class AsyncPG:

    def initialize(
        self,
        url: str = None,
        single_transaction: bool = False,
        pgUtils: AsyncPGUtilsORM = AsyncPGUtilsORM,
        **kwargs,
    ):
        async_pg_utils_kwargs: dict = kwargs.pop("async_pg_utils_kwargs", {})
        async_session_maker_kwargs: dict = kwargs.pop("async_session_maker_kwargs", {})
        async_engine_kwargs: dict = kwargs.pop("async_engine_kwargs", {})

        self.url = url or get_engine_url(connection_type="postgresql+asyncpg")
        self.engine: AsyncEngine = get_async_engine(self.url, **async_engine_kwargs)

        autoflush = async_session_maker_kwargs.pop("autoflush", False)
        expire_on_commit = async_session_maker_kwargs.pop("expire_on_commit", False)

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=autoflush,
            expire_on_commit=expire_on_commit,
            **async_session_maker_kwargs,
        )

        self.Session = async_scoped_session(
            self.session_factory, scopefunc=current_task
        )

        self.utils: AsyncPGUtilsORM = pgUtils(
            single_transaction, **async_pg_utils_kwargs
        )

    async def create_tables(self, Bases: List[DeclarativeMeta]):
        """
        Creates tables for all the models in the list of Bases
        """
        if type(Bases) != list:
            Bases = [Bases]

        async with self.engine.begin() as conn:
            for Base in Bases:
                await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session_ctx(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.Session() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Session, None]:
        async with self.Session() as session:
            async with session.begin():
                yield session

    async def close(self):
        await self.engine.dispose()


db = AsyncPG()
