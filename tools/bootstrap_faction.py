"""Create the data folder of a new faction from its Wahapedia (11th edition) page.

Usage:
    python3 tools/bootstrap_faction.py <wahapedia-faction-slug> [--color "#8a1c1c"] [--html FILE] [--force]

--force regenerates faction.json (and enhancement points) of an existing faction; units/images are kept.

    e.g. python3 tools/bootstrap_faction.py adeptus-custodes --color "#b8923a"

Writes data/factions/<slug>/:
    faction.json   army rule + detachments (DP cost, rule summary) + enhancements (requirements, type)
    units.json     empty, with an "excluded" list for Forge World / Legends datasheets
    weapons.json   empty (datasheets carry their own weapon profiles)
    points.json    enhancement points; unit points are added by import_wahapedia_datasheets.py
    images.json    empty (fill with tools/store_images.py)
and registers the faction in data/factions/index.json.
Next steps: import_wahapedia_datasheets.py --all, import_wahapedia_rules.py (see docs/NUEVA-FACCION.md).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_wahapedia_rules import BASE, clean, fetch, key, slug, strip_fluff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def summary(text, limit=320):
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + '…'


def requirements(body, faction_words):
    """Who can take an enhancement, from the start of its text. Faction keywords are dropped.
    'INFANTRY OFFICER model only.'            → requires [['INFANTRY', 'OFFICER']]
    'GHOSTKEEL BATTLESUIT/PATHFINDER TEAM …'   → one alternative per '/'
    'Kroot War Shaper model only.'             → the datasheet name: [['KROOT', 'WAR', 'SHAPER']]
    '… (excluding KROOT SHAPER models).'       → excludes [['KROOT', 'SHAPER']]
    Returns (requires, excludes)."""
    def groups(names):
        out = []
        for alt in names.split('/'):
            words = [w.upper() for w in alt.split() if w.upper() not in faction_words]
            if words:
                out.append(words)
        return out
    name = r"[A-Z][\w'’-]*(?:[ /][A-Z][\w'’-]*)*"
    m = re.match(rf"^({name})\s+(?:(?:model|unit)s?\s+)?only\b", body)
    requires = groups(m.group(1)) if m else []
    x = re.search(rf"\(excluding ({name}) (?:model|unit)s?\)", body)
    return requires, groups(x.group(1)) if x else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('faction')
    ap.add_argument('--color', default='#6b7d4a')
    ap.add_argument('--html')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    fdir = ROOT / 'data' / 'factions' / args.faction
    if (fdir / 'faction.json').exists() and not args.force:
        sys.exit(f'{fdir}/faction.json already exists (use --force to overwrite)')
    page = Path(args.html).read_text() if args.html else fetch(f'{BASE}/factions/{args.faction}/')

    title = re.search(r'<title>(.*?)</title>', page, re.S)
    name = re.sub(r'\[.*?\]', '', clean(title.group(1))).split('|')[0].split('–')[0].strip() if title else args.faction.replace('-', ' ').title()
    faction_words = set(name.upper().split())

    # army rule: first <h3> after the "Army Rules" heading
    # army rule: first heading after "Army Rules" (an <h3> in most factions, its own <h2> in some)
    a = page.find('id="Army-Rules"')
    army_html = page[page.find('</h2>', a) + 5:]
    head = re.search(r'<(h[23])[^>]*>(.*?)</\1>(.*?)(?=<h[23]|\Z)', army_html, re.S)
    army_rule = {'name': {'en': clean(head.group(2))}, 'text': {'en': summary(clean(strip_fluff(head.group(3))), 900)}} if head else \
        {'name': {'en': 'Army rule'}, 'text': {'en': ''}}

    dets_dp = re.findall(r'data-det-name="([^"]+)" data-dp-base="(\d+)"', page)
    heads = [(m.start(), m.group(1)) for m in re.finditer(r'<h2[^>]*id="([^"]+)"', page)]
    detachments, enh_points = [], {}
    seen = set()
    for det_name, dp in dets_dp:
        det_name = clean(det_name)
        did = slug(det_name)
        if did in seen:
            continue
        seen.add(did)
        pos = next((p for p, h in heads if key(h) == key(det_name)), None)
        if pos is None:
            print(f'warning: no section for detachment {det_name}', file=sys.stderr)
            continue
        end = next((p for p, h in heads if p > pos and (h in ('Crusade-Rules', 'Boarding-Actions') or
                                                         any(key(h) == key(d) for d, _ in dets_dp))), len(page))
        sec = page[pos:end]
        r_pos = re.search(r'id="Detachment-Rules?(-\d+)?"', sec)
        e_pos = re.search(r'id="Enhancements(-\d+)?"', sec)
        s_pos = re.search(r'id="Stratagems(-\d+)?"', sec)
        rule_lines = clean(strip_fluff(sec[r_pos.start():sec.rfind('<h2', 0, e_pos.start())])).split('\n')[1:] if r_pos and e_pos else []
        enhancements = []
        ens_html = sec[e_pos.start():s_pos.start()] if e_pos and s_pos else ''
        for m in re.finditer(r'<ul class="EnhancementsPts"><li><span>(.*?)</span>\s*<span>(\d+) pts</span></li></ul>(.*?)(?=<ul class="EnhancementsPts"|\Z)', ens_html, re.S):
            upgrade = 'EnhUpgrade' in m.group(1)
            ename = re.sub(r'\(Aura\)|UPGRADE', '', clean(re.sub(r'<span class="EnhUpgrade">.*?</span>', '', m.group(1)))).strip()
            body = re.split(r'\n(?:Errata|FAQ)\n', clean(strip_fluff(m.group(3))))[0].strip()
            eid = slug(ename)
            if eid in enh_points:  # same name in two detachments
                eid = f'{eid}-{did}'
            enh_points[eid] = int(m.group(2))
            requires, excludes = requirements(body, faction_words)
            e = {'id': eid, 'requires': requires, 'name': {'en': ename}, 'text': {'en': summary(body, 200)}}
            if excludes:
                e['excludes'] = excludes
            if upgrade:
                e['type'] = 'upgrade'
            enhancements.append(e)
        detachments.append({
            'id': did, 'cost': int(dp), 'name': {'en': det_name},
            'rule': {'name': {'en': rule_lines[0] if rule_lines else det_name},
                     'text': {'en': summary(' '.join(rule_lines[1:]))}},
            'enhancements': enhancements,
        })
        print(f'{did:28} {dp} DP  enhancements={len(enhancements)}')

    fdir.mkdir(parents=True, exist_ok=True)
    src = f'{BASE}/factions/{args.faction}/'
    (fdir / 'faction.json').write_text(json.dumps({
        'id': args.faction, 'name': {'en': name, 'es': name}, 'source': src,
        'armyRule': army_rule, 'detachments': detachments,
    }, ensure_ascii=False, indent=1) + '\n')
    # --force only regenerates faction.json and the enhancement points: imported units, unit points
    # and images are never overwritten
    points_path = fdir / 'points.json'
    if points_path.exists():
        pts = json.loads(points_path.read_text())
        pts['enhancements'] = enh_points
        points_path.write_text(json.dumps(pts, ensure_ascii=False, indent=1) + '\n')
    for fname, content in {
        'units.json': {'_note': 'Datasheets. Points live in points.json.', 'excluded': {'_note': 'Forge World and Warhammer Legends datasheets: never imported.', 'ids': []}, 'units': []},
        'weapons.json': {'_note': 'Shared weapon profiles for hand-written datasheets; imported datasheets carry their own.', 'weapons': {}},
        'points.json': {'_note': 'Edit when a new Munitorum Field Manual comes out.', 'version': datetime.date.today().isoformat(), 'source': src,
                        'verified': ['all-enhancements'], 'units': {}, 'enhancements': enh_points},
        'images.json': {'_note': 'Unit picture URLs (webstore). Fill with tools/store_images.py or from the app.', 'units': {}},
    }.items():
        if not (fdir / fname).exists():
            (fdir / fname).write_text(json.dumps(content, ensure_ascii=False, indent=1) + '\n')

    index_path = ROOT / 'data' / 'factions' / 'index.json'
    index = json.loads(index_path.read_text())
    if not any(f['id'] == args.faction for f in index['factions']):
        index['factions'].append({'id': args.faction, 'name': {'en': name, 'es': name}, 'edition': '11th', 'path': args.faction, 'color': args.color})
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(f'{name}: {len(detachments)} detachments → {fdir}')


if __name__ == '__main__':
    main()
