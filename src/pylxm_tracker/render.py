import datetime as dt
from importlib import resources as ilr
import json
import logging
import pathlib
import sqlite3
import string

import httpx

from . import db, templates


_TEMPLATES = ilr.files(templates)


log = logging.getLogger(__package__)

CHARTJS_CDN_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js'
CHARTJS_FILENAME = 'chart.umd.min.js'
DASHBOARD_FILENAME = 'index.html'

_PALETTE = [
    '#4e79a7',
    '#f28e2b',
    '#e15759',
    '#76b7b2',
    '#59a14f',
    '#edc948',
]


def _ensure_chartjs(output_dir: pathlib.Path) -> None:
    js_path = output_dir / CHARTJS_FILENAME
    if js_path.exists():
        log.info(f'{CHARTJS_FILENAME} already present, skipping download')
        return
    log.info(f'downloading {CHARTJS_FILENAME} from CDN')
    response = httpx.get(CHARTJS_CDN_URL, follow_redirects=True)
    response.raise_for_status()
    js_path.write_bytes(response.content)
    log.info(f'{CHARTJS_FILENAME} saved ({len(response.content):,} bytes)')


def _to_ms(value) -> int:
    """Convert a collected_ts value (datetime or ISO string) to JS milliseconds."""
    if isinstance(value, dt.datetime):
        return int(value.timestamp() * 1000)
    # Fallback: parse ISO string (sqlite3 may return str when TZ is present)
    parsed = dt.datetime.fromisoformat(str(value))
    return int(parsed.timestamp() * 1000)


def _query_groups(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT meetup_ref, name, collected_ts, members, rating, rating_count
        FROM groups
        ORDER BY meetup_ref, collected_ts
        """
    ).fetchall()

    by_ref: dict[str, dict] = {}
    for meetup_ref, name, collected_ts, members, rating, rating_count in rows:
        series = by_ref.setdefault(meetup_ref, {'label': meetup_ref, 'members': [], 'rating': [], 'rating_count': []})
        if name is not None:
            series['label'] = name
        ts_ms = _to_ms(collected_ts)
        if members is not None:
            series['members'].append({'x': ts_ms, 'y': members})
        if rating is not None:
            series['rating'].append({'x': ts_ms, 'y': rating})
        if rating_count is not None:
            series['rating_count'].append({'x': ts_ms, 'y': rating_count})

    return by_ref


def _query_events(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT meetup_ref, ref, name, CAST("when" AS TEXT), collected_ts, attendees
        FROM events
        WHERE ref IS NOT NULL
        ORDER BY meetup_ref, ref, collected_ts
        """
    ).fetchall()

    by_group: dict[str, dict] = {}
    for meetup_ref, ref, name, when, collected_ts, attendees in rows:
        group_events = by_group.setdefault(meetup_ref, {})
        if ref not in group_events:
            group_events[ref] = {
                'name': name or ref,
                'when_ms': _to_ms(when) if when is not None else None,
                'data': [],
            }
        event = group_events[ref]
        if name is not None:
            event['name'] = name
        ts_ms = _to_ms(collected_ts)
        if attendees is not None:
            event['data'].append({'x': ts_ms, 'y': attendees})

    # Sort each group's events by event date
    return {
        meetup_ref: dict(
            sorted(events.items(), key=lambda kv: kv[1]['when_ms'] or 0)
        )
        for meetup_ref, events in by_group.items()
    }


def _generate_html(groups: dict, events_by_group: dict) -> str:
    refs = list(groups.keys())
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(refs))]
    color_by_ref = {ref: colors[i] for i, ref in enumerate(refs)}

    members_datasets = [
        {
            'label': groups[ref]['label'],
            'data': groups[ref]['members'],
            'borderColor': colors[i],
            'backgroundColor': colors[i] + '33',
            'tension': 0.3,
        }
        for i, ref in enumerate(refs)
    ]

    rating_datasets = [
        {
            'label': groups[ref]['label'],
            'data': groups[ref]['rating'],
            'borderColor': colors[i],
            'tension': 0.3,
        }
        for i, ref in enumerate(refs)
    ]

    count_datasets = [
        {
            'label': groups[ref]['label'],
            'data': groups[ref]['rating_count'],
            'borderColor': colors[i],
            'tension': 0.3,
        }
        for i, ref in enumerate(refs)
    ]

    # Per-event data: attach the group color so JS can use it
    events_payload = {
        meetup_ref: {
            'label': groups.get(meetup_ref, {}).get('label', meetup_ref),
            'color': color_by_ref.get(meetup_ref, _PALETTE[0]),
            'events': events,
        }
        for meetup_ref, events in events_by_group.items()
    }

    tmpl = string.Template(
        _TEMPLATES.joinpath('index.html.tmpl').read_text(encoding='utf-8')
    )
    return tmpl.substitute(
        members_json=json.dumps(members_datasets),
        rating_json=json.dumps(rating_datasets),
        count_json=json.dumps(count_datasets),
        events_json=json.dumps(events_payload),
    )


def render(db_path: str, output_dir: str) -> None:
    """Query the database and write index.html + chart.umd.min.js to output_dir."""

    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    _ensure_chartjs(out)

    with db.connection(db_path) as conn:
        groups = _query_groups(conn)
        events_by_group = _query_events(conn)

    html = _generate_html(groups, events_by_group)
    html_path = out / DASHBOARD_FILENAME
    html_path.write_text(html, encoding='utf-8')
    log.info(f'dashboard written to {html_path}')
