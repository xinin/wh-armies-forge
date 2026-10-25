"""Audit imported datasheets against their Wahapedia pages (from the local cache) and report anything suspicious.

Usage:
    .venv/bin/python tools/audit_units.py astra-militarum [tyranids …]     (no argument = every faction)

For each unit it checks:
  weapons      every weapon profile row of the datasheet was imported
  abilities    every ability block (including wargear abilities) was imported
  composition  the model types add up to the unit size, for every size
  loadout      every "is equipped with" item resolved to a weapon (or is gear with a wargear ability)
  reachable    every weapon is in the default loadout or in a wargear option
  options      every wargear option became a selector (or is a known unsupported form)
  replaces     options only replace equipment the unit actually has
  data         stats, keywords, points and leader targets are present
Exit code 1 when there are errors (warnings don't fail).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wargear  # noqa: E402
from import_wahapedia_datasheets import BASE, parse, sections, slug  # noqa: E402
from wahapedia_fetch import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# option texts we know the app cannot model as a selector (shown as text in the datasheet)
UNSUPPORTED = []


def audit_unit(unit, faction, points, all_ids, excluded=frozenset()):
    errors, warns = [], []
    m = re.search(r'/([^/]+)$', unit.get('source', ''))
    if not m or 'wahapedia' not in unit.get('source', ''):
        return [f'not imported from Wahapedia (source: {unit.get("source", "hand-written")})'], []
    page = fetch(f'{BASE}/{faction}/{m.group(1)}')
    fresh, targets, costs, extra = parse(page, m.group(1))
    i = page.find('<div class="dsOuterFrame datasheet')
    block = page[i:page.find('<div class="ds2colKWFlat', i)]

    rows = len(re.findall(r'<tr class="dsWeaponRow">', block))
    profiles = sum(len(w['profiles']) for w in unit['weapons'])
    if rows != profiles:
        errors.append(f'weapons: datasheet has {rows} profile rows, imported {profiles}')

    abil_html = sections(block).get('ABILITIES', '')
    blocks = len(re.findall(r'<div class="dsAbility', abil_html))
    got = len(unit.get('abilities', [])) + len(unit.get('wargearAbilities', []))
    if blocks != got:
        warns.append(f'abilities: {blocks} ability blocks on the page, imported {got}')

    sizes = [s['models'] for s in unit['sizes']]
    alts = wargear.parse_composition(unit.get('composition', []))
    for n in sizes:
        tc = wargear.type_counts(alts, n)
        if sum(tc.values()) != n:
            errors.append(f'composition: cannot split {n} models into {unit.get("composition")}')

    weapon_ids = {w['id'] for w in unit['weapons']}
    gear_abilities = {slug(a['name']['en']) for a in unit.get('wargearAbilities', [])}
    base_items = {i for s in unit['sizes'] for i in s.get('loadout', {})}
    for item in sorted(base_items):
        if item.startswith('gear:') and item[5:] not in gear_abilities and not any(item[5:] in g or g in item[5:] for g in gear_abilities):
            warns.append(f'loadout: "{item[5:]}" is not a weapon of the datasheet (typo or gear without ability?)')
    if not base_items and unit.get('equipped') and not all(e.rstrip('.').lower().endswith('nothing') for e in unit['equipped']):
        errors.append('loadout: could not read the default equipment')

    option_items = {x['item'] for o in unit.get('wargear', []) for p in o.get('packages', {}).values() for x in p}
    for w in sorted(weapon_ids - base_items - option_items):
        errors.append(f'reachable: weapon "{w}" is neither default equipment nor a wargear choice')

    structured = len(unit.get('wargear', []))
    unit_copy = json.loads(json.dumps(fresh))
    unit_copy['sizes'] = [{'models': n} for n in sizes]
    unparsed = wargear.build(unit_copy, sizes)
    for t in unparsed:
        (warns if any(re.match(p, t) for p in UNSUPPORTED) else errors).append(f'options: not a selector: "{t[:110]}"')
    if structured + len(unparsed) != len(unit.get('wargearOptions', [])):
        warns.append(f'options: {len(unit.get("wargearOptions", []))} texts, {structured} selectors, {len(unparsed)} unparsed')

    produced = base_items | option_items
    for o in unit.get('wargear', []):
        for r in o.get('replaces', []):
            if r['item'] not in produced:
                errors.append(f'replaces: option "{o["label"]["en"]}" replaces "{r["item"]}", which the unit never has')

    if not unit.get('stats'):
        errors.append('data: no characteristics')
    if not unit.get('keywords'):
        errors.append('data: no keywords')
    if not points['units'].get(unit['id']):
        errors.append('data: no points')
    for t in targets:
        if slug(t) not in all_ids and slug(t) not in excluded:
            errors.append(f'data: leader target "{t}" is not a unit of the faction')
    return errors, warns


def main():
    factions = sys.argv[1:] or sorted(p.name for p in (ROOT / 'data' / 'factions').iterdir() if p.is_dir())
    total_e = total_w = 0
    for faction in factions:
        fdir = ROOT / 'data' / 'factions' / faction
        units_file = json.loads((fdir / 'units.json').read_text())
        units = units_file['units']
        excluded = set(units_file.get('excluded', {}).get('ids', []))
        points = json.loads((fdir / 'points.json').read_text())
        all_ids = {u['id'] for u in units}
        print(f'== {faction} ({len(units)} units)')
        for u in units:
            errors, warns = audit_unit(u, faction, points, all_ids, excluded)
            for e in errors:
                print(f'  ERROR {u["id"]}: {e}')
            for w in warns:
                print(f'  warn  {u["id"]}: {w}')
            total_e += len(errors)
            total_w += len(warns)
    print(f'\n{total_e} errors, {total_w} warnings')
    sys.exit(1 if total_e else 0)


if __name__ == '__main__':
    main()
