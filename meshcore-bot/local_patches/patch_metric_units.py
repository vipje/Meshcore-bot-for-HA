#!/usr/bin/env python3
"""Source patches hardcoding Celsius output where upstream hardcodes Fahrenheit.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics). Unlike wx/gwx, these
two spots have no [Weather] temperature_unit awareness at all - not a config
mismatch, upstream simply never made them unit-aware. This bot always runs in
Celsius, so these are straight permanent conversions rather than a new toggle.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


# 1. rain command's borderline rain/snow/ice temperature hint (the "34°F" in
#    "(est 0.2 in, 70%) 34°F") is hardcoded Fahrenheit end to end: converted
#    from the API's native Celsius in episode_probability_temp(), then
#    formatted with a literal "°F" and a 30-38°F threshold in _detail_suffix().
#    Keeping the `temp_f` name (rather than renaming it and its parameter
#    across every call site) to keep this a narrow, low-risk patch - it holds
#    a Celsius value from here on, hence the comment.
patch(
    "modules/commands/rain_command.py",
    """    prob_pct = int(round(prob)) if prob is not None else None
    temp_f = int(round(tc * 9 / 5 + 32)) if tc is not None else None
    return prob_pct, temp_f""",
    """    prob_pct = int(round(prob)) if prob is not None else None
    # Local patch: kept in Celsius (bot always runs in Celsius) - `temp_f`
    # is a misnomer left over from the original °F conversion, not renamed
    # everywhere to keep this patch narrow.
    temp_f = int(round(tc)) if tc is not None else None
    return prob_pct, temp_f""",
)
patch(
    "modules/commands/rain_command.py",
    '''        temp = f" {temp_f}°F" if (self.show_temp and temp_f is not None and 30 <= temp_f <= 38) else ""''',
    '''        # 30-38°F (the original borderline-freezing band) is about -1..3°C.
        temp = f" {temp_f}°C" if (self.show_temp and temp_f is not None and -1 <= temp_f <= 3) else ""''',
)

# 2. aqi command's Easter-egg replies for astronomical objects ("aqi mercury",
#    "aqi titan", ...) hardcode a few flavor-text temperatures in Fahrenheit.
#    Converted to Celsius (rounded) for consistency with the rest of the bot's
#    output - purely cosmetic, no config involved.
patch(
    "modules/commands/aqi_command.py",
    """AQI: Perfect, if you can survive 800°F temperature swings. ☿️""",
    """AQI: Perfect, if you can survive 427°C temperature swings. ☿️""",
)
patch(
    "modules/commands/aqi_command.py",
    """AQI: Breathable, but it's -290°F and rains liquid methane. 🪐""",
    """AQI: Breathable, but it's -179°C and rains liquid methane. 🪐""",
)
patch(
    "modules/commands/aqi_command.py",
    """AQI: Decent, but it's -220°F and you're in space. ❄️""",
    """AQI: Decent, but it's -140°C and you're in space. ❄️""",
)
patch(
    "modules/commands/aqi_command.py",
    """AQI: Good, but it's -390°F and you're in deep space. 🥶""",
    """AQI: Good, but it's -234°C and you're in deep space. 🥶""",
)
