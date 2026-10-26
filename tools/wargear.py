"""Wargear model shared by the importers: model counts per unit size, default loadout with counts, and
structured wargear options (swaps, per-model pools, add-ons) built from the datasheet texts.

Data produced for each unit (consumed by js/render.js → loadoutOf):
    sizes[i].loadout = {item: count}        item = weapon id or "gear:<slug>" (vox-caster, medi-pack…)
    wargear = [option, …] with
        type      'swap'   one choice replaces `replaces` (on 1 model, or on all models when scope == 'all')
                  'pool'   several models each pick a choice; total ≤ max for the current size
                  'toggle' add `gives` to 1..max models (checkbox when max == 1 or scope == 'all')
        replaces  [{item, n}]  removed per model that takes the option
        choices   [key, …]     swap/pool choices; key '' (swap) = keep the default
        packages  {key: [{item, n}]}  what each choice gives (per model); n < 0 removes equipment
                                      (exclusive alternatives: "You can select one of the following options")
        maxBySize {models: max}       pools/toggles
        minModels                     only available from that unit size
        scope     'all'               the swap/toggle applies to every model at once
        maxEachBySize {models: n}     pools: the same choice cannot be taken more than n times (footnotes)
        maxEachChoice {key: {models: n}}  pools: limit of one choice ("it cannot take duplicates of this piece of wargear")
        owner     model type the option applies to ("Shock Trooper Sergeants"), exclusive: alternatives
        label / labels  English labels (the app rebuilds them in the current language)
    uniqueGear    [item]          "* This model cannot have duplicates of these pieces of wargear" (at most 1 per model)
    exclusiveGear [[a, b]]        "* No model can be equipped with both a twin plasma rifle and twin smart missile system"
    gearWeapons   {"gear:<slug>": [{item, n}]}  weapons a piece of wargear gives ("MV15 Gun Drone: The bearer is
                                                equipped with 1 twin pulse blaster", faction drones)
    abilityWeapons [{item, n}]                  weapons an ability gives ("… its Shas'ui model is equipped with the
                                                support turret weapon")
Option texts that do not fit a known pattern stay as text only (wargearOptions) and are reported by
tools/audit_units.py.
"""
import re

NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'a': 1, 'an': 1}


def slug(s):
    s = s.lower().replace('’', '').replace('‘', '').replace("'", '').replace('é', 'e')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def num(word):
    return int(word) if word.isdigit() else NUMBERS.get(word.lower(), 1)


def singular(word):
    if word.endswith('men'):
        return word[:-3] + 'man'
    if len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def type_key(name):
    """'Shock Trooper Sergeants' / 'Shock Trooper Sergeant – EPIC HERO' → 'shock trooper sergeant'"""
    name = re.sub(r'\s*–.*$|\*|\bmodels?\b', '', name.replace('’', "'").replace('‘', "'")).strip().lower()
    return ' '.join(singular(w) for w in name.split())


# ---------- composition: model counts per type and unit size ----------

def parse_composition(entries):
    """['1 Tempestor', '4-9 Tempestus Scions'] → [[(1, 1, 'tempestor'), (4, 9, 'tempestus scion')]]
    Entries that each contain ' and ' are alternatives ("1 Sergeant and 9 Troopers" / "2 … and 18 …")."""
    def part(text):
        m = re.match(r'^(\d+)(?:-(\d+))?\s+(.+)$', text.strip())
        return (int(m.group(1)), int(m.group(2) or m.group(1)), type_key(m.group(3))) if m else None

    entries = [e for e in entries if e.strip() and e.strip().upper() != 'OR']
    if len(entries) > 1 and all(' and ' in e for e in entries):
        alts = [[part(p) for p in e.split(' and ')] for e in entries]
    else:
        alts = [[part(p) for e in entries for p in e.split(' and ')]]
    return [[p for p in alt if p] for alt in alts if any(alt)]


def type_counts(alternatives, models):
    """{type: count} for a unit of `models` models."""
    for alt in alternatives:
        lo, hi = sum(p[0] for p in alt), sum(p[1] for p in alt)
        if lo <= models <= hi:
            counts = {t: a for a, _, t in alt}
            rest = models - lo
            for a, b, t in reversed(alt):  # give the extra models to the ranged entries, last first
                add = min(rest, b - a)
                counts[t] += add
                rest -= add
            return counts
    return {}


def count_of(subject, counts, models):
    """How many models a sentence subject refers to: 'Every Shock Trooper' → 9, '1 other Veteran' → 1."""
    s = subject.strip().replace('’', "'")
    low = s.lower()
    if low in ('this model', 'every model', 'each model', 'all models', 'all models in this unit', 'every model in this unit'):
        return models
    m = re.match(r'^(\d+|one|two|three|four|five) (?:other )?(.+)$', s, re.I)
    if m:
        return num(m.group(1))
    s = re.sub(r'^(every|each|all|the)\s+', '', s, flags=re.I)
    t = type_key(s)
    if t in counts:
        return counts[t]
    for k, v in counts.items():  # 'Tempestor Prime' ~ 'tempestor prime', 'Shock Trooper' ⊂ …
        if k.endswith(t) or t.endswith(k):
            return v
    return 1


# ---------- items: weapon ids or gear ----------

def compact(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def one_edit(a, b):
    """True if a and b differ by exactly one inserted, deleted or replaced character."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i + (len(a) == len(b)):] == b[i + 1:]


def make_resolver(weapon_ids, global_ids=()):
    known = set(weapon_ids)
    allids = known | set(global_ids)
    by_compact = {compact(i): i for i in allids}

    def one_word(extra):
        return extra and '-' not in extra and not re.search(r'\d|^and$', extra)

    def find(sid, fuzzy):
        cands = list(filter(None, [sid, sid[:-1] if sid.endswith('s') else None, sid[:-2] if sid.endswith('es') else None]))
        for c in cands:
            if c in allids:
                return c
            if compact(c) in by_compact:  # "battlecannon" ~ "battle-cannon"
                return by_compact[compact(c)]
        # one-letter typo in a long name ("dart-bow and tri-bade" ~ "dart-bow-and-tri-blade")
        typo = {i for c in cands if len(compact(c)) >= 12 for k, i in by_compact.items() if one_edit(compact(c), k)}
        if len(typo) == 1:
            return typo.pop()
        if not fuzzy:
            return None
        # "Militarum multi-laser" ~ "multi-laser", "additional heavy stubbers" ~ "heavy-stubber":
        # the names differ by one leading qualifier word
        ends = [i for c in cands for i in known if (c.endswith('-' + i) and one_word(c[:-len(i) - 1]))
                or (i.endswith('-' + c) and one_word(i[:-len(c) - 1]))]
        return max(ends, key=len) if ends else None

    def resolve(text, fuzzy=True):
        """'2 twin heavy bolters' → (2, ['twin-heavy-bolter'], True); 'vox-caster' → (1, ['gear:vox-caster'], False)"""
        t = text.replace('\u2011', '-').strip().strip('.*').strip()
        n = 1
        m = re.match(r'^(\d+|one|two|three|four|a|an)\s+(.+)$', t, re.I)
        if m:
            n, t = num(m.group(1)), m.group(2)
        t = t.replace('las pistol', 'laspistol')
        c = find(slug(t), fuzzy)
        if c:
            ids = [c] + [f'{c}-{k}' for k in ('melee', 'ranged') if f'{c}-{k}' in known]
            return n, ids, True
        g = slug(' '.join(singular(w) for w in t.split()))
        return n, [f'gear:{g}'], False
    return resolve


def gear_id(name):
    """'MV15 Gun Drones' → 'gear:mv15-gun-drone' (the id resolve() gives to non-weapon equipment)"""
    name = re.sub(r'\s*\(.*?\)', '', name)  # "Command-link Drone (Aura)"
    return 'gear:' + slug(' '.join(singular(w) for w in name.replace('\u2011', '-').split()))


def items_of(text, resolve):
    """'1 bone cleaver, lash whip and rending claws' → the weapon of that exact name if it exists, otherwise
    the parts: '1 Caestus Fist, 1 Iliastus Accelerator Culverin and 1 Twin …' → three items."""
    text = re.sub(r'\(.*?\)|\[.*?\]', '', text).strip(' .:*')
    if not text or text.lower() == 'nothing':
        return []
    tokens = re.split(r'(,\s*|\s+and\s+)', text)
    parts, seps = tokens[0::2], tokens[1::2]
    out, i = [], 0
    while i < len(parts):
        for j in range(len(parts), i, -1):  # longest run of parts that names a real weapon (exact name only)
            cand = parts[i] + ''.join(seps[k] + parts[k + 1] for k in range(i, j - 1))
            n, ids, is_weapon = resolve(cand, fuzzy=(j == i + 1))
            if is_weapon or j == i + 1:
                out += [{'item': x, 'n': n} for x in ids]
                i = j
                break
    return out


# ---------- default loadout ----------

def base_loadout(equipped, counts, models, resolve):
    """'Every Heavy Weapons Gunner is equipped with: lascannon; laspistol …' → {'lascannon': 3, …}"""
    out = {}
    for sentence in equipped:
        m = re.match(r'^(.*?)\s+(?:is|are)\s+equipped with:?\s*(.*)$', sentence.strip().rstrip('.'), re.S)
        if not m:
            continue
        k = count_of(m.group(1), counts, models)
        for item in m.group(2).split(';'):
            for x in items_of(item, resolve):
                out[x['item']] = out.get(x['item'], 0) + x['n'] * k
    return out


# ---------- options ----------

OWNER = r"(?:This model's|(?P<n1>\d+|One|one) (?:other )?(?P<o2>[^']+?)'s|The (?P<o1>[^']+?)'s|(?P<o3>one model)'s)"
COND = r"(?:If this unit contains (?P<min>\d+) models, )?"


def max_each(notes, model_sizes):
    """Footnote '* You cannot select the same weapon more than once per unit unless it contains 20 models, in which
    case … more than twice' → {10: 1, 20: 2}."""
    for note in notes:
        m = re.search(r'cannot select the same (?:weapon|option)\w* more than (once|twice|\w+ times)', note)
        if not m:
            continue
        base = {'once': 1, 'twice': 2}.get(m.group(1), num(m.group(1).split()[0]))
        out = {str(mm): base for mm in model_sizes}
        u = re.search(r'unless it contains (\d+) models, in which case .*? more than (once|twice|\w+ times)', note)
        if u:
            more = {'once': 1, 'twice': 2}.get(u.group(2), num(u.group(2).split()[0]))
            out.update({str(mm): more for mm in model_sizes if mm >= int(u.group(1))})
        return out
    return None


def parse_option(text, choices, resolve, sizes_counts, base_by_size, notes=()):
    """One wargear option text → structured option dict (without id/label), or None if not understood."""
    footnote = '*' in text
    t = re.sub(r'\*+', '', text.replace('’', "'").replace('\u2011', '-')).strip()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'have their (.+?) can be replaced with', r'have their \1 replaced with', t)  # GW typo (Piranhas)
    t = re.sub(r"\.\s*That model's .+? cannot be replaced\.?$", '.', t)  # restriction already implied by the option

    def targets(y):
        y = y.strip().rstrip('.').strip()
        if not y or re.match(r'^(?:one|1) of the following:?$', y, re.I):
            return [items_of(c, resolve) for c in choices]
        return [items_of(y, resolve)]

    def pack(packages):
        keys, out = [], {}
        for p in packages:
            if not p:
                continue
            k = '+'.join(f'{x["n"]}x{x["item"]}' if x['n'] > 1 else x['item'] for x in p)
            keys.append(k)
            out[k] = p
        return keys, out

    def by_size(fn):
        return {str(m): fn(m, c) for m, c in sizes_counts.items()}

    def count_items(m, x):
        return min((base_by_size[m].get(r['item'], 0) // max(r['n'], 1) for r in x), default=0) if x else m

    if re.match(r'^You can select one of the following options', t, re.I):
        # exclusive alternatives → one selector whose choices are net packages (what is removed has n < 0)
        alts = []
        for sub in choices:
            p = alternative_package(sub, resolve, sizes_counts, base_by_size)
            if p is None:
                return None
            alts.append(p)
        keys, packages = pack(alts)
        return {'type': 'swap', 'exclusive': True, 'replaces': [], 'choices': [''] + keys, 'packages': packages} if keys else None

    # single model (or a named model) swaps
    m = re.match(rf'^{COND}{OWNER} (?P<x>.+?) can be replaced with:? ?(?P<y>.*)$', t)
    if not m:
        m = re.match(rf'^{COND}(?P<n1>\d+|One|one) (?P<o2>.+?)(?: (?:not )?equipped with [^,]+?)? can replace (?:their|its) (?P<x>.+?) with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        if not keys:
            return None
        opt = {'type': 'swap', 'replaces': items_of(m.group('x'), resolve), 'choices': [''] + keys, 'packages': packages}
        if m.groupdict().get('min'):
            opt['minModels'] = int(m.group('min'))
        owner = m.groupdict().get('o1') or m.groupdict().get('o2')
        if owner and owner.lower() not in ('model', 'models', 'one model'):
            opt['owner'] = owner
        return opt

    # all models at once
    m = re.match(r'^All models in this unit can each have their (?P<x>.+?) replaced with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        return {'type': 'swap', 'scope': 'all', 'replaces': items_of(m.group('x'), resolve), 'choices': [''] + keys, 'packages': packages} if keys else None
    m = re.match(r'^All models in this unit can each be equipped with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        return {'type': 'toggle', 'scope': 'all', 'gives': keys[0], 'packages': packages, 'replaces': [], 'maxBySize': by_size(lambda mm, c: 1)} if keys else None

    # per-model pools
    pool = [
        (r'^Any number of models can each have their (?P<x>.+?) replaced with (?P<y>.*)$', 'items'),
        (r'^Any number of (?P<t>.+?) can each (?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'type'),
        (r'^For every (?P<per>\d+) models in this unit, (?:up to )?(?P<k>\w+) (?P<t>.+?)(?: equipped with [^,]+?)? can (?:each )?(?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'per'),
        (r"^For every (?P<per>\d+) models in this unit, (?:up to )?(?P<k>\w+) (?P<t>.+?)'s (?P<x>.+?) can be replaced with (?P<y>.*)$", 'per'),
        (r'^Up to (?P<k>\w+) (?P<t>.+?) can (?:each )?(?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'upto'),
        (r'^(?P<k>\d+|Two|two|Three|three|Four|four) (?P<t>.+?) can each (?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'upto'),
    ]
    for pat, kind in pool:
        m = re.match(pat, t)
        if not m:
            continue
        x = items_of(m.groupdict().get('x') or m.groupdict().get('x2') or '', resolve)
        keys, packages = pack(targets(m.group('y')))
        if not keys:
            return None
        opt = {'type': 'pool', 'replaces': x, 'choices': keys, 'packages': packages}
        if kind == 'items':
            opt['maxBySize'] = by_size(lambda mm, c: count_items(mm, x))
        elif kind == 'type':
            opt['maxBySize'] = by_size(lambda mm, c: min(count_of(m.group('t'), c, mm), count_items(mm, x) if x else mm))
            opt['owner'] = m.group('t')
        elif kind == 'per':
            per, k = int(m.group('per')), num(m.group('k'))
            opt['maxBySize'] = by_size(lambda mm, c: (mm // per) * k)
            opt['owner'] = m.group('t')
        else:
            opt['maxBySize'] = by_size(lambda mm, c: num(m.group('k')))
            opt['owner'] = m.group('t')
        each = max_each(notes, sizes_counts) if footnote else None
        if each:
            opt['maxEachBySize'] = each
        return opt

    # add-ons
    adds = [
        (r'^Any number of models can (?:each )?be equipped with (?P<y>.*)$', 'all'),
        (r'^For every (?P<per>\d+) models in this unit, (?P<k>\w+) (?P<t>.+?)(?: equipped with [^,(]+?)? can (?:each )?be equipped (?:with )?(?P<y>.*)$', 'per'),
        (r'^Any number of (?P<t>.+?) can (?:each )?be equipped with (?P<y>.*)$', 'type'),
        (rf'^{COND}(?:This model|it|one model|The (?P<o1>.+?)|(?P<k>\d+|One|one) (?P<t>.+?))(?: (?:not )?equipped with [^,(]+?)? can (?:each )?be equipped (?:with )?(?P<y>.*)$', 'one'),
    ]
    for pat, kind in adds:
        m = re.match(pat, t)
        if not m:
            continue
        # how many models the option covers, for a unit of mm models with type counts c
        if kind == 'all':
            def per_model(mm, c): return mm
        elif kind == 'per':
            def per_model(mm, c): return (mm // int(m.group('per'))) * num(m.group('k'))
        elif kind == 'type':
            def per_model(mm, c): return count_of(m.group('t'), c, mm)
        else:
            def per_model(mm, c): return num(m.groupdict().get('k') or '1')
        up =re.match(r'^up to (\w+) of the following(?:,? (and can|but cannot) take duplicates)?:?$', m.group('y').strip(), re.I)
        if up:
            # "can be equipped with up to two of the following, and can take duplicates: …" → per-model picks
            k = num(up.group(1))
            keys, packages = pack([items_of(re.sub(r'\(.*?\)', '', c), resolve) for c in choices])
            if not keys:
                return None
            opt = {'type': 'pool', 'replaces': [], 'choices': keys, 'packages': packages,
                   'maxBySize': by_size(lambda mm, c: k * per_model(mm, c))}
            if up.group(2) and up.group(2).lower().startswith('but'):
                opt['maxEachBySize'] = by_size(lambda mm, c: per_model(mm, c))
            single = {key: by_size(lambda mm, c: per_model(mm, c)) for key, c in zip(keys, choices)
                      if re.search(r'cannot take duplicates of this', c, re.I)}
            if single:
                opt['maxEachChoice'] = single
        else:
            qty = re.match(r'^up to (\w+) (.+)$', m.group('y').strip(), re.I)
            y = re.sub(r'\(.*?\)|\[.*?\]', '', qty.group(2) if qty else m.group('y'))
            k = num(qty.group(1)) if qty else 1
            tg = [[{**x, 'n': 1} for x in items_of(y, resolve)]] if qty else targets(y)
            keys, packages = pack(tg)
            if not keys:
                return None
            if re.match(r'^(?:one|1) of the following', y.strip(), re.I) and kind == 'one':
                opt = {'type': 'swap', 'replaces': [], 'choices': [''] + keys, 'packages': packages}
            else:
                opt = {'type': 'toggle', 'replaces': [], 'gives': keys[0], 'packages': packages,
                       'maxBySize': by_size(lambda mm, c: k * per_model(mm, c))}
        if m.groupdict().get('min'):
            opt['minModels'] = int(m.group('min'))
        owner = m.groupdict().get('t') or m.groupdict().get('o1')
        if owner and owner.lower() not in ('model', 'models', 'model in this unit'):
            opt['owner'] = owner
        return opt
    return None


def alternative_package(text, resolve, sizes_counts, base_by_size):
    """One alternative of an exclusive choice → net package: "one model's lasgun is replaced with 1 laspistol, and
    one model's lasgun is replaced with 1 missile launcher and 1 laspistol" or a regular option text."""
    t = text.replace('’', "'")
    clauses = re.findall(r"(?:(?:one|\d+) model's|their) (.+?) (?:is|are) replaced with (.+?)(?=, and |\. |\.$|$)", t)
    if clauses:
        out = []
        for x, y in clauses:
            out += [{'item': r['item'], 'n': -r['n']} for r in items_of(x, resolve)] + items_of(y, resolve)
        return out
    opt = parse_option(text, [], resolve, sizes_counts, base_by_size)
    if not opt or len(opt['choices']) != (2 if opt['type'] == 'swap' else 1):
        return None
    key = opt['choices'][-1]
    k = max([int(v) for v in opt.get('maxBySize', {}).values()] or [1]) if opt['type'] == 'pool' else 1
    return [{'item': r['item'], 'n': -r['n'] * k} for r in opt['replaces']] + \
           [{'item': x['item'], 'n': x['n'] * k} for x in opt['packages'][key]]


def expand_conditional(options):
    """'If this unit contains 10 models:' followed by whole option sentences → one option per sentence, each with
    the condition ("If this unit contains 10 models, 1 Vespid Stingwing can replace …")."""
    out = []
    for i, o in enumerate(options):
        m = re.match(r'^If this unit contains (\d+) models:?$', o['text'].strip())
        if m and o['choices'] and all(re.search(r'\bcan\b', c) for c in o['choices']):
            out += [(f'o{i + 1}{chr(97 + k)}', {'text': f'If this unit contains {m.group(1)} models, {c.strip()}', 'choices': []})
                    for k, c in enumerate(o['choices'])]
        else:
            out.append((f'o{i + 1}', o))
    return out


def bearer_weapons(text, resolve):
    """Weapons in "The bearer is equipped with 1 drone burst cannon and …" (not "the following ranged weapon")."""
    m = re.search(r'[Tt]he bearer is equipped with (?!the following)(.+?)(?: and the bearer|\.|$)', text)
    return [x for x in items_of(m.group(1), resolve) if not x['item'].startswith('gear:')] if m else []


def gear_weapons(unit, resolve, faction_gear):
    """{gear id: [{item, n}]} for wargear that gives weapons: datasheet wargear abilities ("The bearer is equipped
    with 1 drone burst cannon …") and faction-wide wargear (T'au drones), whose ability and weapons are copied
    into the unit."""
    out = {}
    for a in unit.get('wargearAbilities', []):
        items = bearer_weapons(a['text']['en'], resolve)
        if items:
            out[gear_id(a['name']['en'])] = items
    used = {i for s in unit['sizes'] for i in s.get('loadout', {})} | \
           {x['item'] for o in unit.get('wargear', []) for p in o['packages'].values() for x in p}
    own = {gear_id(a['name']['en']) for a in unit.get('wargearAbilities', [])}
    for gid, g in (faction_gear or {}).items():
        if gid not in used or gid in own:
            continue
        unit.setdefault('wargearAbilities', []).append({'name': g['name'], 'text': g['text'], 'faction': True})
        ids = []
        for w in g['weapons']:
            wid = f"{gid.removeprefix('gear:')}-{w['id']}"
            if wid not in {x['id'] for x in unit['weapons']}:
                unit['weapons'].append({**w, 'id': wid, 'name': {'en': f"{w['name']['en']} ({g['name']['en']})"}, 'gear': gid})
            ids.append({'item': wid, 'n': 1})
        if ids:
            out[gid] = ids
    return out


def ability_weapons(unit, resolve):
    """Weapons given by an ability: "… its Shas'ui model is equipped with the support turret weapon"."""
    out = []
    for a in unit.get('abilities', []):
        for m in re.finditer(r'is equipped with the (.+?) weapon', a['text']['en']):
            out += [x for x in items_of(m.group(1), resolve) if not x['item'].startswith('gear:')]
    return out


def build(unit, model_sizes, global_weapons=(), faction_gear=None):
    """Add sizes[].loadout and wargear (new schema) to an imported unit. Returns the list of option
    texts that could not be structured."""
    resolve = make_resolver([w['id'] for w in unit['weapons']], global_weapons)
    raw_options = expand_conditional(unit.get('wargearOptions', []))
    alts = parse_composition(unit.get('composition', []))
    # "1 model | 85, 2 models | 105" for a single model that "can be equipped with 1 Tidewall defence platform":
    # the add-on counts as the extra model, so the bigger size includes it and the option goes away
    top = max((sum(p[1] for p in alt) for alt in alts), default=0)
    addon = None
    if top and max(model_sizes) > top:
        for oid, o in raw_options:
            m = re.match(r"^This model can be equipped with 1 (.+?)\.?$", o['text'].strip())
            if m and not o['choices']:
                addon = (oid, m.group(1))
                unit['composition'] = unit.get('composition', []) + [f'0-{max(model_sizes) - top} {m.group(1)}']
                alts = parse_composition(unit['composition'])
                raw_options = [x for x in raw_options if x[0] != oid]
                break
    sizes_counts = {m: type_counts(alts, m) for m in model_sizes}
    base = {m: base_loadout(unit.get('equipped', []), sizes_counts[m], m, resolve) for m in model_sizes}
    if addon:
        for m in model_sizes:
            if m > top:
                for x in items_of(f'{m - top} {addon[1]}', resolve):
                    base[m][x['item']] = base[m].get(x['item'], 0) + x['n']
    names = {w['id']: w['name']['en'] for w in unit['weapons']}
    types = {w['id']: w['type'] for w in unit['weapons']}

    def item_name(i):
        return names.get(i.removesuffix('-melee').removesuffix('-ranged')) or names.get(i) or \
            i.removeprefix('gear:').replace('-', ' ').capitalize()

    def pkg_label(p):
        merged = {}
        for x in p:  # net quantities; only what is gained is named
            if not x['item'].endswith(('-melee', '-ranged')) or x['item'] in names:
                merged[x['item']] = merged.get(x['item'], 0) + x['n']
        return ' + '.join(f'{n}× {item_name(i)}' if n > 1 else item_name(i) for i, n in merged.items() if n > 0)

    options, unparsed = [], []
    for oid, o in raw_options:
        opt = parse_option(o['text'], o['choices'], resolve, sizes_counts, base, unit.get('wargearNotes', []))
        if not opt:
            unparsed.append(o['text'])
            continue
        if opt.get('owner', '').lower() in ('model', 'models'):
            opt.pop('owner')
        for r in opt['replaces']:
            if r['item'] in ('gear:ranged-weapon', 'gear:melee-weapon'):
                kind = r['item'].split(':')[1].split('-')[0]
                pool = {i: c for b in base.values() for i, c in b.items() if types.get(i) == kind}
                if pool:
                    r['item'] = max(pool, key=pool.get)
        opt['labels'] = {k: pkg_label(p) for k, p in opt['packages'].items()}
        replaced = pkg_label(opt['replaces']) if opt['replaces'] else ''
        if opt.get('owner'):
            opt['owner'] = opt['owner'].strip()
        owner = f"{opt['owner']}: " if opt.get('owner') else ''
        if opt['type'] == 'toggle':
            label = {'en': f"{owner}add {opt['labels'][opt['gives']]}", 'es': f"{owner}añadir {opt['labels'][opt['gives']]}"}
        elif opt['type'] == 'pool' and not opt['replaces']:
            label = {'en': f'{owner}add', 'es': f'{owner}añadir'}
        elif opt['type'] == 'pool':
            label = {'en': f'{owner}replace {replaced}', 'es': f'{owner}sustituir {replaced}'}
        elif opt.get('exclusive'):
            label = {'en': 'Choose one option', 'es': 'Elige una opción'}
            opt['labels'][''] = '—'
        else:
            label = {'en': f'{owner}{replaced or "optional"}', 'es': f'{owner}{replaced or "opcional"}'}
            opt['labels'][''] = replaced or '—'
        if opt.get('scope') == 'all':
            label = {'en': label['en'] + ' (all models)', 'es': label['es'] + ' (todos los modelos)'}
        options.append({'id': oid, 'label': label, **opt})

    # footnotes that limit combinations; the app checks them when validating the list
    notes = ' '.join(unit.get('wargearNotes', []))
    if re.search(r'cannot have duplicates of these pieces of wargear', notes):
        starred = {x['item'] for _, o in raw_options for c in o['choices'] if '*' in c for x in items_of(c, resolve)}
        if starred:
            unit['uniqueGear'] = sorted(starred)
            for o in options:
                if o['type'] == 'pool' and not o['replaces']:
                    single = {k: {str(mm): mm for mm in model_sizes} for k, pk in o['packages'].items()
                              if any(x['item'] in starred for x in pk)}
                    if single:
                        o['maxEachChoice'] = {**o.get('maxEachChoice', {}), **single}
    both = re.search(r'No model can be equipped with both (?:an? )?(.+?) and (?:an? )?(.+?)(?: at the same time)?\.', notes)
    if both:
        pair = [items_of(both.group(k), resolve) for k in (1, 2)]
        if all(len(x) == 1 for x in pair):
            unit['exclusiveGear'] = [[pair[0][0]['item'], pair[1][0]['item']]]

    # the equipment list names some profiles differently from the weapon table (Krootox Rampagers: "hunting blades;
    # Rampager fists" for "Close combat weapon" and "Krootox fists"): when every unknown item is carried by the whole
    # unit and as many weapons are never mentioned anywhere, those weapons are the ones carried
    gear_ab = {gear_id(a['name']['en']) for a in unit.get('wargearAbilities', [])}
    mentioned = {i for b in base.values() for i in b} | {x['item'] for o in options for p in o['packages'].values() for x in p}
    granted = {x['item'] for x in ability_weapons(unit, resolve)} | \
              {x['item'] for a in unit.get('wargearAbilities', []) for x in bearer_weapons(a['text']['en'], resolve)}
    unused = [w['id'] for w in unit['weapons'] if w['id'] not in mentioned and w['id'] not in granted
              and not re.search(r'-(melee|ranged)$', w['id'])]
    for m, b in base.items():
        unknown = [i for i in b if i.startswith('gear:') and i not in gear_ab]
        if unknown and len(unknown) == len(unused) and len({b[i] for i in unknown}) == 1:
            n = b[unknown[0]]
            for i in unknown:
                del b[i]
            for w in unused:
                b[w] = n

    unit['wargear'] = options
    unit['sizes'] = [{**s, 'loadout': base.get(s['models'], {})} for s in unit['sizes']]
    unit['loadout'] = sorted({i for b in base.values() for i in b})
    gw = gear_weapons(unit, resolve, faction_gear)
    if gw:
        unit['gearWeapons'] = gw
    aw = ability_weapons(unit, resolve)
    if aw:
        unit['abilityWeapons'] = aw
    return unparsed
