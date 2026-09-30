# 03 · Partitioning

The photo service stores 40,000 photos ([dataset](../photo-data/)). This project splits them
over 4 machines (nodes) in different ways.

**Problem.** When the data or the load is too large for one machine, the rows must be split
over several machines (horizontal partitioning). A bad split gives one node much more data
or all the writes (a hot spot), makes queries ask all nodes, or moves most of the data when a
node is added.

**Idea.** Choose the partition key for the load and the most frequent queries: a hash of a
key spreads the rows evenly, and ranges keep related rows together. Use consistent hashing
so that a new node takes over only a small part of the keys. Split columns that are used
together from those that are used rarely (vertical partitioning). In files, one folder per
partition lets a query skip the other folders.

Consistent hashing puts 100 points per node on a ring; a key belongs to the next point
(`partitioning.ipynb`):

```python
class Ring:
    def __init__(self, nodes: int, points: int = 100):
        self.ring = sorted(
            (stable_hash(f"node{n}-{i}"), n) for n in range(nodes) for i in range(points)
        )
        self.keys = [h for h, _ in self.ring]

    def node(self, key) -> int:
        i = bisect.bisect(self.keys, stable_hash(key)) % len(self.ring)
        return self.ring[i][1]
```

## What the notebook shows

Open `partitioning.ipynb` on GitHub to see the outputs.

1. Three horizontal partitionings over 4 nodes:
   - hash of the user: the largest node has 12,255 photos (the mean is 10,000), because all
     5,124 photos of the most active user are on it;
   - ranges of the upload month: the sizes depend on the ranges and the season (the node with
     July and August has 16,016 photos), and all 2,312 uploads of the last week go to one
     node (a hot spot for writes);
   - hash of the photo id: 9,852 to 10,116 photos per node.
2. The number of nodes that a query must ask: the photos of one user (1 node with the user as
   key, else 4), the photos of one day (1 node with the month as key, else 4), one photo by
   its id (1 node, if the key is known).
3. A fifth node: with `hash % nodes`, 80% of the photos move to another node; with consistent
   hashing, 19% (about one fifth, all to the new node), but the nodes are less equal (6,913 to
   10,086 photos).
4. Vertical partitioning: the 5 columns of the library view in one table (3.0 MB as CSV), the
   7 columns of details in another (2.8 MB); both have the key `photo_id`.
5. Partition pruning: with one Parquet folder per month, the query for the photos of
   2021-12-03 reads 7 of 7 files; with the month in the condition, it reads 1 of 7 files.
   Both find 126 photos.

The parameter `NODES` at the top of the notebook changes the number of nodes.

## Tools

- [pandas](https://pandas.pydata.org) and [NumPy](https://numpy.org): data frames and arrays.
  Here: the assignment of photos to nodes.
- [`hashlib`](https://docs.python.org/3/library/hashlib.html): hash functions of Python's
  standard library. Here: a stable hash (MD5) for keys and ring points.
- [DuckDB](https://duckdb.org): an in-process SQL database for analytics. Here: it writes
  Parquet files partitioned by month and shows the files that a query reads
  (`EXPLAIN ANALYZE`).
- [Altair](https://altair-viz.github.io) with
  [vl-convert](https://github.com/vega/vl-convert): declarative charts, as PNG images. Here:
  the photos per node.
- [Jupyter](https://jupyter.org): notebooks with code and outputs.

## Run

Open `partitioning.ipynb` on GitHub to see the outputs. To change `NODES` and run it again,
with [uv](https://docs.astral.sh/uv/):

```sh
uv run jupyter lab partitioning.ipynb
```
