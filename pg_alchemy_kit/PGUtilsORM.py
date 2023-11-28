import uuid
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.session import Session
from sqlalchemy import select, Select

from typing import Any, List, Optional, Union


from pg_alchemy_kit.PGUtilsBase import PGUtilsBase, BaseModel


class PGUtilsORM(PGUtilsBase):
    def handle_db_error(self, session: Session, error: Exception, action: str):
        """Handles database errors by logging and rolling back the session if needed."""
        self.logger.error(f"Error in {action}: {error}")
        if not self.single_transaction:
            session.rollback()
        raise error

    def select(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[List[dict], None]:
        """Executes a select statement and returns a list of results or None."""
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results: List[BaseModel] = session.execute(stmt).scalars().all()
            if results is None:
                return []
            if convert_to_dict:
                return [record.to_dict() for record in results]

            return results

        except DBAPIError as e:
            self.handle_db_error(session, e, "select")

    def select_one(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, dict]:
        """Executes a select statement and returns a single result or None."""
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results: BaseModel = session.execute(stmt).scalars().one()
            if results is None:
                return {}
            if convert_to_dict:
                return results.to_dict()

            return results

        except DBAPIError as e:
            self.handle_db_error(session, e, "select_one")

    def select_one_strict(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        """Executes a select statement and returns a single result or raises an exception."""
        result: Optional[BaseModel] = self.select_one(session, stmt, **kwargs)
        if result is None or result == {}:
            raise Exception("No records found")
        return result

    def check_exists(
        self, session: Session, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        """Executes a select statement and returns a boolean indicating if a record exists."""
        try:
            result: Optional[BaseModel] = session.execute(stmt).scalars().all()

            if result is None:
                return False
            return len(result) > 0

        except DBAPIError as e:
            self.handle_db_error(session, e, "check_exists")

    def execute(self, session: Session, stmt: Select) -> Union[bool, None]:
        """Executes a select statement and returns a boolean indicating if a record exists."""
        try:
            return session.execute(stmt).fetchall()
        except DBAPIError as e:
            self.handle_db_error(session, e, "execute")

    def update(
        self,
        session: Session,
        Model: BaseModel,
        filter_by: dict,
        values: dict,
        **kwargs,
    ) -> BaseModel:
        """Updates a record and returns the updated record."""
        try:
            update_kwargs = kwargs.get("update_kwargs", {})

            stmt = select(Model).with_for_update(**update_kwargs).filter_by(**filter_by)
            obj: BaseModel = self.select_one_strict(session, stmt)

            to_snake_case = kwargs.get("to_snake_case", self.snake_case)

            if to_snake_case:
                values = self.to_snake_case([values])[0]

            for key, value in values.items():
                setattr(obj, key, value)

            if not self.single_transaction:
                session.commit()

            return obj

        except DBAPIError as e:
            self.handle_db_error(session, e, "update")

    def bulk_update(
        self, session: Session, model: Any, records: List[dict]
    ) -> Union[bool, None]:
        """Updates a record and returns the updated record."""
        try:
            session.bulk_update_mappings(model, records)
            if not self.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            self.handle_db_error(session, e, "bulk_update")

    def insert(
        self, session: Session, model, record: dict, **kwargs
    ) -> Union[object, None]:
        """Inserts a record and returns the inserted record."""
        try:
            to_snake_case = kwargs.get("to_snake_case", self.snake_case)

            if to_snake_case:
                record = self.to_snake_case([record])[0]

            obj = model(**record)
            session.add(obj)
            if not self.single_transaction:
                session.commit()
            else:
                session.flush()
            return obj
        except DBAPIError as e:
            self.handle_db_error(session, e, "insert")

    def bulk_insert(
        self, session: Session, model: Any, records: List[dict], **kwargs
    ) -> List[dict]:
        try:
            records_to_insert: List[BaseModel] = [model(**record) for record in records]

            session.add_all(records_to_insert)
            session.flush()  # Flush the records to obtain their IDs
            records: dict = [record.to_dict() for record in records_to_insert]

            if not self.single_transaction:
                session.commit()

            return records
        except DBAPIError as e:
            self.handle_db_error(session, e, "bulk_insert")

    def insert_on_conflict(
        self,
        session: Session,
        model: Any,
        records: List[dict],
    ):
        for record in records:
            self.insert(session, model, record)

    def delete(self, session: Session, record: BaseModel) -> bool:
        try:
            session.delete(record)
            if not self.single_transaction:
                session.commit()
            return True
        except DBAPIError as e:
            self.handle_db_error(session, e, "delete")

    def delete_by_id(
        self, session: Session, model: Any, record_id: Union[int, uuid.UUID]
    ) -> bool:
        try:
            stmt = select(model).where(model.id == record_id)
            record: BaseModel = self.select_one_strict(session, stmt)
            return self.delete(session, record)
        except DBAPIError as e:
            self.handle_db_error(session, e, "delete_by_id")
