import uuid
from sqlalchemy import select, Select

from typing import Any, List, Optional, Union

from .AsyncPGUtilsBase import AsyncPGUtilsBase, BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


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


class AsyncPGUtilsORM(AsyncPGUtilsBase):

    async def __execute_all(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> List[BaseModel]:
        result = await session.execute(stmt)
        return result.scalars().all()

    async def select(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[List[BaseModel], List[dict], Exception]:
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results: List[BaseModel] = await cls.__execute_all(session, stmt)

            if results is None:
                return []
            if convert_to_dict:
                return [record.to_dict() for record in results]

            return results

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[BaseModel, dict, Exception]:
        try:
            convert_to_dict = kwargs.get("convert_to_dict", False)
            results: List[BaseModel] = await cls.__execute_all(session, stmt)

            if results is None or len(results) != 1:
                return {}

            result: BaseModel = results[0]

            if convert_to_dict:
                return result.to_dict()

            return result

        except Exception as e:
            raise PGSelectError(str(e))

    async def select_one_strict(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[BaseModel, Exception]:
        result = await session.execute(stmt)
        result: Optional[BaseModel] = result.scalars().one()

        if result is None:
            raise PGNotExistsError("No records found")
        return result

    async def select_one_or_none(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[BaseModel, None, Exception]:
        result = await session.execute(stmt)
        result: Optional[BaseModel] = result.scalars().one_or_none()
        return result

    async def check_exists(
        cls, session: AsyncSession, stmt: Select, **kwargs
    ) -> Union[bool, Exception]:
        try:
            results: List[BaseModel] = await cls.__execute_all(session, stmt)

            if results is None:
                return False
            return len(results) > 0

        except Exception as e:
            raise PGNotExistsError(str(e))

    async def execute(
        cls, session: AsyncSession, stmt: Select
    ) -> Union[bool, Exception]:
        try:
            tmp = await session.execute(stmt)
            return tmp.fetchall()
        except Exception as e:
            raise PGSelectError(str(e))

    async def update(
        cls,
        session: AsyncSession,
        Model: BaseModel,
        filter_by: dict,
        values: dict,
        **kwargs,
    ) -> Union[BaseModel, Exception]:
        try:
            obj = await cls.select_one_strict(
                session, select(Model).filter_by(**filter_by)
            )
            to_snake_case = kwargs.get("to_snake_case", cls.snake_case)

            if to_snake_case:
                values = cls.to_snake_case([values])[0]

            for key, value in values.items():
                setattr(obj, key, value)

            if not cls.single_transaction:
                await session.commit()
            else:
                await session.flush()

            return obj

        except Exception as e:
            await session.rollback()
            raise PGUpdateError(str(e))

    async def insert(
        cls, session: AsyncSession, model, record: dict, **kwargs
    ) -> Union[BaseModel, Exception]:
        try:
            to_snake_case = kwargs.get("to_snake_case", cls.snake_case)

            if to_snake_case:
                record = cls.to_snake_case([record])[0]

            obj = model(**record)
            session.add(obj)
            if not cls.single_transaction:
                await session.commit()
            else:
                await session.flush()
            return obj
        except Exception as e:
            await session.rollback()
            raise PGInsertError(str(e))

    async def bulk_insert(
        cls, session: AsyncSession, model: Any, records: List[dict], **kwargs
    ) -> List[dict]:
        try:
            records_to_insert: List[dict] = [model(**record) for record in records]

            session.add_all(records_to_insert)
            await session.flush()  # Flush the records to obtain their IDs
            records: dict = [record.to_dict() for record in records_to_insert]

            if not cls.single_transaction:
                await session.commit()
            else:
                await session.flush()

            return records
        except Exception:
            await session.rollback()
            return []

    async def delete(
        cls, session: AsyncSession, record: BaseModel
    ) -> Union[bool, Exception]:
        try:
            await session.delete(record)
            if not cls.single_transaction:
                await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            raise PGDeleteError(str(e))

    async def delete_by_id(
        cls, session: AsyncSession, model: Any, record_id: Union[int, uuid.UUID]
    ) -> Union[bool, Exception]:
        try:
            stmt = select(model).where(model.id == record_id)
            record: BaseModel = await cls.select_one_strict(session, stmt)
            return await cls.delete(session, record)
        except Exception as e:
            raise PGDeleteError(str(e))
