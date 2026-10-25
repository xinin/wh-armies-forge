"""Import datasheets from Wahapedia (11th edition) into a faction's units.json / points.json.

Usage:
    python3 tools/import_wahapedia_datasheets.py astra-militarum Lord-Marshal-Dreir Centaur-RSV ...
    python3 tools/import_wahapedia_datasheets.py astra-militarum --all          (every non-Legends/FW datasheet)
    python3 tools/import_wahapedia_datasheets.py astra-militarum --list         (show the classification only; fetches every page)
    python3 tools/import_wahapedia_datasheets.py astra-militarum X --html-dir saved_pages/   (uses <slug>.html files)

Adds or updates only the given datasheets. Kept from an existing entry: Spanish name, bodyguard, notes.
Points: the first cost tier goes to points.json "units"; the 3rd+ copy tier (11th edition) to "unitsExtraCopies".
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_datasheets import ROOT, gen_wargear, role_of, slug, title  # noqa: E402

BASE = 'https://wahapedia.ru/wh40k11ed/factions'


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (army-forge importer)'})
    return urllib.request.urlopen(req).read().decode('utf-8')


def text(x):
    x = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', x, flags=re.S)
    x = re.sub(r'<br\s*/?>', '\n', x)
    x = re.sub(r'</(p|div|tr|li|ul)>', '\n', x)
    x = re.sub(r'<[^>]+>', '', x)
    x = html.unescape(x).replace('‑', '-')
    x = re.sub(r'[ \t]+', ' ', x)
    return re.sub(r'\s*\n\s*', '\n', x).strip()


def sections(block):
    """Split the right/left columns by their green headers: {'ABILITIES': html, 'UNIT COMPOSITION': html, ...}"""
    parts = re.split(r'<div class="dsHeader[^"]*">(?:<span[^>]*></span>)?(.*?)</div>', block)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out.setdefault(text(parts[i]).upper(), parts[i + 1])
    return out


def parse_abilities(html_part):
    named, wargear = [], []
    for m in re.finditer(r'<div class="dsAbility( dsWargearAbility)?[^"]*">(.*?)</div>(?=\s*<div class="ds|\s*$)', html_part, re.S):
        t = text(m.group(2))
        mm = re.match(r'^([^:\n]{2,70}):\s*(.*)$', t, re.S)
        if not mm:
            continue
        item = {'name': {'en': mm.group(1).strip()}, 'text': {'en': re.sub(r'\s*\n\s*', ' ', mm.group(2)).strip()}}
        (wargear if m.group(1) or 'dsWargearAbilityText' in m.group(2) else named).append(item)
    return named, wargear


def parse(page, ds_slug):
    i = page.find('<div class="dsOuterFrame datasheet')
    end = page.find('<div class="ds2colKWFlat', i)
    block = page[i:end]
    kw_start = page.find('KEYWORDS:', end)
    kw_block = page[kw_start:page.find('</div>', kw_start)]

    name = text(re.search(r'<div class="dsH2Header"><div>(.*?)</div>', block, re.S).group(1))

    # characteristics: name/value pairs in order; every "M" starts a new model profile
    prof_area = block[block.find('dsProfileBaseWrap'):block.find('<div class="ds2col">')]
    stats = []
    for item in re.finditer(r'class="(dsCharName|dsCharValue[^"]*|dsModelName[^"]*)"[^>]*>(.*?)</div>', prof_area, re.S):
        kind, val = item.group(1), text(item.group(2))
        if kind == 'dsCharName':
            if val == 'M':
                stats.append({})
            key = val
        elif kind.startswith('dsCharValue') and stats:
            stats[-1][{'SV': 'Sv', 'LD': 'Ld'}.get(key, key)] = val
        elif kind.startswith('dsModelName') and stats:
            stats[-1]['name'] = {'en': title(val)}
    stats = [st for st in stats if 'M' in st]
    inv = re.search(r'class="dsCharInvulValue[^"]*">(.*?)</div>', block, re.S)
    if inv:
        for st in stats:
            st['inv'] = text(inv.group(1))

    # weapons: rows after the RANGED / MELEE headers
    weapons = {}
    melee_at = block.find('MELEE WEAPONS')
    for m in re.finditer(r'<tr class="dsWeaponRow">(.*?)</tr>', block, re.S):
        row = m.group(1)
        wname = text(re.search(r'<b class="dsWeaponName">(.*?)</b>', row, re.S).group(1))
        # each weapon ability is one tooltip group whose words are separate spans ("anti-infantry" "4+")
        kws = [title(' '.join(text(w) for w in re.findall(r'<span class="ttw kwbu">(.*?)</span>', grp)))
               for grp in re.findall(r'<span class="tooltip[^"]*"[^>]*>((?:\s*<span class="ttw kwbu">[^<]*</span>)+)\s*</span>', row)]
        vals = [text(v) for v in re.findall(r'<div class="ct[^"]*">(.*?)</div>', row)]
        if len(vals) < 6:
            continue
        mm = re.match(r'^(.*?) [–-] (.*)$', wname)
        base, mode = (mm.group(1).strip(), mm.group(2).strip()) if mm else (wname, '')
        kind = 'melee' if melee_at != -1 and m.start() > melee_at else 'ranged'
        wid = slug(base)
        # a weapon with both a ranged and a melee profile (e.g. guardian spear) gets two entries
        if wid in weapons and weapons[wid]['type'] != kind:
            wid = f'{wid}-{kind}'
        w = weapons.setdefault(wid, {'id': wid, 'name': {'en': base}, 'type': kind, 'profiles': []})
        p = {'range': vals[0], 'A': vals[1], 'skill': vals[2], 'S': vals[3], 'AP': vals[4], 'D': vals[5], 'keywords': kws}
        if mode:
            p['mode'] = {'en': mode}
        w['profiles'].append(p)

    core, faction = [], []
    for label, value in re.findall(r'<td class="dsCoreArmyLabel[^"]*">(.*?)</td><td class="dsCoreArmyValue">(.*?)</td>', block, re.S):
        items = [x.strip() for x in text(value).split(',') if x.strip()]
        (core if 'CORE' in text(label).upper() else faction).extend(items)

    sec = sections(block)
    named, wargear_ab = parse_abilities(sec.get('ABILITIES', ''))

    # wargear options (nested lists → {text, choices})
    opts = []
    wl = re.search(r'<div class="dsWargearOptionsList">(.*?)</div>', block, re.S)
    if wl:
        top = re.sub(r'<ul style="list-style-type:circle">(.*?)</ul>', lambda m: '§' + '§'.join(text(x) for x in re.findall(r'<li>(.*?)</li>', m.group(1), re.S)), wl.group(1), flags=re.S)
        for li in re.findall(r'<li>(.*?)</li>', top, re.S):
            parts = li.split('§')
            t = text(parts[0])
            if t and not t.lower().startswith('none'):
                opts.append({'text': re.sub(r'\s+', ' ', t), 'choices': [p.strip() for p in parts[1:] if p.strip()]})

    comp_html = sec.get('UNIT COMPOSITION', '')
    composition = [text(x) for x in re.findall(r'<li>(.*?)</li>', comp_html, re.S)]
    comp_text = text(re.sub(r'<table.*?</table>', '', comp_html, flags=re.S))
    equipped = [re.sub(r'\s+', ' ', e).strip() for e in re.findall(r'([^.\n]*equipped with:[^.]*\.)', comp_text)]
    attach = next((re.sub(r'\s+', ' ', s).strip() + '.' for s in comp_text.split('.') if 'Leader unit' in s and 'attached' in s), None)

    costs, extra, tier = [], [], 0
    for row in re.findall(r'<tr>(.*?)</tr>', comp_html, re.S):
        if 'dsUnitCostHeader' in row:
            tier += 1
            continue
        mm = re.search(r'<td>(?:\d+-)?(\d+) models?</td><td><div class="PriceTag">\s*(\d+)\s*</div>', row)
        if mm:
            (costs if tier <= 1 else extra).append({'models': int(mm.group(1)), 'points': int(mm.group(2))})

    leader_text = text(sec.get('LEADER', ''))
    leader_targets = [l for l in leader_text.split('\n')[1:] if l.isupper() or l.istitle()]
    orders_text = re.sub(r'\s+', ' ', text(re.split(r'<table class="dsCoreArmy', sec.get('ORDERS', ''))[0])).strip()
    transport = re.sub(r'\s+', ' ', text(sec.get('TRANSPORT', ''))).strip()
    damaged_key = next((k for k in sec if k.startswith('DAMAGED')), None)

    kw_text = text(kw_block)
    km = re.search(r'KEYWORDS:\s*(.*?)\n', kw_text + '\n')
    keywords = [k.strip().upper() for k in re.split(r'[;,]', km.group(1)) if k.strip()] if km else []

    loadout = []
    known = set(weapons)
    for sent in equipped:
        for item in sent.split(':', 1)[1].strip(' .').split(';'):
            sid = slug(re.sub(r'^\d+\s+', '', item.strip()))
            for cand in (sid, sid[:-1] if sid.endswith('s') else sid):
                if cand in known and cand not in loadout:
                    loadout.append(cand)
                    for twin in (f'{cand}-melee', f'{cand}-ranged'):
                        if twin in known and twin not in loadout:
                            loadout.append(twin)
                    break

    unit = {
        'id': slug(name), 'name': {'en': name}, 'keywords': keywords, 'stats': stats,
        'weapons': list(weapons.values()), 'loadout': loadout, 'abilities': named,
        'core': core, 'factionAbilities': faction, 'source': f'wahapedia.ru/wh40k11ed/factions/.../{ds_slug}',
    }
    if wargear_ab: unit['wargearAbilities'] = wargear_ab
    if damaged_key:
        unit['damaged'] = {'name': {'en': damaged_key.replace('DAMAGED:', '').strip().capitalize()},
                           'text': {'en': re.sub(r'\s+', ' ', text(sec[damaged_key]))}}
    if orders_text:
        unit['ordersText'] = {'en': orders_text}
        mm = re.search(r'issue (?:up to )?(\d+) Orders?', orders_text)
        if mm: unit['orders'] = int(mm.group(1))
    if opts: unit['wargearOptions'] = opts
    if composition: unit['composition'] = composition
    if equipped: unit['equipped'] = equipped
    if attach:
        unit['attachRule'] = attach
        bg = {}
        if 'up to two Leader units' in attach: bg['maxLeaders'] = 2
        mm = re.search(r'no more than one of those units is an? ([A-Za-z ]+?) unit', attach)
        if mm: bg['maxWithKeyword'] = {mm.group(1).upper(): 1}
        if bg: unit['bodyguard'] = bg
    if transport: unit['transport'] = {'en': transport}
    return unit, leader_targets, costs, extra


def datasheet_links(faction_page, faction):
    """Every datasheet linked from the faction page (the keyword lists alone miss some units)."""
    return sorted(set(re.findall(rf'href="/wh40k11ed/factions/{faction}/([A-Za-z0-9][A-Za-z0-9-]*)"', faction_page)))


def source_tag(page):
    """'legends' / 'fw' / 'core', from the logo title of the datasheet ("App. X (Warhammer Legends) ...")."""
    i = page.find('<div class="dsOuterFrame datasheet')
    titles = ' '.join(re.findall(r'<img class="tooltip logo3" title="([^"]+)"', page[i:i + 5000]))
    if 'Legends' in titles:
        return 'legends'
    if 'Forge World' in titles:
        return 'fw'
    return 'core'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('faction')
    ap.add_argument('datasheets', nargs='*', help='Wahapedia datasheet slugs, e.g. Lord-Marshal-Dreir')
    ap.add_argument('--all', action='store_true', help='import every datasheet that is not Legends / Forge World')
    ap.add_argument('--list', action='store_true', help='only print the core / legends / fw classification')
    ap.add_argument('--html-dir')
    args = ap.parse_args()

    pages = {}  # slug → html, fetched once
    not_core = []
    if args.all or args.list:
        slugs = datasheet_links(fetch(f'{BASE}/{args.faction}/'), args.faction)
        tags = {'core': [], 'legends': [], 'fw': []}
        for ds in slugs:
            pages[ds] = fetch(f'{BASE}/{args.faction}/{ds}')
            time.sleep(0.5)  # be gentle with Wahapedia
            if '<div class="dsOuterFrame datasheet' not in pages[ds]:
                continue  # not a datasheet page
            tags[source_tag(pages[ds])].append(ds)
        for tag, names in tags.items():
            print(f'{tag.upper()} ({len(names)}): {", ".join(names)}')
        if args.list:
            return
        args.datasheets = tags['core']
        not_core = [slug(ds) for ds in tags['legends'] + tags['fw']]
    if not args.datasheets:
        ap.error('give datasheet slugs or --all')

    fdir = ROOT / 'data' / 'factions' / args.faction
    units_file = json.loads((fdir / 'units.json').read_text())
    points = json.loads((fdir / 'points.json').read_text())
    global_weapons = json.loads((fdir / 'weapons.json').read_text())['weapons']
    existing = {u['id']: u for u in units_file['units']}
    if not_core:
        ex = units_file.setdefault('excluded', {'_note': 'Forge World and Warhammer Legends datasheets: never imported.', 'ids': []})
        ex['ids'] = sorted(set(ex['ids']) | set(not_core))
    excluded = set(units_file.get('excluded', {}).get('ids', []))

    parsed = []
    for ds in args.datasheets:
        if ds in pages:
            page = pages[ds]
        elif args.html_dir:
            page = (Path(args.html_dir) / f'{ds}.html').read_text()
        else:
            page = fetch(f'{BASE}/{args.faction}/{ds}')
            time.sleep(0.5)  # be gentle with Wahapedia
        try:
            unit, targets, costs, extra = parse(page, ds)
        except (AttributeError, ValueError) as e:
            print(f'skip {ds}: could not parse ({e})', file=sys.stderr)
            continue
        if unit['id'] in excluded:
            print(f'skip {unit["id"]} (excluded)')
            continue
        parsed.append((unit, targets, costs, extra))

    by_name = {slug(u['name']['en']): u['id'] for u in existing.values()}
    # 11th-edition datasheet names that differ from the ids we already use
    by_name.update({'death-riders': 'death-rider-squadron', 'militarum-tempestus-command-squad': 'tempestus-command-squad',
                    'cadian-heavy-weapons-squad': 'heavy-weapons-squad', 'ratlings': 'ratlings'})
    by_name.update({slug(u['name']['en']): u['id'] for u, *_ in parsed})
    for unit, targets, costs, extra in parsed:
        old = existing.get(unit['id'], {})
        unit['role'] = role_of(unit['keywords'])
        unit['name']['es'] = old.get('name', {}).get('es', unit['name']['en'])
        lead = [by_name.get(slug(t)) for t in targets]
        if any(lead):
            unit['leader'] = {'canLead': [x for x in lead if x]}
        for key in ('bodyguard', 'notes'):
            if key in old: unit[key] = old[key]
        wargear = gen_wargear(unit, global_weapons)
        if wargear: unit['wargear'] = wargear
        if costs:
            points['units'][unit['id']] = costs
            points.setdefault('verified', [])
            if unit['id'] not in points['verified']: points['verified'].append(unit['id'])
        if extra:
            points.setdefault('unitsExtraCopies', {})[unit['id']] = extra
        unit['sizes'] = [{'models': c['models']} for c in costs] or old.get('sizes') or [{'models': 1}]
        existing[unit['id']] = {**unit}
        print(f"{unit['id']:30} {unit['role']:10} stats={len(unit['stats'])} weapons={len(unit['weapons'])} "
              f"wargear={len(wargear)}/{len(unit.get('wargearOptions', []))} lead={unit.get('leader', {}).get('canLead')} pts={costs} 3rd+={extra}")

    order = ['character', 'battleline', 'infantry', 'mounted', 'monster', 'vehicle', 'transport', 'aircraft', 'titanic', 'fortification']
    units_file['units'] = sorted(existing.values(), key=lambda u: (order.index(u['role']) if u['role'] in order else 99, u['name']['en']))
    (fdir / 'units.json').write_text(json.dumps(units_file, ensure_ascii=False, indent=1) + '\n')
    (fdir / 'points.json').write_text(json.dumps(points, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
