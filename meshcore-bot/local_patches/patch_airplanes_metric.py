#!/usr/bin/env python3
"""Converts the airplanes command's user-facing units from nm/ft to km/m.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics).

The airplanes.live API itself is nm-native (its point-radius endpoint takes
nautical miles, and ADS-B altitude is reported in feet by convention) - that
part is left alone. Only what the user types (radius=) and configures
(default_radius) and what gets displayed (altitude, distance) is converted;
everywhere internal filtering/sorting already also has a `_distance_km` twin
of `_distance_nm` computed alongside it (see _filter_aircraft), so switching
display to km doesn't touch the nm-based radius filter/sort logic at all.

This command is disabled by default in this add-on (airplanes_enabled: false
in config.yaml) - converted proactively while it's off rather than left with
mismatched units for whenever it gets turned on.
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


FILE = "modules/commands/airplanes_command.py"

# 1. Help text for the 'radius=' argument.
patch(
    FILE,
    '''{"name": "radius", "description": "Search radius in nautical miles (default: 25)"},''',
    '''{"name": "radius", "description": "Search radius in kilometers (default: 46)"},''',
)

# 2. Web-viewer settings-panel metadata for default_radius.
patch(
    FILE,
    '''        {"key": "default_radius", "label": "Default radius", "type": "float",
         "min": 1, "max": 250, "default": 25, "unit": "nm",
         "help": "Default search radius in nautical miles (max 250)."},''',
    '''        {"key": "default_radius", "label": "Default radius", "type": "float",
         "min": 2, "max": 463, "default": 46, "unit": "km",
         "help": "Default search radius in kilometers (max ~463, the API's 250nm limit)."},''',
)

# 3. Config read: default_radius is now km; convert once to the nm the API call needs.
patch(
    FILE,
    """        self.default_radius = self.get_config_value('Airplanes_Command', 'default_radius', fallback=25, value_type='float')""",
    """        self.default_radius_km = self.get_config_value(
            'Airplanes_Command', 'default_radius', fallback=46, value_type='float'
        )
        # API's point-radius endpoint takes nautical miles; config/CLI arg is km.
        self.default_radius = self.default_radius_km * 0.539957""",
)

# 4. 'radius=N' argument: N is now km, converted to nm before the existing
#    1-250nm clamp (the API's own hard limit).
patch(
    FILE,
    """            # Radius
            if arg_lower.startswith('radius='):
                try:
                    filters['radius'] = float(arg_lower.split('=')[1])
                    filters['radius'] = min(250, max(1, filters['radius']))  # Clamp 1-250nm
                except (ValueError, IndexError):
                    pass""",
    """            # Radius (user types km; API's point-radius endpoint wants nm)
            if arg_lower.startswith('radius='):
                try:
                    radius_km = float(arg_lower.split('=')[1])
                    filters['radius'] = min(250, max(1, radius_km * 0.539957))  # Clamp 1-250nm (API limit)
                except (ValueError, IndexError):
                    pass""",
)

# 4b. 'alt=N[-M]' argument: displayed altitude is now meters (patch #5/#7), so
#     the filter input is too - converted to feet, the API's alt_baro/alt_geom
#     unit, before the min/max comparison in _filter_aircraft.
patch(
    FILE,
    """            # Altitude range
            elif arg_lower.startswith('alt='):
                try:
                    alt_str = arg_lower.split('=')[1]
                    if '-' in alt_str:
                        parts = alt_str.split('-')
                        filters['alt_min'] = float(parts[0])
                        filters['alt_max'] = float(parts[1])
                    else:
                        filters['alt_min'] = float(alt_str)
                except (ValueError, IndexError):
                    pass""",
    """            # Altitude range (user types meters; API altitude fields are feet)
            elif arg_lower.startswith('alt='):
                try:
                    alt_str = arg_lower.split('=')[1]
                    if '-' in alt_str:
                        parts = alt_str.split('-')
                        filters['alt_min'] = float(parts[0]) / 0.3048
                        filters['alt_max'] = float(parts[1]) / 0.3048
                    else:
                        filters['alt_min'] = float(alt_str) / 0.3048
                except (ValueError, IndexError):
                    pass""",
)

# 4c. 'speed=N[-M]' argument: displayed speed is now km/h (patch #5b/#7b), so
#     the filter input is too - converted to knots, the API's `gs` field unit.
patch(
    FILE,
    """            # Speed range
            elif arg_lower.startswith('speed='):
                try:
                    speed_str = arg_lower.split('=')[1]
                    if '-' in speed_str:
                        parts = speed_str.split('-')
                        filters['speed_min'] = float(parts[0])
                        filters['speed_max'] = float(parts[1])
                    else:
                        filters['speed_min'] = float(speed_str)
                except (ValueError, IndexError):
                    pass""",
    """            # Speed range (user types km/h; API's `gs` field is knots)
            elif arg_lower.startswith('speed='):
                try:
                    speed_str = arg_lower.split('=')[1]
                    if '-' in speed_str:
                        parts = speed_str.split('-')
                        filters['speed_min'] = float(parts[0]) / 1.852
                        filters['speed_max'] = float(parts[1]) / 1.852
                    else:
                        filters['speed_min'] = float(speed_str) / 1.852
                except (ValueError, IndexError):
                    pass""",
)

# 5. Single-aircraft detail view: altitude ft -> m.
patch(
    FILE,
    """            alt_str = f"{int(alt):,}ft"  # Add comma separator for readability""",
    """            alt_str = f"{int(alt * 0.3048):,}m"  # Add comma separator for readability (feet -> meters)""",
)

# 5b. Single-aircraft detail view: speed kt -> km/h. `gs` (ground speed) comes
#     from the API in knots, same aviation-convention field as altitude.
patch(
    FILE,
    '''        # Speed
        gs = aircraft.get('gs')
        speed_str = f"{int(gs)}kt" if gs is not None else "N/A"''',
    '''        # Speed
        gs = aircraft.get('gs')
        speed_str = f"{int(gs * 1.852)}km/h" if gs is not None else "N/A"''',
)

# 6. Single-aircraft detail view: distance nm -> km.
patch(
    FILE,
    """        # Distance and bearing (most important for overhead command - put first)
        distance_nm = aircraft.get('_distance_nm', 0)
        bearing_cardinal = aircraft.get('_bearing_cardinal', 'N')""",
    """        # Distance and bearing (most important for overhead command - put first)
        distance_km = aircraft.get('_distance_km', 0)
        bearing_cardinal = aircraft.get('_bearing_cardinal', 'N')""",
)
patch(
    FILE,
    '''        response_parts.append(f"{distance_nm:.1f}nm {bearing_cardinal}")''',
    '''        response_parts.append(f"{distance_km:.1f}km {bearing_cardinal}")''',
)

# 7. Aircraft-list view: altitude ft -> m.
patch(
    FILE,
    "                alt_str = f\"{int(alt)}ft\"",
    "                alt_str = f\"{int(alt * 0.3048)}m\"",
)

# 7b. Aircraft-list view: speed kt -> km/h.
patch(
    FILE,
    '''            gs = aircraft.get('gs')
            speed_str = f"{int(gs)}kt" if gs is not None else "N/A"''',
    '''            gs = aircraft.get('gs')
            speed_str = f"{int(gs * 1.852)}km/h" if gs is not None else "N/A"''',
)

# 8. Aircraft-list view: distance nm -> km.
patch(
    FILE,
    """            distance_nm = aircraft.get('_distance_nm', 0)
            bearing_cardinal = aircraft.get('_bearing_cardinal', 'N')

            line = f"{callsign} {alt_str} {speed_str} {distance_nm:.1f}nm {bearing_cardinal}\"""",
    """            distance_km = aircraft.get('_distance_km', 0)
            bearing_cardinal = aircraft.get('_bearing_cardinal', 'N')

            line = f"{callsign} {alt_str} {speed_str} {distance_km:.1f}km {bearing_cardinal}\"""",
)
