"""The schema of faction.json as Python classes: bootstrap_faction.py builds a Faction and writes Faction.to_json().

Field order is the JSON order and field names become camelCase keys (army_rule → "armyRule"). Fields made with
opt() / opt_list() are left out of the JSON when empty; the others are always written ("requires": [] included).
The app (js/data.js, js/rules.js) and tools/factions.py read the JSON as plain objects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields


def opt(default=None):
    return field(default=default, metadata={'omit': True})


def opt_list():
    return field(default_factory=list, metadata={'omit': True})


def camel(name):
    return re.sub(r'_(\w)', lambda m: m.group(1).upper(), name)


def dump(value):
    if isinstance(value, Json):
        return value.to_json()
    if isinstance(value, list):
        return [dump(v) for v in value]
    if isinstance(value, dict):
        return {k: dump(v) for k, v in value.items()}
    return value


class Json:
    def to_json(self):
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.metadata.get('omit') and value in (None, [], {}, False):
                continue
            out[camel(f.name)] = dump(value)
        return out


@dataclass
class Text(Json):
    """A game text: English from Wahapedia; Spanish only for the faction name (game texts: i18n.es.json)."""
    en: str
    es: str = opt()


@dataclass
class Item(Json):
    """A named entry listed inside an army rule (Astra Militarum Orders, "Daemonic Manifestation")."""
    name: Text
    text: Text


@dataclass
class Rule(Json):
    name: Text
    text: Text
    items: list[Item] = opt_list()


@dataclass
class Enhancement(Json):
    id: str
    requires: list[list[str]]       # alternatives, each a group of keyword words ([["INFANTRY", "OFFICER"]])
    name: Text
    text: Text                      # summary; the full text is in rules.json
    excludes: list[list[str]] = opt_list()
    grants_lead: list[str] = opt_list()  # datasheet ids the bearer can also be attached to
    type: str = opt()               # "upgrade": for a unit, not a CHARACTER


@dataclass
class UnitAbility(Json):
    """An ability a detachment gives automatically to a named datasheet, for extra points (Pantheon of Woe)."""
    id: str
    unit: str
    name: Text
    text: Text


@dataclass
class KeywordGrant(Json):
    """"WAR DOG units from your army have the BATTLELINE keyword"; chosen: only the units the player picks, up to max
    ("select three WAR DOG units … CHARACTER")."""
    keyword: str
    units: list[list[str]]
    chosen: bool = opt(False)
    max: int = opt()


@dataclass
class MinUnits(Json):
    """"Your army must include three or more WAR DOG units"."""
    units: list[list[str]]
    min: int


@dataclass
class Detachment(Json):
    id: str
    cost: int                       # detachment points
    tags: list[str] = opt_list()    # an army takes one detachment per tag
    name: Text = None
    rule: Rule = None
    enhancements: list[Enhancement] = field(default_factory=list)
    unit_abilities: list[UnitAbility] = opt_list()
    keyword_grants: list[KeywordGrant] = opt_list()
    min_units: list[MinUnits] = opt_list()


@dataclass
class Source(Json):
    """Which part of which Wahapedia page the faction is (see page_scope.py)."""
    faction: str
    chapter: str = opt()
    chapter_bit: str = opt()
    other_factions: list[str] = opt_list()


@dataclass
class ParentExcludes(Json):
    """Parent content a Chapter cannot use (see tools/factions.py)."""
    rules: list[str] = opt_list()
    detachments: list[str] = opt_list()
    units: list[str] = opt_list()
    unit_keywords: list[list[str]] = opt_list()

    def __bool__(self):
        return bool(self.rules or self.detachments or self.units or self.unit_keywords)


@dataclass
class KeywordRule(Json):
    """"The following friendly ADEPTUS ASTARTES units have DEATHWING: TERMINATOR units. …" (a Chapter's rule)."""
    keyword: str
    units: list[list[str]]


@dataclass
class Faction(Json):
    id: str
    name: Text
    source: str
    army_rule: Rule = opt()
    extra_rules: list[Rule] = opt_list()
    wahapedia: Source = opt()
    parent_excludes: ParentExcludes = opt()
    keyword_rules: list[KeywordRule] = opt_list()
    detachments: list[Detachment] = field(default_factory=list)
