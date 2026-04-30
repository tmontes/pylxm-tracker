import datetime as dt
import dataclasses


@dataclasses.dataclass
class Group:
    name: str | None
    members: int | None
    rating: float | None
    rating_count: int | None


@dataclasses.dataclass
class Event:
    ref: str | None
    name: str | None
    when: dt.datetime | None
    attendees: int | None
