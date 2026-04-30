# pylxm-tracker

Track Meetup group metrics over time. Collects snapshots of group statistics and upcoming events, stores them in a local SQLite database, and generates a static HTML dashboard with time-series charts.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

## Usage

```bash
# Collect data for default groups (python-lisbon-meetup, python-lisbon)
uv run pylxm-tracker collect

# Collect data for specific groups
uv run pylxm-tracker collect my-group another-group

# Generate the HTML dashboard
uv run pylxm-tracker render

# Collect and render in one step
uv run pylxm-tracker run
uv run pylxm-tracker run my-group another-group
```

The dashboard is written to the `ouput/` directory as `index.html`.

## Configuration

| Option | CLI flag | Environment variable | Default |
|---|---|---|---|
| Database path | `--db-path` | `PYLXM_TRACKER_DB_PATH` | `pylxm-tracker.sqlite` |
| Output directory | `--output-dir` | `PYLXM_TRACKER_OUTPUT_DIR` | `ouput` |

## Docker

```bash
docker build -t pylxm-tracker .
docker run -v $(pwd)/data:/data pylxm-tracker
```

## Architecture

Data flows through four stages:

1. **`__main__.py`** — Click CLI; orchestrates the collect/render workflow.
2. **`xtract.py`** — Fetches Meetup group pages via `httpx` and parses them with BeautifulSoup into dataclasses.
3. **`db.py`** — Persists parsed data to SQLite. Schema migrations run automatically on every connection. Collection is append-only (no upserts), so full history is preserved.
4. **`render.py`** — Reads from the DB and renders a static `index.html` dashboard using Chart.js, showing member count, rating, and event attendance trends over time.

**Data models** (`data.py`): `Group` and `Event` dataclasses with optional fields (parse failures return `None` rather than raising).

## License

MIT © Tiago Montes
