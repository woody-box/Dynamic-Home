"""Guard: every entity that uses a translation_key has a name in all locales.

Prevents shipping a switch/number whose friendly name falls back to the raw key
(the i18n drift this PR set out to fix).
"""

import json
import pathlib

import custom_components.dynamic_home as dh
from custom_components.dynamic_home import number, switch

_BASE = pathlib.Path(dh.__file__).parent
_FILES = [_BASE / "strings.json",
          _BASE / "translations" / "en.json",
          _BASE / "translations" / "es.json"]


def _names(path: pathlib.Path, platform: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("entity", {}).get(platform, {})


def test_switch_names_translated():
    keys = {d.key for grp in (switch._SHUTTER_SWITCHES, switch._VMC_SWITCHES,
                              switch._CLIMATE_SWITCHES) for d in grp}
    for path in _FILES:
        names = _names(path, "switch")
        missing = {k for k in keys if "name" not in names.get(k, {})}
        assert not missing, f"{path.name}: switch names missing {missing}"


def test_number_names_translated():
    keys = {d.key for grp in (number.THRESHOLDS, number._SHUTTER_NUMBERS,
                              number._VMC_NUMBERS) for d in grp}
    for path in _FILES:
        names = _names(path, "number")
        missing = {k for k in keys if "name" not in names.get(k, {})}
        assert not missing, f"{path.name}: number names missing {missing}"
