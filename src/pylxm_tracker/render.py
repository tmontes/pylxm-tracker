import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path

import httpx

from . import db


log = logging.getLogger(__package__)

CHARTJS_CDN_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js'
CHARTJS_FILENAME = 'chart.umd.min.js'
DASHBOARD_FILENAME = 'dashboard.html'

_PALETTE = [
    '#4e79a7',
    '#f28e2b',
    '#e15759',
    '#76b7b2',
    '#59a14f',
    '#edc948',
]


def _ensure_chartjs(output_dir: Path) -> None:
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


# JS object literals returned by axis factories — interpolated once into the script block.
# Both reference fmtDDMMM(), which is defined at the top of the script block.
_X_AXIS_OBJ = """{
            type: 'linear',
            ticks: {
                callback: (v) => fmtDDMMM(v),
                maxTicksLimit: 10,
            },
        }"""

# Event charts: one tick per week, always on a Thursday.
_EVENT_X_AXIS_OBJ = """{
            type: 'linear',
            ticks: {
                callback: (v) => fmtDDMMM(v),
            },
            afterBuildTicks: (scale) => {
                if (scale.min == null || scale.max == null) return;
                const ticks = [];
                const d = new Date(scale.min);
                d.setDate(d.getDate() + (4 - d.getDay() + 7) % 7);
                d.setHours(0, 0, 0, 0);
                // If the Thursday snapped to midnight falls at or before scale.min
                // (grid line would overlap the Y axis), advance to the next Thursday.
                if (d.getTime() <= scale.min) d.setDate(d.getDate() + 7);
                while (d.getTime() <= scale.max) {
                    ticks.push({value: d.getTime()});
                    d.setDate(d.getDate() + 7);
                }
                scale.ticks = ticks;
            },
        }"""


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

    members_json = json.dumps(members_datasets)
    rating_json = json.dumps(rating_datasets)
    count_json = json.dumps(count_datasets)
    events_json = json.dumps(events_payload)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Python 🐍 Lisbon Meetup tracker</title>
    <script src="./{CHARTJS_FILENAME}"></script>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; }}
        body {{
            font-family: system-ui, sans-serif;
            margin: 0;
            padding: 2rem;
            background: #f5f5f5;
            color: #212529;
        }}
        h1 {{ font-size: 1.25rem; font-weight: 600; margin: 0 0 2rem; }}
        h2 {{ font-size: 0.875rem; font-weight: 600; text-transform: uppercase;
              letter-spacing: .05em; color: #6c757d; margin: 0 0 0.75rem; }}
        h3 {{ font-size: 0.875rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }}
        .card {{
            background: #fff;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,.08);
            position: relative;
            height: 360px;
        }}
        .events-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .events-grid .card {{
            height: 260px;
            margin-bottom: 0;
        }}
    </style>
</head>
<body>
    <h1>Python 🐍 Lisbon Meetup tracker</h1>

    <h2>Members over time</h2>
    <div class="card">
        <canvas id="membersChart"></canvas>
    </div>

    <h2>Rating over time</h2>
    <div class="card">
        <canvas id="ratingChart"></canvas>
    </div>

    <h2>Review count over time</h2>
    <div class="card">
        <canvas id="countChart"></canvas>
    </div>

    <h1>Upcoming Events</h1>
    <div id="eventsSection"></div>

    <script>
        const membersDatasets = {members_json};
        const ratingDatasets = {rating_json};
        const countDatasets = {count_json};
        const eventsData = {events_json};

        // Date formatters used throughout all charts.
        const fmtDDMMM = (ms) => {{
            const d = new Date(ms);
            return String(d.getDate()).padStart(2, '0') + '\u00a0' +
                   d.toLocaleString(undefined, {{month: 'short'}});
        }};
        const fmtDDMMMYYYY = (ms) => fmtDDMMM(ms) + ' ' + new Date(ms).getFullYear();

        // Returns a fresh x-axis config object (Chart.js mutates options).
        const makeXAxis = () => ({_X_AXIS_OBJ});

        // For event charts: no year, fewer ticks.
        const makeEventXAxis = () => ({_EVENT_X_AXIS_OBJ});

        // Returns a tooltip config that formats the x timestamp as a readable date.
        const makeTooltip = () => ({{
            callbacks: {{
                title: (items) => fmtDDMMMYYYY(items[0].parsed.x),
            }},
        }});

        // Draws a dashed vertical line at whenMs, plus a rotated label at the top.
        const eventDatePlugin = {{
            id: 'eventDate',
            afterDraw(chart) {{
                const whenMs = chart.options.plugins?.eventDate?.whenMs;
                if (whenMs == null) return;
                const {{ctx, scales: {{x, y}}}} = chart;
                const px = x.getPixelForValue(whenMs);
                ctx.save();

                // Dashed line
                ctx.beginPath();
                ctx.moveTo(px, y.top);
                ctx.lineTo(px, y.bottom);
                ctx.strokeStyle = 'rgba(220, 80, 60, 0.7)';
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.stroke();

                // Rotated "Event date" label, centred vertically in the plot area
                ctx.setLineDash([]);
                ctx.fillStyle = 'rgba(220, 80, 60, 0.85)';
                ctx.font = '10px system-ui, sans-serif';
                ctx.textAlign = 'center';
                ctx.translate(px - 4, (y.top + y.bottom) / 2);
                ctx.rotate(-Math.PI / 2);
                ctx.fillText('Meetup date', 0, 0);

                ctx.restore();
            }},
        }};
        Chart.register(eventDatePlugin);

        new Chart(document.getElementById('membersChart'), {{
            type: 'line',
            data: {{datasets: membersDatasets}},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                parsing: false,
                plugins: {{tooltip: makeTooltip()}},
                scales: {{x: makeXAxis(), y: {{min: 0, title: {{display: true, text: 'Members'}}}}}},
            }},
        }});

        new Chart(document.getElementById('ratingChart'), {{
            type: 'line',
            data: {{datasets: ratingDatasets}},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                parsing: false,
                plugins: {{tooltip: makeTooltip()}},
                scales: {{
                    x: makeXAxis(),
                    y: {{min: 0, max: 5, title: {{display: true, text: 'Rating'}}}},
                }},
            }},
        }});

        new Chart(document.getElementById('countChart'), {{
            type: 'line',
            data: {{datasets: countDatasets}},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                parsing: false,
                plugins: {{tooltip: makeTooltip()}},
                scales: {{x: makeXAxis(), y: {{min: 0, title: {{display: true, text: 'Review count'}}}}}},
            }},
        }});

        // Per-group, per-event charts
        const section = document.getElementById('eventsSection');
        for (const [meetupRef, group] of Object.entries(eventsData)) {{
            const heading = document.createElement('h2');
            heading.textContent = group.label;
            section.appendChild(heading);

            const grid = document.createElement('div');
            grid.className = 'events-grid';
            section.appendChild(grid);

            for (const [eventRef, event] of Object.entries(group.events)) {{
                const card = document.createElement('div');
                card.className = 'card';
                const canvas = document.createElement('canvas');
                card.appendChild(canvas);
                grid.appendChild(card);

                // Normalise event time to local midnight so the event line coincides
                // with the Thursday tick (which afterBuildTicks also snaps to midnight).
                const _whenDay = new Date(event.when_ms);
                _whenDay.setHours(0, 0, 0, 0);
                const _whenDayMs = _whenDay.getTime();

                const eventDateLabel = event.when_ms ? fmtDDMMMYYYY(_whenDayMs) : '';

                // X-axis range: event line sits at 14/15 of total width.
                // Left span is at least 2 weeks; expands if data reaches further back.
                const _dataMin = event.data.length > 0
                    ? Math.min(...event.data.map(p => p.x))
                    : _whenDayMs - 14 * 86400000;
                const _leftSpan = Math.max(_whenDayMs - _dataMin + 86400000, 14 * 86400000);
                const _xMin = _whenDayMs - _leftSpan;
                const _xMax = _whenDayMs + _leftSpan / 14;

                new Chart(canvas, {{
                    type: 'line',
                    data: {{
                        datasets: [{{
                            label: event.name,
                            data: event.data,
                            borderColor: group.color,
                            backgroundColor: group.color + '33',
                            tension: 0.3,
                            parsing: false,
                        }}],
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        parsing: false,
                        plugins: {{
                            legend: {{display: false}},
                            title: {{display: true, text: [event.name, eventDateLabel]}},
                            tooltip: makeTooltip(),
                            eventDate: {{whenMs: _whenDayMs}},
                        }},
                        scales: {{
                            x: {{...makeEventXAxis(), min: _xMin, max: _xMax}},
                            y: {{
                                beginAtZero: true,
                                title: {{display: true, text: 'Attendees'}},
                            }},
                        }},
                    }},
                }});
            }}
        }}
    </script>
</body>
</html>"""


def render(db_path: str, output_dir: str) -> None:
    """Query the database and write dashboard.html + chart.umd.min.js to output_dir."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    _ensure_chartjs(out)

    with db.connection(db_path) as conn:
        groups = _query_groups(conn)
        events_by_group = _query_events(conn)

    html = _generate_html(groups, events_by_group)
    html_path = out / DASHBOARD_FILENAME
    html_path.write_text(html, encoding='utf-8')
    log.info(f'dashboard written to {html_path}')
