"""Import 10th-edition style datasheet PDFs (one unit per PDF) into a faction's units.json.

Usage (needs `pip install pypdf pillow`):
    python tools/import_datasheets.py <pdf-dir> <faction-id> [--points PointsV1.1.pdf] [--skip "Infantry Squad,..."]

- Every PDF under <pdf-dir> (recursively) is parsed: stats, per-unit weapon profiles, abilities,
  wargear options, composition, leader targets, transport, lore.
- Unit pictures are not extracted: the app uses webstore URLs (images.json, see tools/store_images.py).
- Hand-curated fields already in units.json are kept: Spanish name, structured `wargear`,
  `role`, `bodyguard`, `orders`, `notes`. Units in units.json with no PDF are kept untouched.
- With --points, units that have no entry in points.json get sizes/points from that MFM PDF
  (they stay unverified).
"""
import argparse
import json
import os
import re
import unicodedata
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent

# PDF file name → existing unit id, when the app already uses a different id
ID_ALIASES = {
    'regimental-enginseer': 'tech-priest-enginseer',
    'regimental-preacher': 'ministorum-priest',
    'tank-commander': 'leman-russ-commander',
    'ratling-snipers': 'ratlings',
    'militarum-tempestus-command-squad': 'tempestus-command-squad',
}

TEMPLATE_IMAGE_SIZES = {(214, 214)}  # card textures; full-page backgrounds are filtered by width


def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()  # "Khârn" → "kharn"
    s = s.lower().replace('’', '').replace('‘', '').replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def norm_name(s):
    s = re.sub(r'\bT (ank|aurox|arantula)', r'T\1', s)  # MFM PDF kerning artefacts
    return slug(s)


def title(s):
    small = {'of', 'the', 'and'}
    return ' '.join(w.lower() if w.lower() in small and i else w[:1].upper() + w[1:].lower() for i, w in enumerate(s.split()))


# ---------- text parsing ----------

WEAPON_RE = re.compile(r'^(?P<name>.+?)(?: \[(?P<kw>[^\]]+)\])? (?P<range>Melee|N/A|\d+\+?") (?P<A>\S+) (?P<skill>\S+) (?P<S>\S+) (?P<AP>\S+) (?P<D>\S+)$')
STAT_RE = re.compile(r'^(?P<M>\d+\+?"|-) (?P<T>\d+) (?P<Sv>\d\+) (?P<W>\d+) (?P<Ld>\d\+) (?P<OC>\d+)\s*(?P<name>.*)$')
ABILITY_RE = re.compile(r'^(?P<name>[A-Z0-9‘’\'][^:]{1,70}?):\s*(?P<text>.*)$')


def section(lines, start, stops):
    """Lines after the first line matching `start` up to (excluding) the first line matching any stop."""
    out, on = [], False
    for ln in lines:
        if not on:
            if re.match(start, ln.strip()):
                on = True
            continue
        if any(re.match(s, ln.strip()) for s in stops):
            break
        out.append(ln)
    return out


def parse_weapons(lines, kind):
    weapons, buf = [], ''
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        cand = f'{buf} {ln}'.strip() if buf else ln
        m = WEAPON_RE.match(cand)
        if m:
            weapons.append((m, kind))
            buf = ''
        elif ':' in ln and '[' not in ln:  # explanation of a weapon rule, e.g. "One Shot: ..."
            buf = ''
        else:
            buf = cand if len(cand) < 160 else ''
    out = {}
    for m, kind in weapons:
        full = m['name'].strip()
        mm = re.match(r'^(.*?) [–-] (.*)$', full)
        base, mode = (mm.group(1).strip(), mm.group(2)) if mm else (full, '')
        wid = slug(base)
        w = out.setdefault(wid, {'id': wid, 'name': {'en': base}, 'type': kind, 'profiles': []})
        p = {'range': m['range'], 'A': m['A'], 'skill': m['skill'], 'S': m['S'], 'AP': m['AP'], 'D': m['D'],
             'keywords': [title(k.strip()) for k in m['kw'].split(',')] if m['kw'] else []}
        if mode:
            p['mode'] = {'en': mode.strip()}
        w['profiles'].append(p)
    return list(out.values())


def parse_abilities(lines):
    core, faction, named = [], [], []
    cur = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith('CORE:'):
            core += [x.strip() for x in s[5:].split(',') if x.strip()]
            cur = None
        elif s.startswith('FACTION:'):
            faction += [x.strip() for x in s[8:].split(',') if x.strip()]
            cur = None
        else:
            m = ABILITY_RE.match(s)
            if m and (cur is None or cur['text']['en'].endswith('.') or len(m['name']) < 40):
                cur = {'name': {'en': m['name'].strip()}, 'text': {'en': m['text'].strip()}}
                named.append(cur)
            elif cur:
                cur['text']['en'] = f"{cur['text']['en']} {s}".strip()
    return core, faction, named


def bullets(lines):
    """'■ text ◦ choice ◦ choice' blocks → [{text, choices}]"""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith('*'):
            continue
        if s.startswith('■'):
            out.append({'text': s.lstrip('■ ').strip(), 'choices': []})
        elif s.startswith('◦') and out:
            out[-1]['choices'].append(s.lstrip('◦ ').strip())
        elif out:
            if out[-1]['choices']:
                out[-1]['choices'][-1] += ' ' + s
            else:
                out[-1]['text'] += ' ' + s
    for b in out:
        b['text'] = re.sub(r'\s+', ' ', b['text']).strip()
    return out


def parse_pdf(path):
    pages = [p.extract_text() for p in PdfReader(path).pages]
    p1 = pages[0].split('\n')
    p2 = '\n'.join(pages[1:]).split('\n')
    all_lines = p1 + p2
    name = p1[0].strip()

    kw_first = re.sub(r'^KEYWORDS\s*[–:-]?\s*', '', next(l for l in p1 if l.startswith('KEYWORDS')))
    kw_text = ' '.join([kw_first] + section(p1, r'^KEYWORDS', [r'^(RANGED|MELEE) WEAPONS', r'^FACTION KEYWORDS']))
    keywords = []
    for part in kw_text.split('|'):
        part = re.sub(r'^\s*(ALL MODELS|[A-Z’\' -]+):', '', part.strip())
        for k in part.split(','):
            k = k.strip().upper()
            if k and k not in keywords:
                keywords.append(k)

    weapons = parse_weapons(section(p1, r'^RANGED WEAPONS', [r'^MELEE WEAPONS', r'^FACTION KEYWORDS']), 'ranged')
    weapons += parse_weapons(section(p1, r'^MELEE WEAPONS', [r'^FACTION KEYWORDS']), 'melee')

    stops = [r'^WARGEAR ABILITIES', r'^ORDERS', r'^INVULNERABLE SAVE', r'^M T SV W LD OC', r'^T SV W LD OC', r'^DAMAGED']
    core, faction, abilities = parse_abilities(section(p1, r'^ABILITIES', stops))
    _, _, wargear_abilities = parse_abilities(section(p1, r'^WARGEAR ABILITIES', stops[1:]))
    orders_text = ' '.join(l.strip() for l in section(p1, r'^ORDERS$', stops[2:] + [r'^WARGEAR ABILITIES'])).strip()
    damaged = None
    dmg_head = next((l for l in p1 if l.startswith('DAMAGED')), None)
    if dmg_head:
        damaged = {'name': {'en': dmg_head.replace('DAMAGED:', '').strip().capitalize()},
                   'text': {'en': ' '.join(l.strip() for l in section(p1, r'^DAMAGED', [r'^M T SV', r'^T SV', r'^INVULNERABLE', r'^ORDERS', r'^WARGEAR ABILITIES']))}}
    inv = next((re.search(r'(\d\+)', l).group(1) for l in p1 if l.startswith('INVULNERABLE SAVE') and re.search(r'\d\+', l)), None)

    stats, pending_names = [], []
    # aircraft cards print "T SV W LD OC" and glue M after OC: '10 2+ 14 7+ 020+"'
    for ln in section(p1, r'^T SV W LD OC$', [r'^Before selecting', r'^=====']):
        m = re.match(r'^(\d+) (\d\+) (\d+) (\d\+) (\d)(\d+\+?")$', ln.strip())
        if m:
            stats.append(dict(zip(('T', 'Sv', 'W', 'Ld', 'OC', 'M'), m.groups())))
    for ln in section(p1, r'^M T SV W LD OC', [r'^Before selecting', r'^=====']):
        s = ln.strip()
        m = STAT_RE.match(s)
        if m:
            st = {k: m[k] for k in ('M', 'T', 'Sv', 'W', 'Ld', 'OC')}
            if m['name']:
                st['name'] = {'en': title(m['name'])}
            stats.append(st)
        elif s and s.isupper():
            pending_names.append(title(s))
    for st in stats:
        if 'name' not in st and pending_names and len(stats) > 1:
            st['name'] = {'en': pending_names.pop(0)}
    if inv:
        for st in stats:
            st['inv'] = inv

    heading = r'^(LEADER|TRANSPORT|UNIT COMPOSITION|WARGEAR OPTIONS)$'
    name_line = r'^' + re.escape(name) + r'$'
    wargear_opts = [b for b in bullets(section(p2, r'^WARGEAR OPTIONS', [r'^UNIT COMPOSITION'])) if not b['text'].startswith('None')]
    comp_lines = section(p2, r'^UNIT COMPOSITION', [r'^LEADER$', r'^TRANSPORT$', name_line])
    composition = [b['text'] for b in bullets([l for l in comp_lines if l.strip().startswith('■') or not re.search(r'equipped|attached|Leader', l)]) ]
    comp_text = re.sub(r'\s+', ' ', ' '.join(l.strip() for l in comp_lines if not l.strip().startswith('■')))
    equipped = [e.strip() + '.' for e in re.findall(r'([^.]*equipped with:[^.]*)(?:\.|$)', comp_text)]
    attach_rule = next((s.strip() + '.' for s in comp_text.split('.') if 'Leader unit' in s and 'attached' in s), None)
    composition = [c for c in composition if 'equipped with' not in c and c != 'OR']

    leader_targets = [b['text'] for b in bullets(section(p2, r'^LEADER$', [r'^TRANSPORT$', r'^[A-Z][A-Z ’\'-]+$']))]
    transport = ' '.join(l.strip() for l in section(p2, r'^TRANSPORT$', [name_line])).strip() or None
    lore = ' '.join(l.strip() for l in section(p2, name_line, [r'^KEYWORDS'])).strip() or None

    # default loadout: weapons named in the "equipped with" sentences
    by_slug = {w['id']: w['id'] for w in weapons}
    loadout = []
    for sent in equipped:
        for item in sent.split(':', 1)[1].strip(' .').split(';'):
            item = re.sub(r'^\d+\s+', '', item.strip())
            sid = slug(item.replace('las pistol', 'laspistol'))
            for cand in (sid, sid[:-1] if sid.endswith('s') else sid):
                if cand in by_slug and cand not in loadout:
                    loadout.append(cand)
                    break

    unit = {
        'name': {'en': title(name)},
        'keywords': keywords,
        'stats': stats,
        'weapons': weapons,
        'loadout': loadout,
        'abilities': abilities,
        'core': core,
        'factionAbilities': faction,
    }
    if wargear_abilities: unit['wargearAbilities'] = wargear_abilities
    if damaged: unit['damaged'] = damaged
    if orders_text: unit['ordersText'] = {'en': orders_text}
    m = re.search(r'issue (\d+) Orders?', orders_text)
    if m: unit['orders'] = int(m.group(1))
    if wargear_opts: unit['wargearOptions'] = wargear_opts
    if composition: unit['composition'] = composition
    if equipped: unit['equipped'] = equipped
    if leader_targets: unit['leaderTargets'] = leader_targets
    if attach_rule:
        unit['attachRule'] = attach_rule
        bg = {}
        if re.search(r'up to two Leader units', attach_rule): bg['maxLeaders'] = 2
        m = re.search(r'no more than one of those units is an? ([A-Za-z ]+?) unit', attach_rule)
        if m: bg['maxWithKeyword'] = {m.group(1).upper(): 1}
        if bg: unit['bodyguard'] = bg
    if transport: unit['transport'] = {'en': transport}
    if lore: unit['lore'] = {'en': lore}
    return unit


# ---------- structured wargear from the "Wargear options" text ----------

OWNER = r"(?:This model's|The [^']+?'s|\d+ [^']+?'s)"


def weapon_id(text, known):
    """'2 heavy bolters' → 'heavy-bolter' if that weapon exists (on the datasheet or in weapons.json)."""
    if not text:
        return None
    t = re.sub(r'^\d+\s+', '', text.strip().rstrip('.*').strip())
    t = t.split(' and ')[0] if ' and ' in t else t
    sid = slug(t)
    for cand in (sid, sid[:-1] if sid.endswith('s') else None, sid[:-2] if sid.endswith('es') else None):
        if cand and cand in known:
            return cand
    return None


def gen_wargear(unit, global_weapons):
    known = {w['id'] for w in unit['weapons']} | set(global_weapons)
    name = lambda wid: next((w['name']['en'] for w in unit['weapons'] if w['id'] == wid), None) or global_weapons.get(wid, {}).get('name', {}).get('en', wid)
    opts = []
    for i, o in enumerate(unit.get('wargearOptions', [])):
        t = o['text'].replace('’', "'").strip().rstrip('*: ').strip()
        t = re.sub(r'\b(one|two|three|four)\b(?= [A-Z])', lambda m: str(['one', 'two', 'three', 'four'].index(m.group(1)) + 1), t)
        choices = [c for c in (weapon_id(c, known) for c in o['choices']) if c]
        opt = None
        m_every = re.match(r'^For every (\d+) models in this unit, (?:up to (\d+)|(\d+)) .+? can (?:each )?(?:have their (.+?) replaced|be replaced) with (one of the following|.+?)\.?$', t)
        m_upto = re.match(r'^Up to (\d+) .+? can each have their (.+?) replaced with (one of the following|.+?)\.?$', t)
        m_any = re.match(r'^Any number of (models|.+?) can (?:each have their (.+?) replaced|replace their (.+?)) with (one of the following|.+?)\.?$', t)
        m_swap = re.match(rf'^{OWNER} (.+?) can be replaced with (one of the following|.+?)\.?$', t)
        m_equip_one = re.match(r'^.*can (?:each )?be equipped with one of the following', t)
        m_equip = re.match(r'^(This model|Any number of models|.+?) can (?:each )?be equipped with (\d+ .+?)\.?$', t)
        if m_every:
            per, k = int(m_every.group(1)), int(m_every.group(2) or m_every.group(3))
            alts = choices if m_every.group(5) == 'one of the following' else [weapon_id(m_every.group(5), known)]
            alts = [a for a in alts if a]
            if alts:
                opt = {'type': 'pool', 'max': k, 'per': per, 'choices': alts,
                       'label': {'en': f'Up to {k} per {per} models', 'es': f'Hasta {k} cada {per} modelos'}}
        elif m_upto:
            k = int(m_upto.group(1))
            alts = choices if m_upto.group(3) == 'one of the following' else [weapon_id(m_upto.group(3), known)]
            alts = [a for a in alts if a]
            if alts:
                opt = {'type': 'pool', 'max': k, 'choices': alts, 'label': {'en': f'Up to {k} models', 'es': f'Hasta {k} modelos'}}
        elif m_any:
            x = weapon_id(m_any.group(2) or m_any.group(3), known)
            alts = choices if m_any.group(4) == 'one of the following' else [weapon_id(m_any.group(4), known)]
            alts = [a for a in alts if a and a != x]
            if x and alts:
                if m_any.group(1) == 'models':
                    opt = {'type': 'pool', 'max': 1, 'per': 1, 'replaces': x, 'choices': alts,
                           'label': {'en': f'Replace {name(x)} (any number)', 'es': f'Sustituir {name(x)} (cualquier número)'}}
                else:
                    opt = {'type': 'swap', 'default': x, 'choices': [x] + alts,
                           'label': {'en': f'{m_any.group(1)}: {name(x)}', 'es': f'{m_any.group(1)}: {name(x)}'}}
        elif m_swap:
            x = weapon_id(m_swap.group(1), known)
            alts = choices if m_swap.group(2) == 'one of the following' else [weapon_id(m_swap.group(2), known)]
            alts = [a for a in alts if a and a != x]
            if x and alts:
                opt = {'type': 'swap', 'default': x, 'choices': [x] + alts,
                       'label': {'en': f'Replace {name(x)}', 'es': f'Sustituir {name(x)}'}}
        elif m_equip_one and choices:
            opt = {'type': 'swap', 'default': '', 'choices': [''] + choices,
                   'label': {'en': 'Optional weapon', 'es': 'Arma opcional'}}
        elif m_equip:
            y = weapon_id(m_equip.group(2), known)
            if y:
                many = m_equip.group(1) == 'Any number of models'
                opt = {'type': 'toggle', 'gives': y, **({'max': 1, 'per': 1} if many else {}),
                       'label': {'en': f'Add {name(y)}', 'es': f'Añadir {name(y)}'}}
        if opt:
            opts.append({'id': f'o{i + 1}', **opt})
    return opts


def role_of(kw):
    if 'FORTIFICATION' in kw: return 'fortification'
    if 'TITANIC' in kw: return 'titanic'  # Imperial Knights are TITANIC CHARACTERs: group them as titanic
    if 'CHARACTER' in kw: return 'character'
    if 'BATTLELINE' in kw: return 'battleline'
    if 'AIRCRAFT' in kw: return 'aircraft'
    if 'TITANIC' in kw: return 'titanic'
    if 'TRANSPORT' in kw: return 'transport'
    if 'MONSTER' in kw: return 'monster'
    if 'VEHICLE' in kw: return 'vehicle'
    if 'MOUNTED' in kw: return 'mounted'
    return 'infantry'


# ---------- points (MFM PDF) ----------

def parse_mfm(path, faction_title):
    text = '\n'.join(p.extract_text() for p in PdfReader(path).pages)
    start = text.find(f'\n{faction_title.upper()}\n')
    block = text[start:]
    end = block.find('DETACHMENT ENHANCEMENTS')
    block = block[:end]
    sizes, cur = {}, None
    for ln in block.split('\n'):
        ln = ln.strip()
        m = re.match(r'^(\d+)(?:-(\d+))? models?\s*\.+\s*(\d+) pts', ln)
        if m and cur:
            sizes.setdefault(cur, []).append({'models': int(m.group(2) or m.group(1)), 'points': int(m.group(3))})
        elif ln and not ln.isdigit() and 'POINTS VALUES' not in ln:
            cur = norm_name(ln)
    return sizes


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf_dir')
    ap.add_argument('faction')
    ap.add_argument('--points')
    ap.add_argument('--skip', default='')
    args = ap.parse_args()

    fdir = ROOT / 'data' / 'factions' / args.faction
    units_path, points_path = fdir / 'units.json', fdir / 'points.json'
    units_file = json.loads(units_path.read_text())
    points = json.loads(points_path.read_text())
    existing = {u['id']: u for u in units_file['units']}
    global_weapons = json.loads((fdir / 'weapons.json').read_text())['weapons']
    skip = {slug(s) for s in args.skip.split(',') if s.strip()}
    # Forge World / Legends datasheets listed in units.json are never imported
    excluded = set(units_file.get('excluded', {}).get('ids', []))
    mfm = parse_mfm(args.points, units_file.get('factionTitle', 'Astra Militarum')) if args.points else {}

    pdfs = sorted(Path(args.pdf_dir).rglob('*.pdf'))
    parsed = {}
    for pdf in pdfs:
        sl = slug(pdf.stem)
        if sl in skip:
            continue
        try:
            u = parse_pdf(pdf)
        except Exception as e:  # not a datasheet (index, rules…)
            print(f'skip {pdf.name}: {e}', file=sys.stderr)
            continue
        if not u['stats']:
            print(f'skip {pdf.name}: no stat line', file=sys.stderr)
            continue
        uid = ID_ALIASES.get(sl, sl)
        if uid in excluded:
            continue
        u['id'] = uid
        u['source'] = pdf.name
        u['_mfm_key'] = sl
        parsed[uid] = u

    name_to_id = {}
    for uid, u in {**existing, **parsed}.items():
        name_to_id[slug(u['name']['en'])] = uid
    for sl, uid in ID_ALIASES.items():
        name_to_id[sl] = uid

    out = []
    for uid, u in parsed.items():
        old = existing.get(uid, {})
        u['role'] = old.get('role') or role_of(u['keywords'])
        u['name'] = {'en': old.get('name', {}).get('en', u['name']['en']), 'es': old.get('name', {}).get('es', u['name']['en'])}
        targets = [name_to_id.get(slug(t)) for t in u.pop('leaderTargets', [])]
        if targets:
            u['leader'] = {'canLead': [t for t in targets if t]}
        for key in ('bodyguard', 'orders', 'notes'):
            if key in old:
                u[key] = old[key]
        wargear = gen_wargear(u, global_weapons)
        if wargear:
            u['wargear'] = wargear
        mfm_key = u.pop('_mfm_key')
        if uid not in points['units']:
            sizes = mfm.get(mfm_key) or mfm.get(slug(u['name']['en']))
            if sizes:
                points['units'][uid] = sizes
        u['sizes'] = [{'models': s['models']} for s in points['units'].get(uid, [])] or old.get('sizes') or [{'models': 1}]
        out.append(u)

    # keep units that have no PDF (curated by hand)
    for uid, u in existing.items():
        if uid not in parsed:
            out.append(u)

    order = ['character', 'battleline', 'infantry', 'mounted', 'monster', 'vehicle', 'transport', 'aircraft', 'titanic', 'fortification']
    out.sort(key=lambda u: (order.index(u['role']) if u['role'] in order else 99, u['name']['en']))
    units_file['units'] = out
    units_path.write_text(json.dumps(units_file, ensure_ascii=False, indent=1) + '\n')
    points_path.write_text(json.dumps(points, ensure_ascii=False, indent=1) + '\n')
    print(f'{len(parsed)} datasheets imported, {len(out)} units total')


if __name__ == '__main__':
    main()
