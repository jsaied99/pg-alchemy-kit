import pickle
from sqlalchemy.orm import Session
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql
import time
import datetime

MINUTE = 10


class CacheMissError(Exception):
    """Raised when the cache miss occurs."""


class CachedResult:
    def __init__(self, data):
        self._data = data

    def scalars(self):
        return self

    def all(self):
        return self._data


class CachingSession(Session):
    def __init__(self, **options):
        self.cache_strategy: InMemoryCacheStrategy = options.pop(
            "cache_strategy", InMemoryCacheStrategy()
        )
        super().__init__(**options)

    def execute(self, statement, *multiparams, **params):
        if isinstance(statement, Select):
            try:
                return self.cache_strategy.exec(self, statement, *multiparams, **params)
            except CacheMissError:
                pass

        return super().execute(statement, *multiparams, **params)


class InMemoryCacheStrategy:
    def __init__(self, ttl: int = MINUTE):
        self.cache: dict = {}
        self.expire_times: dict = {}
        self.ttl: int = ttl

    def set_key(self, cache_key: str, result: any):
        self.cache[cache_key] = pickle.dumps(result)
        self.expire_times[cache_key] = datetime.datetime.now().timestamp() + self.ttl

    def get_key(self, cache_key: str) -> str:
        return self.cache.get(cache_key)

    def get_value(self, raw_data) -> any:
        return pickle.loads(raw_data)

    def check_expired(self, raw_data: any, cache_key: str) -> bool:
        if (
            raw_data
            and self.expire_times.get(cache_key, 0)
            <= datetime.datetime.now().timestamp()
        ):
            print("Expired, removing from cache")
            del self.cache[cache_key]
            raw_data = None

    def exec(self, session: Session, statement: Select, *multiparams, **params):
        cache_key = self.create_cache_key(statement)
        raw_data = self.get_key(cache_key)

        self.check_expired(raw_data, cache_key)

        if raw_data is None:
            result = self.__execute(session, statement, *multiparams, **params)
            self.set_key(cache_key, result)
        else:
            result = self.get_value(raw_data)

        return CachedResult(result)

    def __execute(self, session: Session, statement: Select, *multiparams, **params):
        return (
            super(CachingSession, session)
            .execute(statement, *multiparams, **params)
            .scalars()
            .all()
        )

    def create_cache_key(self, statement: Select) -> str:
        return self.get_sql_stmt(statement)

    def get_sql_stmt(self, statement: Select) -> str:
        "Use the statement's SQL and parameters as the cache key"
        return str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
