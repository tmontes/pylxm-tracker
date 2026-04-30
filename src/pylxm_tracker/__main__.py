import datetime as dt

import click
import httpx

from . import db, xtract


MEETUP_BASE_URL = 'https://www.meetup.com'
DEFAULT_GROUP_REF = 'python-lisbon-meetup'


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
    ctx.ensure_object(dict)
    ctx.obj['db_path'] = db_path


@main.command()
@click.option(
    '--meetup-ref',
    default=DEFAULT_GROUP_REF,
    show_default=True,
    help="""
    The meetup.com group reference (eg: python-lisbon)
    """
)
@click.pass_context
def collect(ctx, meetup_ref):

    top_level_url = f'{MEETUP_BASE_URL}/{meetup_ref}'
    response = httpx.get(top_level_url, follow_redirects=True)
    html = response.text

    group = xtract.group_info_from_html(html)
    events = xtract.upcoming_events_from_html(html)

    now = dt.datetime.now(dt.timezone.utc)
    with db.connection(ctx.obj['db_path']) as dbc:
        db.insert_group(dbc, meetup_ref, group, now)
        db.insert_events(dbc, meetup_ref, events, now)


@main.command()
def serve():
    ...


if __name__ == '__main__':
    main()
