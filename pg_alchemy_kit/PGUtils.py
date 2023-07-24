from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.engine.base import Engine
import logging
from typing import Any, List, Union
import uuid
import os


class PGUtils:
    def __init__(cls, logger: logging.Logger):
        cls.session = None
        cls.logger = logger

    def initialize(cls, session: Session):
        cls.session = session

    @staticmethod
    def wrap_to_json(stmt: str) -> text:
        stmt = stmt.replace(";", "")
        return text(f"SELECT json_agg(t) FROM ({stmt}) t")

    def select(
        cls, session: Session, sql: str, params: dict = {}
    ) -> Union[List[dict], None]:
        try:
            stmt: text = cls.wrap_to_json(sql)
            results = session.execute(stmt, params=params).fetchone()[0]
            if results is None:
                return []

            return results
        except DBAPIError as e:
            raise e

    def insert(cls, session: Session, sql: str, params: dict) -> Union[bool, None]:
        try:
            stmt: text = text(sql)
            insert = session.execute(stmt, params=params)
            count = insert.rowcount
            cls.logger.info(f"Inserted {count} rows")
            session.commit()

            return count > 0
        except DBAPIError as e:
            raise e

    def delete(cls, session: Session, sql: str, params: dict) -> Union[bool, None]:
        try:
            stmt: text = text(sql)
            insert = session.execute(stmt, params=params)
            count = insert.rowcount
            cls.logger.info(f"Deleted {count} rows")
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

    def update(
        cls, session: Session, model: Any, key_value: dict, update_values: dict
    ) -> Union[bool, None]:
        try:
            key = list(key_value.keys())[0]
            update_stmt = " , ".join([f"{k} = :{k}" for k in update_values.keys()])

            stmt = text(
                f"UPDATE {model().table_name()} SET {update_stmt} WHERE {key} = :{key}"
            )
            session.execute(stmt, {**key_value, **update_values})
            session.commit()
            return True
        except DBAPIError as e:
            cls.logger.info(f"Error in update: {e}")
            session.rollback()
            raise e

    def insert_orm(cls, session: Session, model, kwargs) -> Union[object, None]:
        try:
            obj = model(**kwargs)
            session.add(obj)
            session.commit()
            return obj
        except DBAPIError as e:
            cls.logger.info(f"Error in add_record_sync: {e}")
            session.rollback()
            return None

    def bulk_insert_orm(
        cls, session: Session, model: Any, records: List[dict]
    ) -> Union[List[uuid.UUID], List[dict]]:
        try:
            inserted_ids = []

            records_to_insert: List[dict] = [model(**record) for record in records]

            session.add_all(records_to_insert)
            session.flush()  # Flush the records to obtain their IDs

            records: dict = [record.to_dict() for record in records_to_insert]
            for record in records_to_insert:
                inserted_ids.append(record.uuid)
            session.commit()
            return inserted_ids, records
        except DBAPIError as e:
            cls.session.rollback()
            cls.logger.info(f"Error in add_records_sync: {e}")
            return [], []

    def insert_orm_on_conflict(
        cls,
        session: Session,
        model: Any,
        records: List[dict],
    ):
        for record in records:
            cls.insert_orm(session, model, record)

    def delete_orm(cls, session: Session, model: Any, records: List[uuid.UUID]) -> bool:
        try:
            session.query(model).filter(model.uuid.in_(records)).delete(
                synchronize_session=False
            )
            session.commit()
            cls.logger.info(f"Deleted {len(records)} records")
            return True
        except DBAPIError as e:
            session.rollback()
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
