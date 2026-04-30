import datetime as dt
import logging
from importlib import metadata as ilm

import click
import httpx

from . import db, render as render_module, xtract


MEETUP_BASE_URL = 'https://www.meetup.com'
DEFAULT_GROUP_REFERENCES = ('python-lisbon-meetup', 'python-lisbon')


log = logging.getLogger(__package__)


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname).1s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logging.getLogger('httpx').setLevel(logging.WARNING)


@click.group()
@click.option(
    '--db-path',
    envvar='PYLXM_TRACKER_DB_PATH',
    default='pylxm-tracker.sqlite',
    show_default=True,
    type=click.Path(),
    help='Path to the SQLite database file.',
)
@click.pass_context
def main(ctx, db_path):
    """Meetup group tracker CLI."""
    ctx.ensure_object(dict)
    ctx.obj['db_path'] = db_path
    _setup_logging()
    log.info(f'version {ilm.version(__package__)}')


@main.command()
@click.argument('meetup_references', nargs=-1, default=DEFAULT_GROUP_REFERENCES)
@click.pass_context
def collect(ctx, meetup_references):
    """Fetch group info and upcoming events, storing them in the database."""

    collected = []
    for meetup_ref in meetup_references:
        top_level_url = f'{MEETUP_BASE_URL}/{meetup_ref}'
        response = httpx.get(top_level_url, follow_redirects=True)
        html = response.text

        group_info = xtract.group_info_from_html(html)
        group_events = xtract.upcoming_events_from_html(html)
        collected.append((meetup_ref, group_info, group_events))

    now = dt.datetime.now(dt.timezone.utc)
    with db.connection(ctx.obj['db_path']) as dbc:
        for meetup_ref, group_info, group_events in collected:
            db.insert_group(dbc, meetup_ref, group_info, now)
            db.insert_events(dbc, meetup_ref, group_events, now)

    for meetup_ref, group_info, group_events in collected:
        log.info(f'{meetup_ref}: {group_info.members} members, {len(group_events)} events')

    log.info('done')


@main.command()
@click.option(
    '--output-dir',
    envvar='PYLXM_TRACKER_OUTPUT_DIR',
    default='output',
    show_default=True,
    type=click.Path(),
    help='Directory to write dashboard.html and chart.umd.min.js into.',
)
@click.pass_context
def render(ctx, output_dir):
    """Render a static HTML dashboard from collected data."""
    render_module.render(ctx.obj['db_path'], output_dir)


if __name__ == '__main__':
    main()
