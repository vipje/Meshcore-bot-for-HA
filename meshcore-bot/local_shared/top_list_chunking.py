"""Shared helper for the topu/topc/topr commands.

Packs a header + numbered leaderboard lines into LoRa-sized message chunks,
splitting across multiple mesh messages instead of exceeding the ~130-160
byte payload budget (BaseCommand.get_max_message_length) and failing to send
outright. send_response() returns False on an oversized single message with
no visible truncation - the "Failed" badge in the HA chat bridge was the
first sign of this, once topr's top-5 (longer repeater names) pushed past
what topu/topc's top-3 output happened to fit under.
"""


def parse_days_arg(content: str, keyword: str, default: int = 1, max_days: int = 90) -> int:
    """Parse an optional '<keyword> <N>' day-count argument, e.g. 'topu 7' -> 7.

    Falls back to `default` (1 = last 24h) for no argument, a non-integer, or
    a value outside 1..max_days, rather than erroring - an out-of-range or
    typo'd argument should just show the usual default window, not fail.
    """
    remainder = content.strip()
    if remainder.lower().startswith(keyword.lower()):
        remainder = remainder[len(keyword):].strip()
    if not remainder:
        return default
    try:
        days = int(remainder)
    except ValueError:
        return default
    if 1 <= days <= max_days:
        return days
    return default


def window_label(days: int) -> str:
    """'24u' for the 1-day default, else '<N>d' (e.g. '7d')."""
    return "24u" if days == 1 else f"{days}d"


def chunk_top_list(header: str, lines: list[str], max_len: int) -> list[str]:
    """Greedily pack header+lines into chunks, each within max_len UTF-8 bytes."""
    chunks: list[str] = []
    current = header
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if current and len(candidate.encode("utf-8")) > max_len:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
