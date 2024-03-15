from sqlalchemy.orm.session import Session
from sqlalchemy.orm.query import Query
from sqlalchemy.dialects import postgresql
from sqlalchemy import Select, text
from sqlalchemy.exc import DBAPIError
import uuid
from typing import Any, List, Optional, Union
from abc import ABC, abstractmethod
import pandas as pd


class BaseModel:
    id: int

    def __init__(self):
        pass

    def table_name(self) -> str:
        return self.__tablename__

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PGUtilsBase(ABC):
    def __init__(self, single_transaction: bool = False, **kwargs):
        self.session = None
        self.single_transaction = single_transaction
        self.snake_case = kwargs.get("snake_case", False)

    def initialize(self, session: Session):
        self.session = session

    @staticmethod
    def wrap_to_json(stmt: Union[str, text]) -> text:
        if type(stmt) == str:
            stmt = stmt.replace(";", "")

        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    def raw_text_select_into_df(
        cls, session: Session, sql: str, **kwargs
    ) -> Union[pd.DataFrame, Exception]:
        try:
            params = kwargs.get("params", {})
            to_camel_case = kwargs.get("to_camel_case", False)

            stmt: text = cls.wrap_to_json(sql)
            results = session.execute(stmt, params=params).fetchone()[0]
            if results is None:
                return pd.DataFrame([])

            if to_camel_case:
                results = cls.results_to_camel_case(results)

            return pd.DataFrame(results)
        except DBAPIError as e:
            raise e

    def raw_text_select(
        cls, session: Session, sql: str, **kwargs
    ) -> Union[List[dict], None]:
        try:
            params = kwargs.get("params", {})
            to_camel_case = kwargs.get("to_camel_case", False)

            stmt: text = cls.wrap_to_json(sql)
            results = session.execute(stmt, params=params).fetchone()[0]
            if results is None:
                return []

            if to_camel_case:
                results = cls.results_to_camel_case(results)

            return results
        except DBAPIError as e:
            raise e

    @abstractmethod
    def select(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[List[dict], None]:
        pass

    @abstractmethod
    def select_one(self, session: Session, stmt: Select, **kwargs) -> Union[dict, None]:
        pass

    @abstractmethod
    def select_one_strict(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        pass

    @abstractmethod
    def check_exists(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        pass

    @abstractmethod
    def execute(self, session: Session, stmt: Select) -> Union[bool, None]:
        pass

    @abstractmethod
    def update(
        self,
        session: Session,
        Model: BaseModel,
        filter_by: dict,
        values: dict,
        **kwargs,
    ) -> BaseModel:
        pass

    @abstractmethod
    def bulk_update(
        self, session: Session, model: Any, records: List[dict]
    ) -> Union[bool, None]:
        pass

    @abstractmethod
    def insert(
        self, session: Session, model, record: dict, **kwargs
    ) -> Union[object, None]:
        pass

    @abstractmethod
    def bulk_insert(
        self, session: Session, model: Any, records: List[dict], **kwargs
    ) -> List[dict]:
        pass

    @abstractmethod
    def insert_on_conflict(self, session: Session, model: Any, records: List[dict]):
        pass

    @abstractmethod
    def delete(self, session: Session, record: BaseModel) -> bool:
        pass

    @abstractmethod
    def delete_by_id(
        self, session: Session, model: Any, record_id: Union[int, uuid.UUID]
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

    def results_to_camel_case(self, results: List[dict]) -> List[dict]:
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
