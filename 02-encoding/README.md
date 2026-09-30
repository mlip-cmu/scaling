# 02 · Data encoding

The photo service stores and sends photo records: the photo, its user, and its camera
(the 40,000 photos of the [dataset](../photo-data/), as nested records). This project writes
the same records in five encodings.

**Problem.** At scale, the encoding decides how much storage and network the data needs, how
fast programs read and write it, and whether a wrong value is found early. Text formats are
easy to read and to write, but large and without types; each JSON record repeats all field
names.

**Idea.** Compare plain text (CSV), semi-structured text (JSON), schema-based binary
encodings for records and messages (Avro, Protocol Buffers), and a columnar file format for
analytics (Parquet). A schema describes the names and types once, so the binary encodings
write only the values, and they reject values of the wrong type.

The schema of Protocol Buffers (`photo.proto`; `photo.avsc` is the same schema for Avro):

```protobuf
message Photo {
  int64 photo_id = 1;
  string path = 2;
  int64 upload_date = 3;  // milliseconds since 1970
  float size = 4;
  repeated string objects = 7;
  User user = 8;
  optional Camera camera = 9;
}
```

Parquet stores each column separately, so a program can read only the columns it needs
(`formats.py`):

```python
pq.read_table(io.BytesIO(data), columns=["photo_id", "size"])
```

## What the code shows

`formats.py`:

1. One photo as one message: JSON 347 bytes (with all field names), CSV 138 bytes (one flat
   line), Avro 132 bytes, Protobuf 144 bytes. As a file, Avro adds a header with the schema
   (956 bytes for one photo), and Parquet adds metadata (3,919 bytes): these formats are for
   many records.
2. All 40,000 photos (the times are the best of 3 runs on one machine; they change a little from
   run to run):

   | format | size | gzip | write | read | read 2 columns |
   |---|---:|---:|---:|---:|---:|
   | CSV | 5.4 MB | 1.4 MB | 0.24 s | 0.16 s | 0.19 s |
   | JSON | 13.7 MB | 1.6 MB | 0.18 s | 0.26 s | 0.27 s |
   | Avro | 5.1 MB | 1.5 MB | 0.33 s | 0.31 s | 0.31 s |
   | Protobuf | 5.7 MB | 1.6 MB | 0.29 s | 0.01 s | 0.04 s |
   | Parquet | 1.9 MB | (compressed) | 0.10 s | 0.02 s | 0.003 s |

   JSON is more than twice as large as the others; general compression (gzip) removes most of
   the repeated names. Parquet is the smallest (a column has similar values that compress
   well) and it reads 2 columns in 3 ms, because it does not read the other columns. The
   Protobuf library parses in C, so it is fast to read.
3. CSV gives back only strings (`size = '5.7'`, `objects = 'person;christmas tree'`). A
   record with the size `'5.7 MB'` is accepted by CSV and JSON, and rejected by Avro,
   Protobuf, and Parquet.

For schema evolution (a new version of a schema, and old data), see the data quality examples
of this course.

## Tools

- [`csv`](https://docs.python.org/3/library/csv.html) and
  [`json`](https://docs.python.org/3/library/json.html): Python's standard library for the
  text formats.
- [Apache Avro](https://avro.apache.org) with [fastavro](https://fastavro.readthedocs.io):
  a schema-based binary encoding, common for Kafka messages and data pipelines. Here: the
  records with the schema `photo.avsc`.
- [Protocol Buffers](https://protobuf.dev) (the `protobuf` package, and `grpcio-tools` for
  the compiler `protoc`): Google's schema-based binary encoding, common for remote procedure
  calls (gRPC). Here: the code for `photo.proto` is generated when the script starts.
- [Apache Parquet](https://parquet.apache.org) with [PyArrow](https://arrow.apache.org/docs/python/):
  a columnar, compressed file format for analytics. Here: the same records as a table with
  nested columns.

## Run

With [uv](https://docs.astral.sh/uv/):

```sh
uv run formats.py   # the files are in out/
```
