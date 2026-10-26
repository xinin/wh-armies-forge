"""Import datasheets from Wahapedia (11th edition) into a faction's units.json / points.json.

Usage:
    python3 tools/import_wahapedia_datasheets.py astra-militarum Lord-Marshal-Dreir Centaur-RSV ...
    python3 tools/import_wahapedia_datasheets.py astra-militarum --all          (every non-Legends/FW datasheet)
    python3 tools/import_wahapedia_datasheets.py astra-militarum --list         (show the classification only; fetches every page)
    python3 tools/import_wahapedia_datasheets.py astra-militarum X --html-dir saved_pages/   (uses <slug>.html files)
    python3 tools/import_wahapedia_datasheets.py astra-militarum --all --check  (writes nothing: lists what would change)

Adds or updates only the given datasheets. Kept from an existing entry: Spanish name, bodyguard, notes.
Points: the first cost tier goes to points.json "units"; the 3rd+ copy tier (11th edition) to "unitsExtraCopies";
"per <wargear>" costs to "wargearCosts" ({unit: {item: points}}, charged for every piece the unit carries).
Faction-wide wargear (T'au drones, from the faction page) is copied into the units that can take it.
Wargear (model counts, default loadout, options) is built by tools/wargear.py. With --all, units that are no
longer datasheets of the faction are removed. Run tools/audit_units.py afterwards.
Chapters (index.json "parent", see tools/factions.py): the generic datasheets are read with the Chapter's bit too,
and only those that come out different from the parent's (points, units they can lead) are kept, as overrides.
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_datasheets import ROOT, role_of, slug, title  # noqa: E402
import wargear  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
import wahapedia_fetch  # noqa: E402
from wahapedia_fetch import fetch  # noqa: E402
import factions  # noqa: E402

BASE = 'https://wahapedia.ru/wh40k11ed/factions'


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
    """Ability blocks → (named, wargear). Each block runs until the next dsAbility div (they contain nested divs)."""
    named, wargear_ab = [], []
    for chunk in re.split(r'(?=<div class="dsAbility)', html_part):
        if not chunk.startswith('<div class="dsAbility'):
            continue
        t = text(chunk)
        mm = re.match(r'^([^:\n]{2,70}):\s*(.*)$', t, re.S)
        if not mm:
            continue
        item = {'name': {'en': mm.group(1).strip()}, 'text': {'en': re.sub(r'\s+', ' ', mm.group(2)).strip()}}
        (wargear_ab if 'dsWargearAbility' in chunk[:120] else named).append(item)
    return named, wargear_ab


class _OptionList(HTMLParser):
    """<ul><li>text<ul><li>choice</li>…</ul></li>…</ul> → [{'text', 'choices'}] (any nested <ul> markup)."""
    def __init__(self):
        super().__init__()
        self.depth, self.items, self.buf = 0, [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'ul':
            self.depth += 1
        elif tag == 'li':
            if self.depth == 1:
                self.items.append({'text': '', 'choices': []})
                self.buf = 'text'
            elif self.depth >= 2 and self.items:
                self.items[-1]['choices'].append('')
                self.buf = 'choice'
        elif tag == 'br' and self.buf == 'text' and self.items:
            self.items[-1]['text'] += ' '

    def handle_endtag(self, tag):
        if tag == 'ul':
            self.depth -= 1
            self.buf = 'text' if self.depth == 1 else None
        elif tag == 'li' and self.depth >= 2:
            self.buf = 'text'

    def handle_data(self, data):
        if not self.items or not self.buf:
            return
        if self.buf == 'choice' and self.depth >= 2:
            self.items[-1]['choices'][-1] += data
        elif self.depth == 1:
            self.items[-1]['text'] += data


def parse_option_list(html_part):
    p = _OptionList()
    p.feed(html_part)
    out = []
    for it in p.items:
        t = re.sub(r'\s+', ' ', it['text']).strip()
        if t and not t.lower().startswith('none'):
            out.append({'text': t.replace('\u2011', '-'),
                        'choices': [re.sub(r'\s+', ' ', c).strip().replace('\u2011', '-') for c in it['choices'] if c.strip()]})
    return out


def parse_weapons(block):
    """Weapon profiles of a weapon table: rows after the RANGED / MELEE headers → {id: weapon}."""
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
    return weapons


def faction_wargear(faction_page):
    """Wargear shared by the whole faction, listed on the faction page (T'au "Drones": guardian, gun, marker,
    missile and shield drone) → {gear id: {name, text, weapons}}."""
    i = faction_page.find('id="Drones"')
    if i < 0:
        return {}
    sec = faction_page[i:faction_page.find('<h2', i + 10)]
    out = {}
    for block in re.split(r'<div class="BreakInsideAvoid">', sec)[1:]:
        nm = re.search(r'class="impact18 underl">(.*?)</p>', block, re.S)
        if not nm:
            continue
        name = title(text(nm.group(1)))
        body = re.sub(r'<p class="ShowFluff.*?</p>|<p[^>]*class="impact18 underl">.*?</p>', '', block, flags=re.S)
        body = re.sub(r'<table class="wTable.*?</table>', '', body, flags=re.S)
        rule = re.sub(r'\s+', ' ', text(body)).strip()
        weapons = list(parse_weapons(block).values())
        if rule.endswith(':') and weapons:  # "… the following ranged weapon:" + its table → name it
            rule += ' ' + ', '.join(w['name']['en'] for w in weapons) + '.'
        out[wargear.gear_id(name)] = {'name': {'en': name}, 'text': {'en': rule}, 'weapons': weapons}
    return out


def faction_keywords(page):
    """FACTION KEYWORDS of a datasheet page: {'ADEPTUS ASTARTES', 'SPACE WOLVES'}"""
    i = page.find('<div class="dsRight', page.find('<div class="ds2colKWFlat'))
    t = text(page[i:page.find('</div>', page.find('FACTION KEYWORDS', i))]).replace('FACTION KEYWORDS:', '')
    return {k.strip().upper() for k in re.split(r'[;,\n]', t) if k.strip()}


def only_chapter(page, chapter_bit):
    """Drop the rows a Space Marine datasheet shows only for other Chapters (data-f="CH:<hex mask>": unit costs,
    leader targets)."""
    if chapter_bit is None:
        return page
    def keep(m):
        return m.group(0) if int(m.group(2), 16) & chapter_bit else ''
    return re.sub(r'<(tr|li) class="clFlCH" data-f="CH:([0-9a-f]+)[^"]*">.*?</\1>', keep, page, flags=re.S)


def parse(page, ds_slug, chapter_bit=None):
    page = only_chapter(page, chapter_bit)
    i = page.find('<div class="dsOuterFrame datasheet')
    end = page.find('<div class="ds2colKWFlat', i)
    block = page[i:end]
    # left keyword column: "KEYWORDS: A; B" or, with per-model keywords,
    # "KEYWORDS – ALL MODELS: A; B | TEMPESTOR PRIME: CHARACTER; OFFICER" (the unit gets all of them)
    kw_block = page[end:page.find('<div class="dsRight', end)].replace('<span class="dsVertLine"></span>', '\n')

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

    weapons = parse_weapons(block)

    core, faction = [], []
    for label, value in re.findall(r'<td class="dsCoreArmyLabel[^"]*">(.*?)</td><td class="dsCoreArmyValue">(.*?)</td>', block, re.S):
        items = [x.strip() for x in text(value).split(',') if x.strip()]
        (core if 'CORE' in text(label).upper() else faction).extend(items)

    sec = sections(block)
    named, wargear_ab = parse_abilities(sec.get('ABILITIES', ''))

    wl = re.search(r'<div class="dsWargearOptionsList">(.*?)</div>', block, re.S)
    opts = parse_option_list(wl.group(1)) if wl else []
    notes = [re.sub(r'\s+', ' ', text(n)).strip() for n in re.findall(r'<div class="dsOptionsComment">(.*?)</div>', block, re.S)]

    comp_html = sec.get('UNIT COMPOSITION', '')
    composition = [text(x) for x in re.findall(r'<li>(.*?)</li>', comp_html, re.S)]
    comp_text = text(re.sub(r'<table.*?</table>', '', comp_html, flags=re.S))
    comp_text = re.sub(r'([;:])\s*\n\s*', r'\1 ', comp_text)  # item lists broken by <br> after "x;" or "with:"
    equipped = [re.sub(r'\s+', ' ', e).strip().rstrip('.') + '.' for e in re.findall(r'([^.\n]*equipped with:[^.\n]*)', comp_text)]
    attach = next((re.sub(r'\s+', ' ', s).strip() + '.' for s in comp_text.split('.') if 'Leader unit' in s and 'attached' in s), None)

    # cost tiers: "YOUR 1ST TO 2ND UNITS COST" / "YOUR 3RD+ UNIT COSTS" (or "YOUR 2ND+ …"): extra = {from, sizes}
    costs, extra_sizes, extra_from, tier, gear_costs, in_gear = [], [], None, 0, [], False
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', comp_html, re.S):
        if 'dsUnitCostHeader' in row:
            # "WARGEAR OPTIONS | per Lascannon | 5": points per piece of that wargear the unit carries
            in_gear = 'WARGEAR' in text(row).upper()
            if in_gear:
                continue
            tier += 1
            fm = re.search(r'YOUR (\d+)(?:ST|ND|RD|TH)\+', text(row).upper())
            if tier > 1 and fm:
                extra_from = int(fm.group(1))
            continue
        gm = re.search(r'<td>per (.+?)</td><td><div class="PriceTag">\s*(\d+)\s*</div>', row)
        if in_gear and gm:
            gear_costs.append((text(gm.group(1)), int(gm.group(2))))
            continue
        mm = re.search(r'<td>(?:\d+-)?(\d+) models?</td><td><div class="PriceTag">\s*(\d+)\s*</div>', row)
        if mm:
            (costs if tier <= 1 else extra_sizes).append({'models': int(mm.group(1)), 'points': int(mm.group(2))})
    extra = {'from': extra_from or 3, 'sizes': extra_sizes} if extra_sizes else None

    # LEADER, or SUPPORT (11th: a bodyguard can have one Leader and one Support unit attached)
    lead_key = 'LEADER' if 'LEADER' in sec else 'SUPPORT'
    leader_text = text(sec.get(lead_key, ''))
    # targets marked as Warhammer Legends ("sLegendary"; not always right, so only used to silence the "not found" check)
    legends_targets = [text(x) for x in re.findall(r'<li class="[^"]*sLegendary[^"]*"[^>]*>(.*?)</li>', sec.get(lead_key, ''), re.S)]
    leader_targets = [l for l in leader_text.split('\n')[1:] if l.isupper() or l.istitle()]
    orders_text = re.sub(r'\s+', ' ', text(re.split(r'<table class="dsCoreArmy', sec.get('ORDERS', ''))[0])).strip()
    transport = re.sub(r'\s+', ' ', text(sec.get('TRANSPORT', ''))).strip()
    damaged_key = next((k for k in sec if k.startswith('DAMAGED')), None)

    kw_lines = [re.sub(r'^[^;:]*:', '', line).strip() for line in text(kw_block).split('\n')]
    keywords = list(dict.fromkeys(k.strip().upper() for line in kw_lines for k in re.split(r'[;,]', line) if k.strip()))

    unit = {
        'id': slug(name), 'name': {'en': name}, 'keywords': keywords, 'stats': stats,
        'weapons': list(weapons.values()), 'abilities': named,
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
    if notes: unit['wargearNotes'] = [n for n in notes if n]
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
    if lead_key == 'SUPPORT' and leader_targets: unit['leader'] = {'support': True}
    leader_targets = [(t, t in legends_targets) for t in leader_targets]
    return unit, leader_targets, costs, extra, gear_costs


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
    ap.add_argument('--refresh', action='store_true', help='ignore the local page cache')
    ap.add_argument('--check', action='store_true',
                    help='write nothing; list what the import would change (exit code 1 if anything)')
    args = ap.parse_args()
    wahapedia_fetch.REFRESH = args.refresh

    fdir = ROOT / 'data' / 'factions' / args.faction
    # a Space Marine Chapter lives inside another Wahapedia faction page (see bootstrap_faction.py --chapter)
    cfg = json.loads((fdir / 'faction.json').read_text()).get('wahapedia', {})
    source, chapter = cfg.get('faction', args.faction), cfg.get('chapter')
    chapter_bit = int(cfg['chapterBit'], 16) if cfg.get('chapterBit') else None
    # base army or Chapter: only generic datasheets and the Chapter's own
    allowed = {'ADEPTUS ASTARTES'} | ({chapter} if chapter else set()) if chapter_bit is not None else None
    parent = factions.entry(args.faction).get('parent')

    pages = {}  # slug → html, fetched once
    not_core = []
    if args.all or args.list:
        slugs = datasheet_links(fetch(f'{BASE}/{source}/'), source)
        tags = {'core': [], 'legends': [], 'fw': []} | ({'other chapters': []} if allowed else {})
        for ds in slugs:
            pages[ds] = fetch(f'{BASE}/{source}/{ds}')
            if '<div class="dsOuterFrame datasheet' not in pages[ds]:
                continue  # not a datasheet page
            tag = source_tag(pages[ds])
            if tag == 'core' and allowed and not faction_keywords(pages[ds]) <= allowed:
                tag = 'other chapters'
            tags[tag].append(ds)
        for tag, names in tags.items():
            print(f'{tag.upper()} ({len(names)}): {", ".join(names)}')
        if args.list:
            return
        args.datasheets = tags['core']
        not_core = [slug(ds) for t, names in tags.items() if t != 'core' for ds in names]
    if not args.datasheets:
        ap.error('give datasheet slugs or --all')

    units_file = json.loads((fdir / 'units.json').read_text())
    points = json.loads((fdir / 'points.json').read_text())
    global_weapons = json.loads((fdir / 'weapons.json').read_text())['weapons']
    existing = {u['id']: u for u in units_file['units']}
    if not_core:
        ex = units_file.setdefault('excluded', {'_note': 'Forge World and Warhammer Legends datasheets: never imported.', 'ids': []})
        if chapter:
            ex['_note'] = "Forge World, Warhammer Legends and other Chapters' datasheets: never imported."
        ex['ids'] = sorted(set(ex['ids']) | set(not_core))
    excluded = set(units_file.get('excluded', {}).get('ids', []))
    # generic datasheets a Chapter cannot use ("Your army cannot include …", see bootstrap_faction.py)
    denied = json.loads((fdir / 'faction.json').read_text()).get('parentExcludes', {}) if parent else {}

    parsed = []
    for ds in args.datasheets:
        if ds in pages:
            page = pages[ds]
        elif args.html_dir:
            page = (Path(args.html_dir) / f'{ds}.html').read_text()
        else:
            page = fetch(f'{BASE}/{source}/{ds}')
        try:
            unit, targets, costs, extra, gear_costs = parse(page, ds, chapter_bit)
        except (AttributeError, ValueError) as e:
            print(f'skip {ds}: could not parse ({e})', file=sys.stderr)
            continue
        if slug(ds) in excluded:  # by datasheet page: "Venerable-Dreadnought" (Legends) ≠ "Venerable-Dreadnought-1"
            print(f'skip {unit["id"]} (excluded)')
            continue
        if denied and chapter not in faction_keywords(page) and (
                unit['id'] in denied.get('units', []) or any(factions.has_keywords(unit, g) for g in denied.get('unitKeywords', []))):
            print(f'skip {unit["id"]} (not allowed in this Chapter)')
            excluded.add(unit['id'])
            continue
        parsed.append((unit, targets, costs, extra, gear_costs))

    if args.all:
        # a full import replaces the faction: units that are no longer datasheets are dropped
        keep = {u['id'] for u, *_ in parsed}
        for uid in sorted(set(existing) - keep):
            print(f'drop {uid} (not an 11th edition datasheet any more)')
            existing.pop(uid)
            points['units'].pop(uid, None)
            points.get('unitsExtraCopies', {}).pop(uid, None)
            points.get('wargearCosts', {}).pop(uid, None)
    by_name = {slug(u['name']['en']): u['id'] for u in existing.values()}
    by_name.update({slug(u['name']['en']): u['id'] for u, *_ in parsed})
    issues = {}
    shared_gear = faction_wargear(fetch(f'{BASE}/{source}/'))
    for unit, targets, costs, extra, gear_costs in parsed:
        old = existing.get(unit['id'], {})
        unit['role'] = role_of(unit['keywords'])
        unit['name']['es'] = old.get('name', {}).get('es', unit['name']['en'])
        lead = [by_name.get(slug(t)) for t, _ in targets]
        if any(lead):
            unit['leader'] = {'canLead': [x for x in lead if x], **unit.get('leader', {})}
        else:
            unit.pop('leader', None)
        for key in ('bodyguard', 'notes'):
            if key in old: unit[key] = old[key]
        unmatched = [t for (t, legends), x in zip(targets, lead) if not x and not legends and slug(t) not in excluded]  # Legends/FW targets are expected
        if costs:
            points['units'][unit['id']] = costs
            points.setdefault('verified', [])
            if unit['id'] not in points['verified']: points['verified'].append(unit['id'])
        if extra:
            points.setdefault('unitsExtraCopies', {})[unit['id']] = extra
        else:
            points.get('unitsExtraCopies', {}).pop(unit['id'], None)
        costs_raw = costs
        split = wargear.companion_split(unit.get('composition', []), unit.get('equipped', []), [c['models'] for c in costs])
        if split:  # 3, 3+3 companions, 6, 6+6 → sizes 3 and 6, companions cost per model (see wargear.companion_split)
            lo = split[2]
            comp_cost = (costs[1]['points'] - costs[0]['points']) // lo
            costs = [costs[0], costs[2]]
            if extra:
                extra['sizes'] = [extra['sizes'][0], extra['sizes'][2]]
                points.setdefault('unitsExtraCopies', {})[unit['id']] = extra
            points['units'][unit['id']] = costs
        unit['sizes'] = [{'models': c['models']} for c in costs] or old.get('sizes') or [{'models': 1}]
        unparsed = wargear.build(unit, [c['models'] for c in costs_raw] if split else [s['models'] for s in unit['sizes']], global_weapons, shared_gear)
        resolve = wargear.make_resolver([w['id'] for w in unit['weapons']], global_weapons)
        per_item = {}
        for name, pts in gear_costs:
            _, ids, is_weapon = resolve(name)
            per_item[ids[0]] = pts
            carried = {i for sz in unit['sizes'] for i in sz['loadout']} | \
                      {x['item'] for o in unit['wargear'] for pk in o['packages'].values() for x in pk}
            if not is_weapon and ids[0] not in carried:
                unparsed.append(f'wargear cost for "{name}" is not a weapon of the datasheet')
        if split:
            comp_opt = unit['wargear'][-1]
            for x in comp_opt['packages'][comp_opt['gives']][:1]:
                per_item[x['item']] = comp_cost
        if per_item:
            points.setdefault('wargearCosts', {})[unit['id']] = per_item
        else:
            points.get('wargearCosts', {}).pop(unit['id'], None)
        existing[unit['id']] = {**unit}
        if unparsed or unmatched:
            issues[unit['id']] = unparsed + [f'leader target not found: {t}' for t in unmatched]
        print(f"{unit['id']:34} {unit['role']:12} weapons={len(unit['weapons']):2} "
              f"wargear={len(unit['wargear'])}/{len(unit.get('wargearOptions', []))} pts={[c['points'] for c in costs]}")
    for uid, msgs in issues.items():
        print(f'CHECK {uid}: ' + ' | '.join(msgs))

    order = ['character', 'battleline', 'infantry', 'mounted', 'monster', 'vehicle', 'transport', 'aircraft', 'titanic', 'fortification']
    if parent:
        inherited = drop_inherited(existing, points, factions.raw(parent))
        print(f'{len(inherited)} generic datasheets inherited from {parent}; overrides: '
              f'{", ".join(sorted(u for u in existing if u in {p["id"] for p in factions.raw(parent)["units"]})) or "none"}')
    units_file['units'] = sorted(existing.values(), key=lambda u: (order.index(u['role']) if u['role'] in order else 99, u['name']['en']))
    if args.check:
        changes = report_changes(fdir, units_file, points)
        print(f'{args.faction}: {changes} changes' if changes else f'{args.faction}: no changes')
        sys.exit(1 if changes else 0)
    (fdir / 'units.json').write_text(json.dumps(units_file, ensure_ascii=False, indent=1) + '\n')
    (fdir / 'points.json').write_text(json.dumps(points, ensure_ascii=False, indent=1) + '\n')
    factions.refresh_counts(parent or args.faction)


POINT_SECTIONS = ('units', 'unitsExtraCopies', 'wargearCosts')


def drop_inherited(existing, points, parent):
    """A Chapter keeps a generic datasheet only if it differs from the parent's (datasheet or points).
    Removes the identical ones from `existing` and `points`; returns their ids."""
    def same(a, b):
        strip = lambda u: {**u, 'name': u['name']['en']}  # noqa: E731  (the Spanish name lives in i18n)
        return strip(a) == strip(b)
    by_id = {u['id']: u for u in parent['units']}
    inherited = [uid for uid, u in existing.items() if uid in by_id and same(u, by_id[uid]) and
                 all(points.get(s, {}).get(uid) == parent['points'].get(s, {}).get(uid) for s in POINT_SECTIONS)]
    for uid in inherited:
        del existing[uid]
        for s in POINT_SECTIONS:
            points.get(s, {}).pop(uid, None)
        if uid in points.get('verified', []):
            points['verified'].remove(uid)
    return inherited


def report_changes(fdir, units_file, points):
    """--check: print what the import would change in units.json / points.json, field by field. Returns the count.
    After a change to the importer or to tools/wargear.py, a re-import of the other factions should change nothing."""
    short = lambda v: (s if len(s := json.dumps(v, ensure_ascii=False)) <= 140 else s[:137] + '…')  # noqa: E731
    old_units = {u['id']: u for u in json.loads((fdir / 'units.json').read_text())['units']}
    new_units = {u['id']: u for u in units_file['units']}
    old_points = json.loads((fdir / 'points.json').read_text())
    changes = []
    for uid in sorted(set(old_units) | set(new_units)):
        old, new = old_units.get(uid), new_units.get(uid)
        if old is None or new is None:
            changes.append(f'{uid}: {"new unit" if old is None else "removed"}')
            continue
        changes += [f'{uid}.{k}: {short(old.get(k))} → {short(new.get(k))}' for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
    if units_file.get('excluded') != json.loads((fdir / 'units.json').read_text()).get('excluded'):
        changes.append('excluded datasheets')
    for section in sorted(set(old_points) | set(points)):
        old, new = old_points.get(section), points.get(section)
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict):
            changes += [f'points.{section}.{k}: {short(old.get(k))} → {short(new.get(k))}' for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
        else:
            changes.append(f'points.{section}: {short(old)} → {short(new)}')
    for c in changes:
        print(f'CHANGE {c}')
    return len(changes)


if __name__ == '__main__':
    main()
