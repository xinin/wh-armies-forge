"""Factions as the app sees them. A Chapter (index.json "parent": "space-marines") only stores its own data; the app
(js/data.js → mergeChapter) and these tools combine it with its parent faction:

    faction     the parent's army rule (unless the Chapter has one) and extra rules, then the Chapter's;
                the parent's detachments, then the Chapter's
    units       the parent's datasheets, then the Chapter's; a Chapter datasheet with a parent id replaces it
                (a generic datasheet that is different for the Chapter: other points, other units it can lead)
    points, weapons, images, rules, stratagems   the parent's entries, overridden/extended by the Chapter's
    i18n        both files are loaded

faction.json of a Chapter can also have:
    parentExcludes  {"rules": [army rule names], "detachments": [ids], "units": [ids], "unitKeywords": [[kw…]]}
                    parent content the Chapter cannot use ("Your army cannot include any ADEPTUS ASTARTES PSYKER
                    models")
    keywordRules    [{"keyword": "DEATHWING", "units": [["TERMINATOR"], ["LAND", "RAIDER"], …]}]: units with all the
                    words of one group in their keywords or name gain the keyword ("The following friendly ADEPTUS
                    ASTARTES units have DEATHWING: TERMINATOR units. LAND RAIDER units. …")
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTIONS = ROOT / 'data' / 'factions'


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def index():
    return read(FACTIONS / 'index.json')['factions']


def entry(fid):
    return next(f for f in index() if f['id'] == fid)


def children(fid):
    return [f['id'] for f in index() if f.get('parent') == fid]


def raw(fid):
    """The files of one faction folder, unmerged."""
    d = FACTIONS / entry(fid)['path']
    return {
        'faction': read(d / 'faction.json'),
        'units': read(d / 'units.json')['units'],
        'points': read(d / 'points.json', {}),
        'images': read(d / 'images.json', {'units': {}})['units'],
    }


def has_keywords(unit, group):
    """Every word of the group is a word of the unit's keywords or name (["VEHICLE", "FLY"], ["LAND", "RAIDER"])."""
    words = {w for k in unit['keywords'] + [unit['name']['en']] for w in k.upper().replace('’', "'").split()}
    return all(w.replace('’', "'") in words for w in group)


def merge(parent, chapter):
    """Parent + Chapter, the same way as js/data.js (see the module docstring)."""
    pf, cf = parent['faction'], chapter['faction']
    ex = cf.get('parentExcludes', {})
    faction = {**pf, **{k: v for k, v in cf.items() if k not in ('detachments', 'extraRules')}}
    faction['armyRule'] = cf.get('armyRule') or pf['armyRule']
    faction['extraRules'] = [r for r in pf.get('extraRules', []) if r['name']['en'] not in ex.get('rules', [])] + cf.get('extraRules', [])
    faction['detachments'] = [d for d in pf['detachments'] if d['id'] not in ex.get('detachments', [])] + cf['detachments']
    own = {u['id']: u for u in chapter['units']}
    units = [own.pop(u['id'], u) for u in parent['units']
             if u['id'] not in ex.get('units', []) and not any(has_keywords(u, g) for g in ex.get('unitKeywords', []))]
    units += list(own.values())
    for rule in cf.get('keywordRules', []):
        for u in units:
            if rule['keyword'] not in u['keywords'] and any(has_keywords(u, g) for g in rule['units']):
                u['keywords'] = u['keywords'] + [rule['keyword']]
    points = dict(parent['points'])
    for k, v in chapter['points'].items():
        points[k] = {**points.get(k, {}), **v} if isinstance(v, dict) else sorted(set(points.get(k, [])) | set(v)) if isinstance(v, list) else v
    return {'faction': faction, 'units': units, 'points': points, 'images': {**parent['images'], **chapter['images']}}


def load(fid):
    """The merged faction: {'faction', 'units', 'points', 'images'}."""
    parent = entry(fid).get('parent')
    return merge(raw(parent), raw(fid)) if parent else raw(fid)


def refresh_counts(fid):
    """Unit and detachment counts in index.json (shown by the faction picker) for the faction and its Chapters."""
    path = FACTIONS / 'index.json'
    idx = read(path)
    for f in idx['factions']:
        if f['id'] == fid or f.get('parent') == fid:
            data = load(f['id'])
            f['units'], f['detachments'] = len(data['units']), len(data['faction']['detachments'])
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + '\n')
