import uuid
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.session import Session
from sqlalchemy import select, Select

from typing import Any, List, Optional, Union


from pg_alchemy_kit.PGUtilsBase import PGUtilsBase, BaseModel


class PGUtilsORM(PGUtilsBase):
    def select(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[List[BaseModel], List[dict], Exception]:
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

    def select_one(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, dict, Exception]:
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

    def select_one_strict(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        result: Optional[BaseModel] = session.execute(stmt).scalars().one()
        if result is None:
            raise Exception("No records found")
        return result

    def check_exists(
        cls, session: Session, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        try:
            result: Optional[BaseModel] = session.execute(stmt).scalars().all()

            if result is None:
                return False
            return len(result) > 0

        except DBAPIError as e:
            raise e

    def execute(cls, session: Session, stmt: Select) -> Union[bool, Exception]:
        try:
            return session.execute(stmt).fetchall()
        except DBAPIError as e:
            raise e

    def update(
        cls, session: Session, Model: BaseModel, filter_by: dict, values: dict, **kwargs
    ) -> Union[BaseModel, Exception]:
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

    def bulk_update(
        cls, session: Session, model: Any, records: List[dict], **kwargs
    ) -> Union[bool, None]:
        try:
            to_snake_case = kwargs.get("to_snake_case", cls.snake_case)

            if to_snake_case:
                records = cls.to_snake_case(records)

            session.bulk_update_mappings(model, records)
            if not cls.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            cls.logger.info(f"Error in bulk_update: {e}")
            if not cls.single_transaction:
                session.rollback()
            raise e

    def insert(
        cls, session: Session, model, record: dict, **kwargs
    ) -> Union[BaseModel, Exception]:
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
            raise e

    def bulk_insert(
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

    def insert_on_conflict(
        cls,
        session: Session,
        model: Any,
        records: List[dict],
    ):
        for record in records:
            cls.insert(session, model, record)

    def delete(cls, session: Session, record: BaseModel) -> Union[bool, Exception]:
        try:
            session.delete(record)
            if not cls.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            if not cls.single_transaction:
                session.rollback()
            cls.logger.info(f"Error in remove_records_sync: {e}")
            raise e

    def delete_by_id(
        cls, session: Session, model: Any, record_id: Union[int, uuid.UUID]
    ) -> Union[bool, Exception]:
        try:
            stmt = select(model).where(model.id == record_id)
            record: BaseModel = cls.select_one_strict(session, stmt)
            return cls.delete(session, record)
        except DBAPIError as e:
            cls.logger.info(f"Error in remove_records_sync: {e}")
            raise e
