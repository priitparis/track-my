"""Shared bits for the event source modules."""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Every field an event dict carries, in the "Events" sheet's column
# order minus `Time` (which the orchestrator builds from `date` + `time`).
# A source leaves any field it can't get as "".
EVENT_FIELDS = [
    "date", "time", "event",
    "port", "country",
    "lat", "lon", "speed", "course",
]


def blank_event():
    """An event dict with every field present and empty. Callers
    overwrite the fields they actually found."""
    return {key: "" for key in EVENT_FIELDS}
