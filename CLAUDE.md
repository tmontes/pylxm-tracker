# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run pylxm-tracker --help
uv run pylxm-tracker collect [MEETUP_REFERENCES...]
uv run pylxm-tracker render
uv run pylxm-tracker run [MEETUP_REFERENCES...]

# Run as a module
uv run python -m pylxm_tracker
```

The database path defaults to `pylxm-tracker.sqlite` and can be overridden with `--db-path` or the `PYLXM_TRACKER_DB_PATH` environment variable. The `render` output directory defaults to `ouput` (sic) and can be overridden with `--output-dir` or `PYLXM_TRACKER_OUTPUT_DIR`.

## Architecture

The tool scrapes Meetup.com group pages and stores snapshots in a local SQLite database. Each `collect` run appends new rows — it is append-only, not upsert.

**Data flow**: `__main__` fetches HTML via `httpx` → `xtract` parses it with BeautifulSoup into `data` dataclasses → `db` persists them.

**Modules**:
- `data.py` — `Group` and `Event` dataclasses with an `as_dict()` helper used for DB inserts.
- `xtract.py` — HTML parsing. All fields are optional (returns `None` on parse failure rather than raising). The `_event_from_card()` function strips timezone bracket notation (e.g. `[America/New_York]`) from datetime strings before parsing.
- `db.py` — Schema migrations run automatically on every `connection()` open. Migrations are versioned in `_SCHEMA_MIGRATIONS` (list of `(version, sql)` tuples). Both tables (`groups`, `events`) record a `collected_ts` timestamp per row.
- `render.py` — Reads data from the DB and writes a static `index.html` alongside a bundled `chart.umd.min.js` (downloaded from CDN on first run, cached thereafter). Uses Chart.js for time-series charts of member counts and ratings per group. The HTML is generated from `templates/index.html.tmpl` via `string.Template`.
- `__main__.py` — Click CLI; `collect` accepts multiple group references as arguments, defaulting to `('python-lisbon-meetup', 'python-lisbon')`; `render` generates the static HTML dashboard; `run` runs `collect` then `render`.

**Package manager**: `uv`. Python 3.14 required.
