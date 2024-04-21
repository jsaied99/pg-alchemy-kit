import uuid
from sqlalchemy import select, Select

from typing import Any, TypeVar, Generic, TypedDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import TextClause, text
import pandas as pd
from sqlalchemy.orm.query import Query
from sqlalchemy.dialects import postgresql


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
    single_transaction: bool
    snake_case: bool


class AsyncPGUtilsORM(Generic[T]):
    def __init__(self, single_transaction: bool = False, **kwargs):
        self.single_transaction = single_transaction
        self.snake_case = kwargs.get("snake_case", False)

    @staticmethod
    def __wrap_to_json(stmt: str | TextClause) -> TextClause:
        if type(stmt) == str:
            stmt = stmt.replace(";", "")

        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    async def raw_text_select(
        cls, session: AsyncSession, sql: str, **kwargs
    ) -> list[dict[str, Any]]:
        params = kwargs.get("params", {})
        to_camel_case = kwargs.get("to_camel_case", False)

        stmt: text = cls.__wrap_to_json(sql)
        results = await session.execute(stmt, params=params)
        results = results.fetchone()[0]
        if results is None:
            return []

        if to_camel_case:
            results = cls.__results_to_camel_case(results)

        return results

    async def raw_text_select_into_df(
        cls, session: AsyncSession, sql: str, **kwargs
    ) -> pd.DataFrame:
        params = kwargs.get("params", {})
        to_camel_case = kwargs.get("to_camel_case", False)

        stmt: text = cls.__wrap_to_json(sql)
        results = await session.execute(stmt, params=params)
        results = results.fetchone()[0]
        if results is None:
            return pd.DataFrame([])

        if to_camel_case:
            results = cls.__results_to_camel_case(results)

        return pd.DataFrame(results)

    def __init__(self, single_transaction: bool = False, **kwargs):
        self.single_transaction = single_transaction
        self.snake_case = kwargs.get("snake_case", False)

    async def __execute_all(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> list[T]:
        result = await session.execute(stmt)
        return result.scalars().all()

    async def select(self, session: AsyncSession, stmt: Select) -> list[T]:
        try:
            results: list[T] = await self.__execute_all(session, stmt)

            if results is None:
                return []
            return results

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one(self, session: AsyncSession, stmt: Select) -> T:
        try:
            results: list[T] = await self.__execute_all(session, stmt)

            if results is None or len(results) != 1:
                return {}

            result: T = results[0]
            return result

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one_strict(self, session: AsyncSession, stmt: Select) -> T:
        result = await session.execute(stmt)
        result: T | None = result.scalars().one()

        if result is None:
            raise PGNotExistsError("No records found")
        return result

    async def select_one_or_none(self, session: AsyncSession, stmt: Select) -> T:
        result = await session.execute(stmt)
        result: T | None = result.scalars().one_or_none()
        return result

    async def check_exists(self, session: AsyncSession, stmt: Select, **kwargs) -> bool:
        try:
            results: list[T] = await self.__execute_all(session, stmt)

            if results is None:
                return False
            return len(results) > 0

        except Exception as e:
            raise PGNotExistsError(str(e))

    async def execute(self, session: AsyncSession, stmt: Select) -> bool:
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
            await session.rollback()
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
            await session.rollback()
            raise PGInsertError(str(e))

    async def bulk_insert(
        self, session: AsyncSession, model: Any, records: list[dict], **kwargs
    ) -> bool:
        try:
            records_to_insert: list[dict] = [model(**record) for record in records]

            session.add_all(records_to_insert)
            await session.flush()  # Flush the records to obtain their IDs

            if not self.single_transaction:
                await session.commit()
            else:
                await session.flush()

            return True
        except Exception:
            await session.rollback()
            return False

    async def delete(self, session: AsyncSession, record: T) -> bool:
        try:
            await session.delete(record)
            if not self.single_transaction:
                await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            raise PGDeleteError(str(e))

    async def delete_by_id(
        self, session: AsyncSession, model: Any, record_id: int | uuid.UUID
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

    @staticmethod
    def __to_camel_case(snake_str: str) -> str:
        """
        Convert a snake_case string to camelCase.

        Parameters:
        snake_str (str): The snake_case string to convert.

        Returns:
        str: The string in camelCase.
        """
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])

    def __results_to_camel_case(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Convert all keys in a list of dictionaries from snake_case to camelCase.

        Parameters:
        results (List[Dict[str, any]]): A list of dictionaries with snake_case keys.

        Returns:
        List[Dict[str, any]]: A list of dictionaries with keys in camelCase.
        """
        return [
            {self.__to_camel_case(key): value for key, value in record.items()}
            for record in results
        ]

    def print_query(self, query: Query) -> str:
        """
        Print the query generated by a SQLAlchemy Query object.

        Parameters:
        query (Query): The SQLAlchemy Query object to print.

        Returns:
        str: The query generated by the Query object.
        """
        return str(
            query.statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
