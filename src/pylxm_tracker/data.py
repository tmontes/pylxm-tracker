import datetime as dt
import dataclasses


@dataclasses.dataclass
class _AsDict:
    def as_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Group(_AsDict):
    name: str | None
    members: int | None
    rating: float | None
    rating_count: int | None


@dataclasses.dataclass
class Event(_AsDict):
    ref: str | None
    name: str | None
    when: dt.datetime | None
    attendees: int | None
