# 07 · Event sourcing

Users of the photo service add photos, give them titles, apply filters, and delete them. This
project stores 10 such changes to three photos (the photos 133422131 to 133422133 of the
[dataset](../photo-data/)) as events.

**Problem.** A normal database table keeps only the current state: an `UPDATE` overwrites the
old value and a `DELETE` removes the row. The history is lost: which title did a photo have
before, which photos were deleted, and which filters did users try and then undo? This
information can be valuable later, for example as training data.

**Idea.** Never change data; record each change as an event in an append-only log (event
sourcing). The current state is computed by replaying all events in order. Replaying only the
events up to a given time gives the state at that time. Different components can compute
different views from the same log. Snapshots make replays faster.

The event store only accepts new events (`event_sourcing.ipynb`):

```sql
CREATE TABLE events (seq INTEGER PRIMARY KEY, time TEXT, type TEXT, photo_id INTEGER, data TEXT);
CREATE TRIGGER no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;
CREATE TRIGGER no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append only'); END;
```

The state is a function of the events:

```python
def replay(events: pd.DataFrame, state: dict | None = None) -> dict:
    state = dict(state or {})
    for e in events.itertuples():
        state = apply(state, e)
    return state


def state_at(time: str) -> pd.DataFrame:
    return table(replay(events[events.time <= time]))
```

## What the notebook shows

Open `event_sourcing.ipynb` on GitHub to see the outputs.

1. The 10 events, for example `replacePhoto(id=133422131, user=54351,
   path="/st/x594/vipxBMFlLF.jpg", operation="/filter/palma")`. An `UPDATE` of the log is
   rejected.
2. The current state after a replay of all events: 2 photos.
3. One table with the state of the three photos after each of the 10 events.
4. The state on 2021-12-05, which still has photo 133422131 (with the title "Sunset" and the
   palma filter); it was deleted on 2021-12-06.
5. Views from the same log: photos per user, all filter operations, the deleted photos, and a
   photo where the user tried a filter and undid it 34 seconds later.
6. A mutable table with the same changes has the same current state, but it cannot answer the
   questions of step 5.
7. A snapshot after event 6 (a copy of all 3 photos) plus a replay of the 4 later events gives
   the same state as a replay of all 10 events.
8. Drawbacks: 10 events for 2 photos, and the deleted photo 133422131 (with its path) is still
   in the log. Deleting personal data from an append-only log needs extra work, for example
   crypto-shredding: encrypt the data of each user with a separate key, and delete the key.

## Tools

- [SQLite](https://sqlite.org) through Python's
  [`sqlite3`](https://docs.python.org/3/library/sqlite3.html): an embedded database. Here: the
  event store (append-only with triggers) and the mutable table for comparison.
- [pandas](https://pandas.pydata.org): data frames. Here: the tables of events and states.
- [Jupyter](https://jupyter.org): notebooks with code and outputs. Here: all steps on one
  page.

Event stores for production are, for example, [KurrentDB](https://www.kurrent.io) (formerly
EventStoreDB) and Kafka topics with unlimited retention (see [`06`](../06-stream-processing/)).

## Run

Open `event_sourcing.ipynb` on GitHub to see the outputs. To run it again, with
[uv](https://docs.astral.sh/uv/):

```sh
uv run jupyter lab event_sourcing.ipynb
```
