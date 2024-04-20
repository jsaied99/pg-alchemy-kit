from .AsyncPGUtilsORM import AsyncPGUtilsORM
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
    async_scoped_session,
)
from asyncio import current_task

from typing import Any, TypedDict
from typing_extensions import Unpack, NotRequired


class InitParams(TypedDict):
    async_engine_kwargs: NotRequired[dict[str, Any]]
    async_pg_utils_kwargs: NotRequired[dict[str, Any]]
    async_session_maker_kwargs: NotRequired[dict[str, Any]]
    echo: NotRequired[bool]
    pool_size: NotRequired[int]
    max_overflow: NotRequired[int]


class AsyncPG:

    def initialize(
        self,
        url: str,
        single_transaction: bool = False,
        **kwargs: Unpack[InitParams],
    ):
        async_pg_utils_kwargs: dict[str, Any] = kwargs.pop("async_pg_utils_kwargs", {})
        async_session_maker_kwargs: dict[str, Any] = kwargs.pop(
            "async_session_maker_kwargs", {}
        )
        async_engine_kwargs: dict[str, Any] = kwargs.pop("async_engine_kwargs", {})

        self.url: str = url
        self.engine: AsyncEngine = create_async_engine(self.url, **async_engine_kwargs)

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

        self.utils: AsyncPGUtilsORM = AsyncPGUtilsORM(
            single_transaction, **async_pg_utils_kwargs
        )

    @asynccontextmanager
    async def get_session_ctx(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.Session() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.Session() as session:
            async with session.begin():
                yield session

    async def close(self):
        await self.engine.dispose()


db = AsyncPG()
