import datetime as dt

import click
import httpx

from . import db, xtract


MEETUP_BASE_URL = 'https://www.meetup.com'
DEFAULT_GROUP_REFERENCES = ('python-lisbon-meetup', 'python-lisbon')


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
@click.argument('meetup_references', nargs=-1, default=DEFAULT_GROUP_REFERENCES)
@click.pass_context
def collect(ctx, meetup_references):

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


@main.command()
def serve():
    ...


if __name__ == '__main__':
    main()
