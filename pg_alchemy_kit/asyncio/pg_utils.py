from sqlalchemy import select, Select

from typing import Any, TypeVar, Generic, TypedDict, Unpack, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import TextClause, text
import pandas as pd
from collections.abc import Sequence


class PGBaseError(Exception):
    pass


class PGSelectError(PGBaseError):
    pass


class PGNotExistsError(PGBaseError):
    pass


class PGInsertError(PGBaseError):
    pass


class PGUpdateError(PGBaseError):
    pass


class PGDeleteError(PGBaseError):
    pass


T = TypeVar("T")


class PGUtilsParams(TypedDict):
    snake_case: bool
    single_transaction: bool


class RawTextSelectParams(TypedDict):
    params: dict[str, Any]


class AsyncPGUtilsORM(Generic[T]):
    def __init__(self, **kwargs: Unpack[PGUtilsParams]):
        super().__init__()
        self.single_transaction = kwargs.get("single_transaction", True)
        self.snake_case = kwargs.get("snake_case", False)

    @staticmethod
    def __wrap_to_json(stmt: str | TextClause) -> TextClause:
        if isinstance(stmt, str):
            stmt = stmt.replace(";", "")

        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    async def raw_text_select(
        self,
        session: AsyncSession,
        sql: str | TextClause,
        **kwargs: Unpack[RawTextSelectParams],
    ) -> list[dict[str, Any]]:
        params = kwargs.get("params", {})

        stmt: TextClause = self.__wrap_to_json(sql)
        wrapped_results = await session.execute(stmt, params=params)
        results = wrapped_results.fetchone()

        if results is None:
            return []

        return results[0]

    async def raw_text_select_into_df(
        self, session: AsyncSession, sql: str, **kwargs: Unpack[RawTextSelectParams]
    ) -> pd.DataFrame:
        records = await self.raw_text_select(session, sql, **kwargs)
        return pd.DataFrame(records)

    async def __execute_all(
        self,
        session: AsyncSession,
        stmt: Select[tuple[T]],
    ) -> Sequence[T]:
        result = await session.execute(stmt)
        return result.scalars().all()

    async def select(self, session: AsyncSession, stmt: Select[tuple[T]]) -> list[T]:
        try:
            results: Sequence[T] = await self.__execute_all(session, stmt)
            return cast(list[T], results)

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one(
        self, session: AsyncSession, stmt: Select[tuple[T]]
    ) -> T | None:
        try:
            results: Sequence[T] = await self.__execute_all(session, stmt)

            if len(results) != 1:
                return None

            result: T = results[0]
            return result

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one_strict(
        self, session: AsyncSession, stmt: Select[tuple[T]]
    ) -> T:
        result = await session.execute(stmt)
        result_one: T | None = result.scalars().one_or_none()

        if result_one is None:
            raise PGNotExistsError("No records found")
        return result_one

    async def select_one_or_none(
        self, session: AsyncSession, stmt: Select[tuple[T]]
    ) -> T | None:
        result = await session.execute(stmt)
        result_one: T | None = result.scalars().one_or_none()
        return result_one

    async def check_exists(self, session: AsyncSession, stmt: Select[tuple[T]]) -> bool:
        try:
            results: Sequence[T] = await self.__execute_all(session, stmt)
            return len(results) > 0

        except Exception as e:
            raise PGNotExistsError(str(e))

    async def execute(
        self, session: AsyncSession, stmt: Select[tuple[Any]]
    ) -> Sequence[Any]:
        try:
            tmp = await session.execute(stmt)
            return tmp.fetchall()
        except Exception as e:
            raise PGSelectError(str(e))

    async def update(
        self,
        session: AsyncSession,
        Model: Any,
        filter_by: dict[str, Any],
        values: dict[str, Any],
    ) -> T:
        try:
            obj = await self.select_one_strict(
                session, select(Model).filter_by(**filter_by)
            )

            if self.snake_case:
                values = self.to_snake_case([values])[0]

            for key, value in values.items():
                setattr(obj, key, value)

            if not self.single_transaction:
                await session.commit()
            else:
                await session.flush()

            return obj

        except Exception as e:
            raise PGUpdateError(str(e))

    async def insert(
        self, session: AsyncSession, model: Any, record: dict[str, Any]
    ) -> T:
        try:
            if self.snake_case:
                record = self.to_snake_case([record])[0]

            obj = model(**record)
            session.add(obj)
            if not self.single_transaction:
                await session.commit()
            else:
                await session.flush()
            return obj
        except Exception as e:
            raise PGInsertError(str(e))

    async def insert_dto(self, session: AsyncSession, model: T) -> T:
        try:
            session.add(model)
            if not self.single_transaction:
                await session.commit()
            else:
                await session.flush()
            return model
        except Exception as e:
            raise PGInsertError(str(e))

    async def bulk_insert(
        self, session: AsyncSession, model: Any, records: list[dict[str, Any]]
    ) -> bool:
        try:
            records_to_insert: list[dict[str, Any]] = [
                model(**record) for record in records
            ]

            session.add_all(records_to_insert)
            await session.flush()  # Flush the records to obtain their IDs

            if not self.single_transaction:
                await session.commit()
            else:
                await session.flush()

            return True
        except Exception:
            return False

    async def delete(self, session: AsyncSession, record: T) -> bool:
        try:
            await session.delete(record)
            if not self.single_transaction:
                await session.commit()
            return True
        except Exception as e:
            raise PGDeleteError(str(e))

    async def delete_by_id(
        self, session: AsyncSession, model: Any, record_id: Any
    ) -> bool:
        try:
            stmt = select(model).where(model.id == record_id)
            record: T = await self.select_one_strict(session, stmt)
            return await self.delete(session, record)
        except Exception as e:
            raise PGDeleteError(str(e))

    @staticmethod
    def __to_snake_case(camel_str: str) -> str:
        """
        Convert a camelCase string to snake_case.

        Parameters:
        camel_str (str): The camelCase string to convert.

        Returns:
        str: The string in snake_case.
        """
        snake_str = camel_str[0].lower()
        for char in camel_str[1:]:
            if char.isupper():
                snake_str += "_"
            snake_str += char.lower()
        return snake_str

    def to_snake_case(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert all keys in a list of dictionaries from camelCase to snake_case.

        Parameters:
        results (List[Dict[str, any]]): A list of dictionaries with camelCase keys.

        Returns:
        List[Dict[str, any]]: A list of dictionaries with keys in snake_case.
        """
        return [
            {self.__to_snake_case(key): value for key, value in record.items()}
            for record in results
        ]
