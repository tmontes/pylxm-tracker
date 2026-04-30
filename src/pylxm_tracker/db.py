import contextlib
import datetime as dt
import sqlite3


from . import data


_SCHEMA_MIGRATIONS = [
    (
        1,
        """
        CREATE TABLE groups (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            meetup_ref   TEXT NOT NULL,
            name         TEXT,
            members      INTEGER,
            rating       REAL,
            rating_count INTEGER,
            collected_ts TIMESTAMP NOT NULL
        )
        """,
    ),
    (
        2,
        """
        CREATE TABLE events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            meetup_ref   TEXT NOT NULL,
            ref          TEXT,
            name         TEXT,
            "when"       TIMESTAMP,
            attendees    INTEGER,
            collected_ts TIMESTAMP NOT NULL
        )
        """,
    ),
]

_SCHEMA_MIGRATIONS_CREATE = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        applied_at TIMESTAMP NOT NULL
    )
"""

_SCHEMA_MIGRATIONS_SELECT = """
    SELECT version FROM schema_migrations
"""

_SCHEMA_MIGRATIONS_INSERT = """
    INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)
"""


@contextlib.contextmanager
def connection(db_path: str):
    """Open a database connection, applying any pending schema migrations."""
    with sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES) as dbc:
        dbc.execute(_SCHEMA_MIGRATIONS_CREATE)
        applied = {row[0] for row in dbc.execute(_SCHEMA_MIGRATIONS_SELECT)}
        for version, sql in _SCHEMA_MIGRATIONS:
            if version not in applied:
                dbc.execute(sql)
                dbc.execute(
                    _SCHEMA_MIGRATIONS_INSERT,
                    {
                        'version': version,
                        'applied_at': dt.datetime.now(dt.timezone.utc),
                    },
                )
        yield dbc
    dbc.close()


def insert_group(
    conn: sqlite3.Connection,
    meetup_ref: str,
    group: data.Group,
    now: dt.datetime,
) -> None:
    """Insert a group snapshot row into the groups table."""
    conn.execute(
        """
        INSERT INTO
        groups (meetup_ref, name, members, rating, rating_count, collected_ts)
        VALUES (:meetup_ref, :name, :members, :rating, :rating_count, :collected_ts)
        """,
        {
            'meetup_ref': meetup_ref,
            **group.as_dict(),
            'collected_ts': now,
        },
    )


def insert_events(
    conn: sqlite3.Connection,
    meetup_ref: str,
    events: list[data.Event],
    now: dt.datetime,
) -> None:
    """Insert a batch of event snapshot rows into the events table."""
    conn.executemany(
        """
        INSERT INTO
        events (meetup_ref, ref, name, "when", attendees, collected_ts)
        VALUES (:meetup_ref, :ref, :name, :when, :attendees, :collected_ts)
        """,
        [
            {
                'meetup_ref': meetup_ref,
                **event.as_dict(),
                'collected_ts': now,
            }
            for event in events
        ],
    )
