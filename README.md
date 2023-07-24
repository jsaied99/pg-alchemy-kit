# Documentation for `PG` Library

## Introduction
The `PG` library offers a suite of utilities to manage and interact with PostgreSQL databases using SQLAlchemy. It provides functionality such as initializing the database engine, creating tables, and managing sessions.

## Installation

`pip3 install pg-alchemy-kit` or if you prefer `poetry add pg-alchemy-kit`

## Usage

### 1. Initialization

To initialize the PostgreSQL utility class, use:

```python
from pg_alchemy_kit import PG

db = PG()
db.initialize(url="postgresql://username:password@localhost:5432/mydatabase")
```

- `url` (Optional): The connection string for the PostgreSQL database. If not provided, the default is derived from `get_engine_url()`, which uses the following environment variables:
  - `PG_USER`: The username for the database.
  - `PG_PASSWORD`: The password for the database.
  - `PG_HOST`: The host for the database.
  - `PG_PORT`: The port for the database.
  - `PG_DB`: The name of the database.

### 2. Creating Tables

To create tables in your PostgreSQL database:

```python
from your_orm_module import BaseModel1, BaseModel2

# Create tables for the models in the provided list
db.create_tables([BaseModel1, BaseModel2])
```

- `Bases`: A list of SQLAlchemy base models.
- `schemas`: A list of schema names. Default is `["public"]`.

### 3. Managing Sessions

**Context Manager**

Use the `get_session_ctx()` to manage your session using a context manager:

```python
with db.get_session_ctx() as session:
    # Use session for database operations here
    ...
```

**Generator**

You can also use `get_session()` to get a session:

```python
session = next(db.get_session())
```

### 4. Closing the Connection

After all operations, ensure you close the database connection:

```python
db.close()
```

## Logging

The `PG` class sets up a logger to capture messages. If you want to use your own logger, pass it during initialization:

```python
import logging

logger = logging.getLogger('my_custom_logger')
db.initialize(url="postgresql://username:password@localhost:5432/mydatabase", logger=logger)
```

# Documentation for `PGUtils` Class

## Introduction
`PGUtils` is a utility class that provides various database-related methods for performing CRUD operations, transforming SQL statements, and managing connections.

## Initialization
Before using `PGUtils`, it should be initialized:

```python
from your_module_path import PGUtils

logger = logging.getLogger('my_custom_logger')
db_utils = PGUtils(logger)
```

- `logger`: A logging instance to capture any log messages.

### Setting up a session:
After initializing, you should set up a session for further operations:

```python
session = db.get_session_ctx()  # Get this from the PG class
db_utils.initialize(session)
```

## Methods

### 1. SQL Execution
**Select Query**

To select records from the database:

```python
results = db_utils.select(session, "SELECT * FROM your_table WHERE condition=:condition", {'condition': value})
```

**Insert Query**

To insert records:

```python
status = db_utils.insert(session, "INSERT INTO your_table(column) VALUES (:value)", {'value': value})
```

**Delete Query**

To delete records:

```python
status = db_utils.delete(session, "DELETE FROM your_table WHERE condition=:condition", {'condition': value})
```

**Execute Query**

To execute any SQL:

```python
status = db_utils.execute(session, "YOUR SQL QUERY HERE")
```

**Update Query**

To update records:

```python
status = db_utils.update(session, ModelClass, {'key': key_value}, {'column_to_update': new_value})
```

### 2. ORM Operations

**Insert ORM Record**

To insert a single ORM record:

```python
record = db_utils.insert_orm(session, ModelClass, {'column': value})
```

**Bulk Insert ORM Records**

To insert multiple ORM records:

```python
ids, records = db_utils.bulk_insert_orm(session, ModelClass, [{'column1': value1}, {'column2': value2}])
```

**Insert ORM on Conflict**

To insert ORM records with conflict handling:

```python
db_utils.insert_orm_on_conflict(session, ModelClass, [{'column': value}])
```

**Delete ORM Records**

To delete ORM records:

```python
status = db_utils.delete_orm(session, ModelClass, [uuid1, uuid2])
```

**Get UUID**

To get the UUID of a record:

```python
record_uuid = db_utils.get_uuid(session, ModelClass, {'column': value})
```

### 3. Utilities

**Wrap SQL to JSON**

To wrap a SQL statement such that its result is returned as a JSON array:

```python
json_sql = PGUtils.wrap_to_json("YOUR SQL QUERY HERE")
```

### 4. Engine Management

**Get Engine**

To get an engine:

```python
engine = get_engine("postgresql://username:password@localhost:5432/mydatabase")
```

**Get Engine URL**

To get an engine URL:

```python
url = get_engine_url(connection_type="postgresql", pg_username="username", pg_password="password", pg_host="localhost", pg_port="5432", pg_db="mydatabase")
```

## Conclusion
The combination of `PG` and `PGUtils` offers a robust solution for database operations with PostgreSQL using SQLAlchemy. Whether you're using raw SQL or ORM models, these classes simplify your database tasks. Always ensure to handle exceptions and roll back sessions where necessary to maintain data integrity.