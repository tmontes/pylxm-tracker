import datetime as dt
import logging
import re
import zoneinfo

import bs4

from . import data



log = logging.getLogger(__name__.split('.')[-1])



def group_info_from_html(html: str) -> data.Group:

    soup = bs4.BeautifulSoup(html, 'html.parser')

    h1 = soup.find('h1')
    name = h1.get_text(strip=True) if h1 else None

    tag = soup.find(id='member-count-link')
    if not tag:
        log.warning('member-count-link tag not found')
        members = None
    else:
        text = tag.get_text(strip=True)
        if not (match := re.search(r'(\d+)', text)):
            log.warning('no member count match in %r', text)
            members = None
        else:
            members = int(match.group(1))

    rating_tag = soup.find(string=re.compile(r'^\d+\.\d+$'))
    rating = float(rating_tag.get_text(strip=True)) if rating_tag else None

    ratings_link = soup.find('a', href=re.compile(r'feedback-overview'))
    if ratings_link and (match := re.search(r'(\d+)', ratings_link.get_text(strip=True))):
        rating_count = int(match.group(1))
    else:
        rating_count = None

    return data.Group(name=name, members=members, rating=rating, rating_count=rating_count)



def upcoming_events_from_html(html: str) -> list[data.Event]:
    soup = bs4.BeautifulSoup(html, 'html.parser')
    upcoming_h2 = soup.find(id='upcoming-section')
    if not upcoming_h2:
        print('upcoming_h2 not found')
        return []
    header_container = upcoming_h2.parent.parent
    events_ul = header_container.find_next_sibling('ul')
    if not events_ul:
        print('events_ul not found')
        return []
    return [
        _event_from_card(card)
        for card in events_ul.find_all(attrs={'data-element-name': 'event-card'})
    ]



def _event_from_card(card) -> data.Event:

    h3 = card.find('h3')

    ref = card.get('data-eventref')
    ref = str(ref) if ref else None

    name = h3.get_text(strip=True) if h3 else None

    text = card.get_text()
    match = re.search(r'(\d+)\s+attendee', text, re.IGNORECASE)
    attendees = int(match.group(1)) if match else None

    if (time_tag := card.find('time')):
        when_text = str(time_tag['datetime'])
        tz_match = re.search(r'\[([^\]]+)\]$', when_text)
        tz = zoneinfo.ZoneInfo(tz_match.group(1)) if tz_match else dt.timezone.utc
        when = dt.datetime.fromisoformat(re.sub(r'\[.*\]$', '', when_text)).replace(tzinfo=tz)
    else:
        when = None

    return data.Event(ref=ref, name=name, attendees=attendees, when=when)
