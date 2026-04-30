import click
import httpx

from . import xtract


MEETUP_BASE_URL = 'https://www.meetup.com'
DEFAULT_GROUP_REF = 'python-lisbon-meetup'


@click.group()
def main():
    ...

@main.command()
@click.option(
    '--meetup-ref',
    default=DEFAULT_GROUP_REF,
    show_default=True,
    help="""
    The meetup.com group reference (eg: python-lisbon)
    """
)
def collect(meetup_ref):
    
    top_level_url = f'{MEETUP_BASE_URL}/{meetup_ref}'

    response = httpx.get(top_level_url, follow_redirects=True)
    html = response.text

    group = xtract.group_info_from_html(html)
    print(f'{group=}')

    events = xtract.upcoming_events_from_html(html)
    print(f'{events=}')


@main.command()
def serve():
    ...



if __name__ == '__main__':
    main()
