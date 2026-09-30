# 01 · Storage models: tables, documents, and log files

The photo service stores users, photos, cameras, and shared albums
([dataset](../photo-data/): 300 users, 40,000 photos), and its web servers write access logs.
This project stores the same data in three ways and asks the same questions.

**Problem.** Each storage model makes some questions and changes easy and others hard. The
choice decides how much the application code must do, how fast the queries are, and which
mistakes are possible.

**Idea.**

- In a *relational* database (PostgreSQL), the data is *normalized*: each fact is stored once,
  and tables refer to each other by keys. A declarative query language (SQL) joins the tables,
  and the database decides how to run the query. The schema rejects wrong values.
- In a *document* database (MongoDB), a photo is one document with its user and camera inside
  (*denormalized*). Reading one document is simple, but the copies must all change together,
  and relations between collections are the job of the application. There is no schema,
  unless you add one.
- *Log files* are unstructured text. It is easy to append a line, but there is no index: each
  question must read all lines.

The same question as SQL and as a MongoDB query (`queries.py`):

```sql
SELECT p.photo_id, p.path, u.photos_total
FROM photos p, users u
WHERE u.user_id = p.user_id AND u.account_name = 'ckaestne'
```

```python
db.photos.find({"user.account_name": "ckaestne"})
```

A photo document has copies of the user and the camera data inside (`load.py`):

```json
{"_id": 133388053, "path": "/st/u733/GGf33x4TWS.jpg",
 "user": {"account_name": "ckaestne", "account_id": "a/54351"}, "size": 4.4,
 "camera": {"manufacturer": "Google", "print_name": "Google Pixel 5",
            "settings": "ƒ/1.8; 1/60; 4.44mm; ISO422"}}
```

## What the code shows

- `schema.sql`: 6 tables with keys; the albums, their photos, and their followers are
  many-to-many relations (tables of pairs).
- `load.py` loads the same data into PostgreSQL and MongoDB (40,000 photos, 301 albums).
- `queries.py`:
  1. The photos of `ckaestne`: 5,124 rows in both databases. `EXPLAIN` shows the plan that
     PostgreSQL chose. Without an index, MongoDB reads all 40,000 documents; with an index on
     `user.account_name`, only 5,124.
  2. A renamed account: 1 row in PostgreSQL, but 5,124 photo documents and 24 album documents
     in MongoDB (every copy of the name must change, or the data becomes inconsistent).
  3. The photos in the albums that `eva.burk` follows (many-to-many): one SQL query with 3
     joins; in MongoDB three steps in the application (user, albums, photos). Both give the
     same 38 photos.
  4. A photo with the size `'5.7 MB'`: PostgreSQL rejects it (the column is a number); MongoDB
     accepts it, and rejects it only after we add an optional schema validator.
  5. The log files: the views of photo 133422131 (5 views) need a read of all 50,495 lines.

## Tools

- [PostgreSQL](https://www.postgresql.org) with [psycopg](https://www.psycopg.org): an
  open-source relational database, and its Python driver. Here: the normalized tables.
- [MongoDB](https://www.mongodb.com) with [PyMongo](https://pymongo.readthedocs.io): a
  document database, and its Python driver. Here: photos and albums as documents.
- [Docker Compose](https://docs.docker.com/compose/): starts both databases.

## Run

With [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/):

```sh
docker compose up -d     # PostgreSQL and MongoDB
uv run load.py           # the same data in both databases
uv run queries.py        # the questions and changes
docker compose down -v   # stop and remove the databases
```
