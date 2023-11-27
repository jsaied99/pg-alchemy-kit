from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.session import Session
from sqlalchemy import create_engine, text, Select
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm.query import Query
from sqlalchemy.dialects import postgresql
from sqlalchemy import select

import logging
from typing import Any, List, Optional, Union
import uuid
import os
import warnings


def deprecated(func):
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"Call to deprecated function {func.__name__}. {func.__doc__}",
            category=DeprecationWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    return wrapper


class BaseModel:
    id: int

    def __init__(self):
        pass

    def table_name(self) -> str:
        return self.__tablename__

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class PGUtils:
    def __init__(
        cls, logger: logging.Logger, single_transaction: bool = False, **kwargs
    ):
        cls.session = None
        cls.logger = logger
        cls.single_transaction = single_transaction
        cls.snake_case = kwargs.get("snake_case", False)

    def initialize(cls, session: Session):
        cls.session = session

    @staticmethod
    def wrap_to_json(stmt: Union[str, text]) -> text:
        if type(stmt) == str:
            stmt = stmt.replace(";", "")

        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    def select(cls, session: Session, sql: str, **kwargs) -> Union[List[dict], None]:
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

    def select_orm(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[List[dict], None]:
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results = session.execute(stmt).scalars().all()
            if results is None:
                return []
            if convert_to_dict:
                return [record.to_dict() for record in results]

            return results

        except DBAPIError as e:
            raise e

    def select_orm_one(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[dict, None]:
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results: BaseModel = session.execute(stmt).scalars().one()
            if results is None:
                return {}
            if convert_to_dict:
                return results.to_dict()

            return results

        except DBAPIError as e:
            raise e

    def select_orm_one_strict(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        result: Optional[BaseModel] = session.execute(stmt).scalars().one()
        if result is None:
            raise Exception("No records found")
        return result

    def check_exists_orm(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        try:
            result: Optional[BaseModel] = session.execute(stmt).scalars().all()

            if result is None:
                return False
            return len(result) > 0

        except DBAPIError as e:
            raise e

    def insert(cls, session: Session, sql: str, params: dict) -> Union[bool, None]:
        try:
            stmt: text = text(sql)
            insert = session.execute(stmt, params=params)
            count = insert.rowcount
            cls.logger.info(f"Inserted {count} rows")

            if not cls.single_transaction:
                session.commit()
            else:
                session.flush()

            return count > 0
        except DBAPIError as e:
            raise e

    def delete(cls, session: Session, sql: str, params: dict) -> Union[bool, None]:
        try:
            stmt: text = text(sql)
            insert = session.execute(stmt, params=params)
            count = insert.rowcount
            cls.logger.info(f"Deleted {count} rows")
            if not cls.single_transaction:
                session.commit()

            return count > 0
        except DBAPIError as e:
            raise e

    def execute(cls, session: Session, sql: str) -> Union[bool, None]:
        try:
            stmt: text = text(sql)
            session.execute(stmt)

            return True
        except DBAPIError as e:
            raise e

    def execute_orm(cls, session: Session, stmt: Select) -> Union[bool, None]:
        try:
            return session.execute(stmt).fetchall()
        except DBAPIError as e:
            raise e

    def query(cls, query: Query) -> Union[bool, None]:
        try:
            return query.all()
        except DBAPIError as e:
            raise e

    # @deprecated
    def update(
        cls, session: Session, model: Any, key_value: dict, update_values: dict
    ) -> Union[bool, None]:
        """This method is deprecated. Use update() instead."""
        try:
            key = list(key_value.keys())[0]
            update_stmt = " , ".join([f"{k} = :{k}" for k in update_values.keys()])

            stmt = text(
                f"UPDATE {model().table_name()} SET {update_stmt} WHERE {key} = :{key}"
            )
            session.execute(stmt, {**key_value, **update_values})

            if not cls.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            cls.logger.info(f"Error in update: {e}")
            if not cls.single_transaction:
                session.rollback()
            raise e

    def update_orm(
        cls, session: Session, Model: BaseModel, filter_by: dict, values: dict, **kwargs
    ) -> BaseModel:
        try:
            obj = session.query(Model).filter_by(**filter_by).one()
            to_snake_case = kwargs.get("to_snake_case", cls.snake_case)

            if to_snake_case:
                values = cls.to_snake_case([values])[0]

            for key, value in values.items():
                setattr(obj, key, value)

            if not cls.single_transaction:
                session.commit()

            return obj

        except DBAPIError as e:
            cls.logger.info(f"Error in update: {e}")
            if not cls.single_transaction:
                session.rollback()
            raise e

    def bulk_update_orm(
        cls, session: Session, model: Any, records: List[dict]
    ) -> Union[bool, None]:
        try:
            session.bulk_update_mappings(model, records)
            if not cls.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            cls.logger.info(f"Error in bulk_update: {e}")
            if not cls.single_transaction:
                session.rollback()
            raise e

    def insert_orm(
        cls, session: Session, model, record: dict, **kwargs
    ) -> Union[object, None]:
        try:
            to_snake_case = kwargs.get("to_snake_case", cls.snake_case)

            if to_snake_case:
                record = cls.to_snake_case([record])[0]

            obj = model(**record)
            session.add(obj)
            if not cls.single_transaction:
                session.commit()
            else:
                session.flush()
            return obj
        except DBAPIError as e:
            cls.logger.info(f"Error in add_record_sync: {e}")
            session.rollback()
            return None

    def bulk_insert_orm(
        cls, session: Session, model: Any, records: List[dict], **kwargs
    ) -> List[dict]:
        try:
            records_to_insert: List[dict] = [model(**record) for record in records]

            session.add_all(records_to_insert)
            session.flush()  # Flush the records to obtain their IDs
            records: dict = [record.to_dict() for record in records_to_insert]

            if not cls.single_transaction:
                session.commit()

            return records
        except DBAPIError as e:
            cls.session.rollback()
            cls.logger.info(f"Error in add_records_sync: {e}")
            return []

    def insert_orm_on_conflict(
        cls,
        session: Session,
        model: Any,
        records: List[dict],
    ):
        for record in records:
            cls.insert_orm(session, model, record)

    def delete_orm(cls, session: Session, record: BaseModel) -> bool:
        try:
            session.delete(record)
            if not cls.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            if not cls.single_transaction:
                session.rollback()
            cls.logger.info(f"Error in remove_records_sync: {e}")
            return False

    def delete_orm_by_id(
        cls, session: Session, model: Any, record_id: Union[int, uuid.UUID]
    ) -> bool:
        try:
            stmt = select(model).where(model.id == record_id)
            record: BaseModel = cls.select_orm_one_strict(session, stmt)
            return cls.delete_orm(session, record)
        except DBAPIError as e:
            cls.logger.info(f"Error in remove_records_sync: {e}")
            return False

    def get_uuid(
        cls,
        session: Session,
        model: Any,
        key_value: dict,
    ) -> uuid.UUID:
        table_name = model().table_name()

        try:
            key = list(key_value.keys())[0]
            stmt = f"SELECT uuid FROM {table_name} WHERE {key} = :{key}"
            return cls.select(session, stmt, key_value)[0]["uuid"]
        except Exception as e:
            cls.logger.info(f"Error in get_uuid: {e}")
            return None

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

    def to_snake_case(cls, results: List[dict]) -> List[dict]:
        """
        Convert all keys in a list of dictionaries from camelCase to snake_case.

        Parameters:
        results (List[Dict[str, any]]): A list of dictionaries with camelCase keys.

        Returns:
        List[Dict[str, any]]: A list of dictionaries with keys in snake_case.
        """
        return [
            {cls.__to_snake_case(key): value for key, value in record.items()}
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

    def results_to_camel_case(cls, results: List[dict]) -> List[dict]:
        """
        Convert all keys in a list of dictionaries from snake_case to camelCase.

        Parameters:
        results (List[Dict[str, any]]): A list of dictionaries with snake_case keys.

        Returns:
        List[Dict[str, any]]: A list of dictionaries with keys in camelCase.
        """
        return [
            {cls.__to_camel_case(key): value for key, value in record.items()}
            for record in results
        ]

    def print_query(cls, query: Query) -> str:
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


def get_engine(url: str, **kwargs) -> Engine:
    try:
        pool_size = kwargs.get("pool_size", 5)
        max_overflow = kwargs.get("max_overflow", 0)
        pool_pre_ping = kwargs.get("pool_pre_ping", True)
        return create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            **kwargs,
        )
    except DBAPIError as e:
        raise e


def get_engine_url(
    connection_type: str = "postgresql", settings: Any = None, **kwargs
) -> str:
    if settings is not None:
        return f"{connection_type}://{settings.pg_username}:{settings.pg_password}@{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"

    username = kwargs.get("pg_username", os.environ.get("PG_USERNAME"))
    password = kwargs.get("pg_password", os.environ.get("PG_PASSWORD"))
    host = kwargs.get("pg_host", os.environ.get("PG_HOST"))
    port = kwargs.get("pg_port", os.environ.get("PG_PORT"))
    db = kwargs.get("pg_db", os.environ.get("PG_DB"))

    return f"{connection_type}://{username}:{password}@{host}:{port}/{db}"
