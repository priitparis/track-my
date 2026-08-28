"""Shared bits for the position source modules."""

import re

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Every column a source may fill, in the sheet's order minus the ones the
# orchestrator owns (`time`, `full_distance`). A source leaves any field
# it can't get as "".
SOURCE_FIELDS = [
    "lat", "lon", "reported_at",
    "speed", "course", "area", "status", "draught",
    "imo", "flag", "call_sign", "size", "gt", "dwt", "build",
    "distance_travelled", "remaining_distance", "avg_speed", "max_speed", "time_travelled",
    "temperature", "wind_speed", "wind_direction", "pressure", "humidity", "cloud_coverage",
    "source",
]

_TAG_STRIP_PATTERN = re.compile(r"<[^>]+>")


def blank_row(source):
    """A result dict with every source field present and empty except
    `source`. Callers overwrite the fields they actually found."""
    row = {key: "" for key in SOURCE_FIELDS}
    row["source"] = source
    return row


def strip_tags(raw):
    """Strip HTML tags and collapse whitespace."""
    text = _TAG_STRIP_PATTERN.sub(" ", raw)
    return re.sub(r"\s+", " ", text).strip()
