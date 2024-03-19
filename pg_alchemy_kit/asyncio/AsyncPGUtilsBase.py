from sqlalchemy.orm.query import Query
from sqlalchemy.dialects import postgresql
from sqlalchemy import Select, text
from sqlalchemy.exc import DBAPIError
import uuid
from typing import Any, List, Optional, Union
from abc import ABC, abstractmethod
import pandas as pd

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine


class BaseModel:
    id: int

    def __init__(self):
        pass

    def table_name(self) -> str:
        return self.__tablename__

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class AsyncPGUtilsBase(ABC):
    def __init__(self, single_transaction: bool = False, **kwargs):
        self.single_transaction = single_transaction
        self.snake_case = kwargs.get("snake_case", False)

    @staticmethod
    def __wrap_to_json(stmt: Union[str, text]) -> text:
        if type(stmt) == str:
            stmt = stmt.replace(";", "")

        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    async def raw_text_select_into_df(
        cls, session: AsyncSession, sql: str, **kwargs
    ) -> Union[pd.DataFrame, Exception]:
        try:
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
        except DBAPIError as e:
            raise e

    async def raw_text_select(
        cls, session: AsyncSession, sql: str, **kwargs
    ) -> Union[List[dict], None]:
        try:
            params = kwargs.get("params", {})
            to_camel_case = kwargs.get("to_camel_case", False)

            stmt: text = cls.__wrap_to_json(sql)
            results = await session.execute(stmt, params=params)
            results = results.fetchone()[0]
            # results = await session.execute(stmt, params=params).fetchone()[0]
            if results is None:
                return []

            if to_camel_case:
                results = cls.__results_to_camel_case(results)

            return results
        except DBAPIError as e:
            raise e

    @abstractmethod
    async def select(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[List[dict], None]:
        pass

    @abstractmethod
    async def select_one(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[dict, None]:
        pass

    @abstractmethod
    async def select_one_strict(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        pass

    @abstractmethod
    async def select_one_or_none(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[BaseModel, None]:
        pass

    @abstractmethod
    async def check_exists(
        self, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        pass

    @abstractmethod
    async def execute(self, session: AsyncSession, stmt: Select) -> Union[bool, None]:
        pass

    @abstractmethod
    async def update(
        self,
        session: AsyncSession,
        Model: BaseModel,
        filter_by: dict,
        values: dict,
        **kwargs,
    ) -> BaseModel:
        pass

    @abstractmethod
    async def insert(
        self, session: AsyncSession, model, record: dict, **kwargs
    ) -> Union[object, None]:
        pass

    @abstractmethod
    async def bulk_insert(
        cls, session: AsyncSession, model: Any, records: List[dict], **kwargs
    ) -> List[dict]:
        pass

    @abstractmethod
    async def delete(self, session: AsyncSession, record: BaseModel) -> bool:
        pass

    @abstractmethod
    async def delete_by_id(
        self, session: AsyncSession, model: Any, record_id: Union[int, uuid.UUID]
    ) -> bool:
        pass

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

    def to_snake_case(self, results: List[dict]) -> List[dict]:
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

    def __results_to_camel_case(self, results: List[dict]) -> List[dict]:
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
