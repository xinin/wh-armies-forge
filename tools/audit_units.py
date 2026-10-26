"""Audit imported datasheets against their Wahapedia pages (from the local cache) and report anything suspicious.

Usage:
    .venv/bin/python tools/audit_units.py astra-militarum [tyranids …]     (no argument = every faction)

For each unit it checks:
  weapons      every weapon profile row of the datasheet was imported
  abilities    every ability block (including wargear abilities) was imported
  composition  the model types add up to the unit size, for every size
  loadout      every "is equipped with" item resolved to a weapon (or is gear with a wargear ability)
  reachable    every weapon is in the default loadout or in a wargear option
  options      every wargear option became a selector (or is a known unsupported form), and the equipment it
               gives is a weapon or has a wargear ability
  costs        every "per <wargear>" cost is for something the unit can carry
  replaces     options only replace equipment the unit actually has
  data         stats, keywords, points and leader targets are present
and that the unit/detachment counts in data/factions/index.json (shown by the faction picker) match.
Exit code 1 when there are errors (warnings don't fail).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factions as fx  # noqa: E402
import wargear  # noqa: E402
from import_wahapedia_datasheets import BASE, only_chapter, parse, sections, slug  # noqa: E402
from wahapedia_fetch import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# option texts we know the app cannot model as a selector (shown as text in the datasheet)
UNSUPPORTED = []


def audit_unit(unit, faction, points, all_ids, excluded=frozenset()):
    errors, warns = [], []
    m = re.search(r'/([^/]+)$', unit.get('source', ''))
    if not m or 'wahapedia' not in unit.get('source', ''):
        return [f'not imported from Wahapedia (source: {unit.get("source", "hand-written")})'], []
    cfg = json.loads((ROOT / 'data' / 'factions' / faction / 'faction.json').read_text()).get('wahapedia', {})
    bit = int(cfg['chapterBit'], 16) if cfg.get('chapterBit') else None
    page = only_chapter(fetch(f'{BASE}/{cfg.get("faction", faction)}/{m.group(1)}'), bit)
    fresh, targets, costs, extra, _ = parse(page, m.group(1))
    i = page.find('<div class="dsOuterFrame datasheet')
    block = page[i:page.find('<div class="ds2colKWFlat', i)]

    rows = len(re.findall(r'<tr class="dsWeaponRow">', block))
    profiles = sum(len(w['profiles']) for w in unit['weapons'] if 'gear' not in w)  # faction drones are not on the page
    if rows != profiles:
        errors.append(f'weapons: datasheet has {rows} profile rows, imported {profiles}')

    abil_html = sections(block).get('ABILITIES', '')
    blocks = len(re.findall(r'<div class="dsAbility', abil_html))
    got = len(unit.get('abilities', [])) + len([a for a in unit.get('wargearAbilities', []) if not a.get('faction')])
    if blocks != got:
        warns.append(f'abilities: {blocks} ability blocks on the page, imported {got}')

    sizes = [s['models'] for s in unit['sizes']]
    alts = wargear.parse_composition(unit.get('composition', []))
    for n in sizes:
        tc = wargear.type_counts(alts, n)
        if sum(tc.values()) != n:
            errors.append(f'composition: cannot split {n} models into {unit.get("composition")}')

    weapon_ids = {w['id'] for w in unit['weapons']}
    gear_abilities = {slug(a['name']['en']) for a in unit.get('wargearAbilities', []) + unit.get('abilities', [])}
    gear_ids = {wargear.gear_id(a['name']['en']) for a in unit.get('wargearAbilities', [])}
    base_items = {i for s in unit['sizes'] for i in s.get('loadout', {})}
    for item in sorted(base_items):
        if item.startswith('gear:') and item[5:] not in gear_abilities and not any(item[5:] in g or g in item[5:] for g in gear_abilities):
            warns.append(f'loadout: "{item[5:]}" is not a weapon of the datasheet (typo or gear without ability?)')
    if not base_items and unit.get('equipped') and not all(e.rstrip('.').lower().endswith('nothing') for e in unit['equipped']):
        errors.append('loadout: could not read the default equipment')

    option_items = {x['item'] for o in unit.get('wargear', []) for p in o.get('packages', {}).values() for x in p}
    granted = {x['item'] for g, ws in unit.get('gearWeapons', {}).items() if g in base_items | option_items for x in ws} | \
              {x['item'] for x in unit.get('abilityWeapons', [])}
    for w in sorted(weapon_ids - base_items - option_items - granted):
        errors.append(f'reachable: weapon "{w}" is neither default equipment nor a wargear choice')

    structured = len(unit.get('wargear', []))
    unit_copy = json.loads(json.dumps(fresh))
    unit_copy['sizes'] = [{'models': c['models']} for c in costs] or [{'models': n} for n in sizes]
    unparsed = wargear.build(unit_copy, [s['models'] for s in unit_copy['sizes']])
    for t in unparsed:
        (warns if any(re.match(p, t) for p in UNSUPPORTED) else errors).append(f'options: not a selector: "{t[:110]}"')
    if structured != len(unit_copy['wargear']):
        warns.append(f'options: {structured} selectors saved, the datasheet gives {len(unit_copy["wargear"])} (re-import?)')

    for item in sorted(i for i in option_items - base_items if i.startswith('gear:') and i not in gear_ids):
        warns.append(f'options: "{item[5:]}" is neither a weapon nor wargear with an ability (misread option?)')
    for item in points.get('wargearCosts', {}).get(unit['id'], {}):
        if item not in base_items | option_items:
            errors.append(f'costs: "{item}" has a points cost but the unit can never carry it')

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
    if targets and not unit.get('leader'):
        errors.append('data: the datasheet has Leader/Support targets but the unit has none')
    for t, legends in targets:
        if slug(t) not in all_ids and slug(t) not in excluded and not legends:
            errors.append(f'data: leader target "{t}" is not a unit of the faction')
    return errors, warns


def main():
    index = {f['id']: f for f in fx.index()}
    total_e = total_w = 0
    for faction in sys.argv[1:] or list(index):
        fdir = ROOT / 'data' / 'factions' / faction
        units_file = json.loads((fdir / 'units.json').read_text())
        units = units_file['units']  # a Chapter's own datasheets (the parent's are audited with the parent)
        excluded = set(units_file.get('excluded', {}).get('ids', []))
        merged = fx.load(faction)
        points = merged['points']
        all_ids = {u['id'] for u in merged['units']}
        parent = index[faction].get('parent')
        if parent:  # generic datasheets the Chapter cannot use are not missing leader targets
            excluded |= {u['id'] for u in fx.raw(parent)['units']} - all_ids
        print(f'== {faction} ({len(units)} units)')
        # the faction picker shows these counts from index.json
        counts = (len(merged['units']), len(merged['faction']['detachments']))
        entry = index.get(faction, {})
        if not parent and entry.get('alliance') not in ('imperium', 'chaos', 'xenos'):
            print('  ERROR index.json: no "alliance" (imperium/chaos/xenos) for the faction picker')
            total_e += 1
        if (entry.get('units'), entry.get('detachments')) != counts:
            print(f'  ERROR index.json: {entry.get("units")} units / {entry.get("detachments")} detachments, '
                  f'the faction has {counts[0]} / {counts[1]}')
            total_e += 1
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
