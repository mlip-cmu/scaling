"""The same 40,000 photo records as CSV, JSON, Avro, Protocol Buffers, and Parquet."""

import csv
import gzip
import io
import json
import sys
import time
from pathlib import Path

import fastavro
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from grpc_tools import protoc

import photo_data

OUT = Path("out")
OUT.mkdir(exist_ok=True)
protoc.main(["protoc", "-I.", f"--python_out={OUT}", "photo.proto"])
sys.path.insert(0, str(OUT))
import photo_pb2  # noqa: E402  (generated from photo.proto)


def records() -> list[dict]:
    """Photos as nested records (like documents): with the user and the camera inside."""
    p = photo_data.photos()
    users = photo_data.users().set_index("user_id").account_name
    cams = photo_data.cameras().set_index("camera_id")
    out = []
    for r in p.itertuples():
        camera = None
        if not pd.isna(r.camera_id):
            c = cams.loc[int(r.camera_id)]
            camera = {
                "manufacturer": c.manufacturer,
                "print_name": c.print_name,
                "settings": r.camera_setting,
            }
        out.append(
            {
                "photo_id": r.photo_id,
                "path": r.path,
                "upload_date": int(r.upload_date.timestamp() * 1000),
                "size": r.size,
                "format": r.format,
                "title": r.title,
                "objects": r.objects.split(";"),
                "user": {"user_id": r.user_id, "account_name": users[r.user_id]},
                "camera": camera,
            }
        )
    return out


def flat(r: dict) -> dict:
    cam = r["camera"] or {}
    return {k: v for k, v in r.items() if k not in ("user", "camera", "objects")} | {
        "objects": ";".join(r["objects"]),
        "user_id": r["user"]["user_id"],
        "account_name": r["user"]["account_name"],
        "camera": cam.get("print_name", ""),
        "camera_settings": cam.get("settings", ""),
    }


SCHEMA = fastavro.parse_schema(json.loads(Path("photo.avsc").read_text()))
ARROW = pa.schema(
    [
        ("photo_id", pa.int64()),
        ("path", pa.string()),
        ("upload_date", pa.timestamp("ms", tz="UTC")),
        ("size", pa.float32()),
        ("format", pa.string()),
        ("title", pa.string()),
        ("objects", pa.list_(pa.string())),
        ("user", pa.struct([("user_id", pa.int64()), ("account_name", pa.string())])),
        (
            "camera",
            pa.struct(
                [
                    ("manufacturer", pa.string()),
                    ("print_name", pa.string()),
                    ("settings", pa.string()),
                ]
            ),
        ),
    ]
)


def to_proto(r: dict):
    m = photo_pb2.Photo(**{k: v for k, v in r.items() if k not in ("user", "camera")})
    m.user.CopyFrom(photo_pb2.User(**r["user"]))
    if r["camera"]:
        m.camera.CopyFrom(photo_pb2.Camera(**r["camera"]))
    return m


def write(fmt: str, rs: list[dict]) -> bytes:
    if fmt == "CSV":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(flat(rs[0])))
        w.writeheader()
        w.writerows(flat(r) for r in rs)
        return buf.getvalue().encode()
    if fmt == "JSON":
        return "".join(json.dumps(r) + "\n" for r in rs).encode()
    if fmt == "Avro":
        buf = io.BytesIO()
        fastavro.writer(buf, SCHEMA, rs)
        return buf.getvalue()
    if fmt == "Protobuf":
        return photo_pb2.PhotoList(photos=[to_proto(r) for r in rs]).SerializeToString()
    if fmt == "Parquet":
        buf = io.BytesIO()
        pq.write_table(pa.Table.from_pylist(rs, schema=ARROW), buf)
        return buf.getvalue()
    raise ValueError(fmt)


def read(fmt: str, data: bytes, columns: list[str] | None = None):
    if fmt == "CSV":
        rows = list(csv.DictReader(io.StringIO(data.decode())))
    elif fmt == "JSON":
        rows = [json.loads(line) for line in data.decode().splitlines()]
    elif fmt == "Avro":
        rows = list(fastavro.reader(io.BytesIO(data)))
    elif fmt == "Protobuf":
        rows = photo_pb2.PhotoList.FromString(data).photos
    else:
        return pq.read_table(io.BytesIO(data), columns=columns)  # only these columns
    if columns:  # the other formats must parse whole records to get some columns
        rows = [[getattr(r, c) if fmt == "Protobuf" else r[c] for c in columns] for r in rows]
    return rows


def best(f, repeat: int = 3) -> float:
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        f()
        times.append(time.perf_counter() - start)
    return min(times)


FORMATS = ["CSV", "JSON", "Avro", "Protobuf", "Parquet"]

if __name__ == "__main__":
    rs = records()
    one = next(r for r in rs if r["photo_id"] == 133422131)
    print("1. One photo (133422131) as one message:")
    print(f"   JSON: {json.dumps(one, ensure_ascii=False)}")
    message = io.BytesIO()
    fastavro.schemaless_writer(message, SCHEMA, one)
    sizes = {
        "CSV (one line)": len(write("CSV", [one]).splitlines()[1]),
        "JSON": len(json.dumps(one).encode()),
        "Avro": len(message.getvalue()),
        "Protobuf": len(to_proto(one).SerializeToString()),
    }
    for fmt, n in sizes.items():
        print(f"   {fmt:<15} {n:>4} bytes")
    print("   Avro and Protobuf write only the values: the schema has the names and types.")
    print(f"   As files, Avro adds a header with the schema ({len(write('Avro', [one]))} bytes")
    print(f"   for one photo), and Parquet adds metadata ({len(write('Parquet', [one]))} bytes).\n")

    print(f"2. All {len(rs):,} photos (best of 3 runs):")
    print(f"   {'format':<9} {'size':>8} {'gzip':>8} {'write':>8} {'read':>8} {'2 columns':>10}")
    for fmt in FORMATS:
        data = write(fmt, rs)
        (OUT / f"photos.{fmt.lower()}").write_bytes(data)
        zipped = len(gzip.compress(data)) if fmt != "Parquet" else len(data)
        w = best(lambda fmt=fmt: write(fmt, rs))
        r = best(lambda fmt=fmt, data=data: read(fmt, data))
        c = best(lambda fmt=fmt, data=data: read(fmt, data, ["photo_id", "size"]))
        print(
            f"   {fmt:<9} {len(data) / 1e6:>6.2f}MB {zipped / 1e6:>6.2f}MB {w:>7.2f}s {r:>7.2f}s "
            f"{c:>9.3f}s"
        )
    print("   (Parquet is compressed already; gzip does not apply)\n")

    print("3. What comes back, and what happens with a wrong value (size = '5.7 MB'):")
    back = read("CSV", write("CSV", [one]))[0]
    print(f"   CSV gives back strings: size = {back['size']!r}, objects = {back['objects']!r}")
    bad = one | {"size": "5.7 MB"}
    for fmt in FORMATS:
        try:
            write(fmt, [bad])
            print(f"   {fmt:<9} accepted")
        except Exception as e:
            print(f"   {fmt:<9} rejected: {type(e).__name__}: {str(e).splitlines()[0][:70]}")
