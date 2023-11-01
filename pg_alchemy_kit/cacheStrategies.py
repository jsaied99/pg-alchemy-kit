import datetime
import pickle
from sqlalchemy.orm import Session
from sqlalchemy import Select, Insert
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm.util import _ORMJoin
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound


MINUTE = 10


class CacheMissError(Exception):
    """Raised when the cache miss occurs."""


class CachedResult:
    def __init__(self, data):
        self._data = self._format_data(data)
        self._attributes = {}

    def _format_data(self, data):
        return [v for d in data for v in d.values()]

    def all(self):
        return self._data

    def fetchall(self):
        return self._data

    def fetchone(self):
        return self._data[0] if self._data else None

    def first(self):
        return self._data[0] if self._data else None

    def one(self):
        if len(self._data) == 1:
            return self._data[0]
        elif len(self._data) == 0:
            raise NoResultFound("No result found.")
        else:
            raise MultipleResultsFound("Multiple results found.")

    def scalar(self):
        result = self.one()
        return result[0] if result else None

    def scalars(self):
        return self

    def one_or_none(self):
        try:
            return self.one()
        except MultipleResultsFound:
            raise
        except NoResultFound:
            return None

    def unique(self):
        if len(self._data) == 0:
            raise NoResultFound("No result found.")
        elif len(self._data) > 1:
            raise MultipleResultsFound("Multiple results found.")
        return self._data[0]


class CachingSession(Session):
    def __init__(self, **options):
        self.cache_strategy: InMemoryCacheStrategy = options.pop(
            "cache_strategy", InMemoryCacheStrategy()
        )
        super().__init__(**options)

    def add(self, instance: object, _warn: bool = True) -> None:
        self.cache_strategy.add(self, instance, _warn=_warn)

    def delete(self, instance: object) -> None:
        return self.cache_strategy.delete(self, instance)

    def execute(self, statement, *multiparams, **params):
        if isinstance(statement, Select):
            try:
                return self.cache_strategy.select(
                    self, statement, *multiparams, **params
                )
            except CacheMissError:
                pass

        return super().execute(statement, *multiparams, **params)


class InMemoryCacheStrategy:
    def __init__(self, ttl: int = MINUTE):
        self.cache: dict = {}
        self.expire_times: dict = {}
        self.ttl: int = ttl

    def set_cache(self, cache_key: str, result: any):
        self.cache[cache_key] = pickle.dumps(result)
        self.expire_times[cache_key] = datetime.datetime.now().timestamp() + self.ttl

    def get_raw_data(self, cache_key: str) -> str:
        return self.cache.get(cache_key)

    def load_data(self, raw_data) -> any:
        return pickle.loads(raw_data)

    def _extract_table_name(self, from_clause):
        """Extract table name(s) from a SQLAlchemy clause (table or join)."""

        if hasattr(from_clause, "name"):
            return [from_clause.name]

        elif isinstance(from_clause, _ORMJoin):
            left_names = self._extract_table_name(from_clause.left)
            right_names = self._extract_table_name(from_clause.right)
            return left_names + right_names

        return []

    def extract_table_name(self, statement: Select) -> str:
        return self._extract_table_name(statement.froms[0])[0]

    def check_expired(self, raw_data: any, cache_key: str) -> bool:
        if (
            raw_data
            and self.expire_times.get(cache_key, 0)
            <= datetime.datetime.now().timestamp()
        ):
            print("Expired, removing from cache")
            del self.cache[cache_key]
            raw_data = None

    def select(self, session: Session, statement: Select, *multiparams, **params):
        cache_key = self.generate_cache_key(session, statement)
        raw_data = self.get_raw_data(cache_key)

        self.check_expired(raw_data, cache_key)

        if raw_data is None:
            result = self.__execute(session, statement, *multiparams, **params)
            self.set_cache(cache_key, result)
        else:
            result = self.load_data(raw_data)

        return CachedResult(result)

    def add(self, session: Session, instance: object, _warn: bool = True) -> None:
        self.clear_cache_for_table(session, instance.__table__.name)
        super(CachingSession, session).add(instance, _warn=_warn)

    def delete(self, session: Session, instance: object) -> None:
        self.clear_cache_for_table(session, instance.__table__.name)
        return super(CachingSession, session).delete(instance)

    def clear_cache_for_table(self, session: Session, table_name: str):
        cache_keys = list(filter(lambda x: x.startswith(table_name), self.cache.keys()))

        for cache_key in cache_keys:
            del self.cache[cache_key]

    def __execute(self, session: Session, statement: Select, *multiparams, **params):
        return (
            super(CachingSession, session)
            .execute(statement, *multiparams, **params)
            # .scalars()
            # .all()
            # .fetchall()
            .mappings()
            .all()
        )

    def generate_cache_key(self, session: Session, statement: Select) -> str:
        return f"{self.extract_table_name(statement)}:{self.get_sql_stmt(statement)}"

    def get_sql_stmt(self, statement: Select) -> str:
        "Use the statement's SQL and parameters as the cache key"
        return str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
