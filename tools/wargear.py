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
        maxModels                     only up to that unit size ("If this unit contains only 3 models, …")
        scope     'all'               the swap/toggle applies to every model at once
        maxEachBySize {models: n}     pools: the same choice cannot be taken more than n times (footnotes)
        needs     [{item, n}]     only while the unit carries that ("If this model is equipped with 1 Neo-volkite
                                  Pistol, it can be equipped with 1 Storm Shield")
        keywords  {key: KEYWORD}  a choice also gives the model that keyword; with required: true one must be made
                                  ("Daemonic Allegiance": KHORNE + torrent of burning blood…); name = the choice's name
        needsNot  [{item, n}]     only while the unit does not carry that ("If this model is not equipped with a
                                  tachyon arrow, it can be equipped with 1 resurrection orb")
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
import unicodedata

NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'a': 1, 'an': 1}


def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()  # "Kâhl" → "kahl"
    s = s.lower().replace('’', '').replace('‘', '').replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def num(word):
    return int(word) if word.isdigit() else NUMBERS.get(word.lower(), 1)


def singular(word):
    if word.endswith('men'):
        return word[:-3] + 'man'
    if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'os')):  # "Chaos icon" keeps its s
        return word[:-1]
    return word


def type_key(name):
    """'Shock Trooper Sergeants' / 'Shock Trooper Sergeant – EPIC HERO' → 'shock trooper sergeant'"""
    name = re.sub(r'\s*–.*$|\*|\bmodels?\b', '', name.replace('’', "'").replace('‘', "'")).strip().lower()
    return ' '.join(singular(w) for w in name.split())


# ---------- composition: model counts per type and unit size ----------

def parse_composition(entries):
    """['1 Tempestor', '4-9 Tempestus Scions'] → [[(1, 1, 'tempestor'), (4, 9, 'tempestus scion')]]
    Entries that each contain ' and <number>' (or ', <number>') are alternatives ("1 Sergeant and 9 Troopers" /
    "2 … and 18 …", "1 Jakhal Pack Leader, 1 Dishonoured and 8 Jakhals");
    other ' and's are part of the model name ("Deathwatch Veteran with Heavy Thunder Hammer and Bolt Pistol")."""
    split = lambda e: re.split(r',\s*(?=\d)|\s+and\s+(?=\d)', e)  # noqa: E731
    def part(text):
        m = re.match(r'^(\d+)(?:-(\d+))?\s+(.+)$', text.strip())
        return (int(m.group(1)), int(m.group(2) or m.group(1)), type_key(m.group(3))) if m else None

    entries = [e for e in entries if e.strip() and e.strip().upper() != 'OR']
    if len(entries) > 1 and all(len(split(e)) > 1 for e in entries):
        alts = [[part(p) for p in split(e)] for e in entries]
    else:
        alts = [[part(p) for e in entries for p in split(e)]]
    return [[p for p in alt if p] for alt in alts if any(alt)]


def type_counts(alternatives, models):
    """{type: count} for a unit of `models` models. A size below the sum of the minimums (Decimus Kill Team: 5 models
    of "1, 1, 1-2, 1-2, 1-2, 1-2") leaves out the last ranged types."""
    for alt in alternatives:
        lo, hi = sum(p[0] for p in alt), sum(p[1] for p in alt)
        if models < lo and len(alternatives) == 1:
            short = lo - models
            alt = list(alt)
            for i in reversed(range(len(alt))):
                a, b, t = alt[i]
                if short and a > 0 and b > a:
                    alt[i] = (a - 1, b, t)
                    short -= 1
            lo = sum(p[0] for p in alt)
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
        if ends:
            return max(ends, key=len)
        # or by one word too many at the end (GW typo "Bolt Rifle Fire" for "Bolt Rifle")
        starts = [i for c in cands for i in known if c.startswith(i + '-') and one_word(c[len(i) + 1:]) and '-' in i]
        return max(starts, key=len) if starts else None

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
        m = re.match(r'^(.*?)\s+(?:is|are)\s+(?:additionally\s+)?equipped with:?\s*(.*)$', sentence.strip().rstrip('.'), re.S)
        if not m:
            continue
        k = count_of(m.group(1), counts, models)
        for item in m.group(2).split(';'):
            for x in items_of(item, resolve):
                out[x['item']] = out.get(x['item'], 0) + x['n'] * k
    return out


# ---------- options ----------

FOLLOWING = r'(?:one|1) of the following(?: options)?'
NO_DUPLICATES = r'\s*\((?:duplicates are not allowed|you cannot select the same option more than once)\)'
OWNER = r"(?:This model's|(?P<n1>\d+|One|one) (?:other )?(?P<o2>[^']+?)'s|The (?P<o1>[^']+?)(?:'s|(?<=s)')|(?P<o3>one model)'s)"
COND = r"(?:If this unit contains (?P<only>only )?(?P<min>\d+) models, )?"


def size_limits(m):
    """minModels / maxModels of an option from its "If this unit contains (only) N models, …" condition."""
    if not m.groupdict().get('min'):
        return {}
    n = int(m.group('min'))
    return {'minModels': n, **({'maxModels': n} if m.groupdict().get('only') else {})}


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
    t = re.sub(r"^(?:1|One|one) of this model's ", "This model's ", t)
    t = re.sub(r'^For every (\d+) models in the unit,', r'For every \1 models in this unit,', t)  # "in the unit" (Seraphim)
    t = t.replace('-pattem ', '-pattern ').replace('::', ':')  # GW typos ("Autoch-pattem combi-bolter", "following::")  # "1 of this model's Helbrute fists can be replaced" 
    t = re.sub(r"\.\s*(?:That|This) model's .+? cannot be replaced\.?$", '.', t)  # restriction already implied by the option
    # "(duplicates are not allowed)": each choice at most once in the unit
    no_duplicates = bool(re.search(NO_DUPLICATES, t))
    t = re.sub(NO_DUPLICATES, '', t)
    # "can be equipped with 1 havoc launcher or can replace 1 combi-bolter with 1 havoc launcher": an add-on
    t = re.sub(r'^(This model can be equipped with (.+?)) or can replace .+? with \2\.?$', r'\1.', t)

    def targets(y):
        y = y.strip().rstrip('.').strip()
        if not y or re.match(rf'^{FOLLOWING}:?$', y, re.I):
            return [items_of(c, resolve) for c in choices]
        both = re.match(rf'^(.+?) and {FOLLOWING}:?$', y, re.I)
        if both:  # "1 axe of Khorne and one of the following: 1 bloodflail / 1 lash of Khorne"
            return [items_of(both.group(1), resolve) + items_of(c, resolve) for c in choices]
        inline = re.match(rf'^{FOLLOWING}:\s*(.+)$', y, re.I)
        if inline:  # "one of the following: 1 Power Fist, 1 Power Weapon"
            return [items_of(c, resolve) for c in re.split(r',\s*(?=\d+ )', inline.group(1))]
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

    def replaced(x):
        # "1 model's gauss scalpel or tesla caster can be replaced": the default one is replaced (an option that
        # swaps it on every model applies after this one, see loadoutCounts in js/rules.js)
        items = items_of(x, resolve)
        if ' or ' in x and any(i['item'].startswith('gear:') for i in items):
            for alt in x.split(' or '):
                alt_items = items_of(alt, resolve)
                if alt_items and all(any(i['item'] in b for b in base_by_size.values()) for i in alt_items):
                    return alt_items
        return items

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
        m = re.match(rf"^{COND}(?:This model|The (?P<o1>.+?)|(?P<n1>\d+|One|one) (?P<o2>.+?)) can have (?:their|its) (?P<x>.+?) replaced with:? ?(?P<y>.*)$", t)
    if not m:
        m = re.match(rf'^{COND}(?P<n1>\d+|One|one) (?P<o2>.+?)(?: (?:not )?equipped with [^,]+?)? can replace (?:their|its) (?P<x>.+?) with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        if not keys:
            return None
        opt = {'type': 'swap', 'replaces': replaced(m.group('x')), 'choices': [''] + keys, 'packages': packages}
        opt.update(size_limits(m))
        owner = m.groupdict().get('o1') or m.groupdict().get('o2')
        if owner and owner.lower() not in ('model', 'models', 'one model'):
            opt['owner'] = owner
        return opt

    # all models at once
    m = re.match(r'^All (?:[\w-]+ )*?models in this unit can each have their (?P<x>.+?) replaced with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        return {'type': 'swap', 'scope': 'all', 'replaces': items_of(m.group('x'), resolve), 'choices': [''] + keys, 'packages': packages} if keys else None
    m = re.match(r'^All models in this unit can each be equipped with (?P<y>.*)$', t)
    if m:
        keys, packages = pack(targets(m.group('y')))
        return {'type': 'toggle', 'scope': 'all', 'gives': keys[0], 'packages': packages, 'replaces': [], 'maxBySize': by_size(lambda mm, c: 1)} if keys else None

    # "Up to 2 Chaos Bikers can each have their combi-bolter replaced with 1 combi-weapon, or can be equipped with one of
    # the following: …": each of those models takes one choice; only the first one replaces equipment
    m = re.match(r'^Up to (?P<k>\w+) (?P<t>.+?) can each have their (?P<x>.+?) replaced with (?P<y1>[^,]+), or can be '
                 r'equipped with (?P<y2>.*)$', t)
    if m:
        removed = [{'item': r['item'], 'n': -r['n']} for r in items_of(m.group('x'), resolve)]
        keys, packages = pack([items_of(m.group('y1'), resolve) + removed] + targets(m.group('y2')))
        return {'type': 'pool', 'replaces': [], 'choices': keys, 'packages': packages, 'owner': m.group('t'),
                'maxBySize': by_size(lambda mm, c: num(m.group('k')))} if keys else None

    # per-model pools
    pool = [
        (r'^Any number of models can each have their (?P<x>.+?) replaced with (?P<y>.*)$', 'items'),
        (r'^Any number of (?P<t>.+?) can each (?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'type'),
        (r"^(?:Each|Every) (?P<t>.+?)'s (?P<x>.+?) can be replaced with (?P<y>.*)$", 'type'),  # "Each Retributor's heavy bolter …"
        (r'^For every (?P<per>\d+) models in this unit, (?:up to )?(?P<k>\w+) (?P<t>.+?)(?: (?:that is (?:not )?)?equipped with [^,]+?)? can (?:each )?(?:have (?:their|its) (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'per'),
        (r"^For every (?P<per>\d+) models in this unit, (?:up to )?(?P<k>\w+) (?P<t>.+?)'s? (?P<x>.+?) can (?:each )?be replaced with (?P<y>.*)$", 'per'),
        (rf'^{COND}[Uu]p to (?P<k>\w+) (?:additional )?(?P<t>.+?) can (?:each )?(?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'upto'),
        (r'^(?P<k>\d+|Two|two|Three|three|Four|four) (?P<t>.+?) can each (?:have their (?P<x>.+?) replaced with|replace their (?P<x2>.+?) with) (?P<y>.*)$', 'upto'),
    ]
    for pat, kind in pool:
        m = re.match(pat, t)
        if not m:
            continue
        # "their Autoch-pattern bolter or ion blaster": the one the models carry by default
        x = replaced(m.groupdict().get('x') or m.groupdict().get('x2') or '')
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
        elif no_duplicates:
            opt['maxEachBySize'] = by_size(lambda mm, c: 1)
        opt.update(size_limits(m))
        return opt

    # add-ons; "If this model is equipped with X, it can be equipped with Y" needs X
    needs = None
    nm = re.match(r'^If this model is (?P<neg>not )?equipped with (?P<c>[^,]+), it can be equipped with:? ?(?P<rest>.*)$', t)
    if nm:  # "… equipped with a plasma pistol and a power weapon, it can be equipped with: 1 rod of office"
        needs = ('needsNot' if nm.group('neg') else 'needs', items_of(nm.group('c'), resolve))
        t = 'This model can be equipped with ' + (nm.group('rest') or 'one of the following:')
    adds = [
        (r'^This unit can be equipped with (?P<y>.*)$', 'one'),
        (r'^Any number of models can (?:each )?be equipped with (?P<y>.*)$', 'all'),
        (r'^For every (?P<per>\d+) models in this unit, (?P<k>\w+) (?P<t>.+?)(?: (?:that is (?:not )?)?equipped with [^,(]+?)? can (?:each )?be equipped (?:with )?(?P<y>.*)$', 'per'),
        (r'^For every (?P<per>\d+) models in this unit, this unit can have (?P<y>.*)$', 'per'),
        (r'^Any number of (?P<t>.+?) can (?:each )?be equipped with (?P<y>.*)$', 'type'),
        (r'^Up to (?P<k>\w+) (?P<t>.+?)(?: models)? can (?:each )?be equipped with (?P<y>.*)$', 'one'),  # "Up to 2 Kommando models …"
        (rf'^{COND}(?:This model|it|one model|The (?P<o1>.+?)|(?P<k>\d+|One|one) (?P<t>.+?))(?: (?:that|who) (?:is|are))?(?: (?:not )?equipped with [^,(]+?)? can (?:each )?be equipped (?:with )?(?P<y>.*)$', 'one'),
    ]
    for pat, kind in adds:
        m = re.match(pat, t)
        if not m:
            continue
        # how many models the option covers, for a unit of mm models with type counts c
        if kind == 'all':
            def per_model(mm, c): return mm
        elif kind == 'per':
            def per_model(mm, c): return (mm // int(m.group('per'))) * num(m.groupdict().get('k') or '1')
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
            elif len(keys) > 1:  # "For every 3 models in this unit, 1 model can be equipped with one of the following"
                opt = {'type': 'pool', 'replaces': [], 'choices': keys, 'packages': packages,
                       'maxBySize': by_size(lambda mm, c: k * per_model(mm, c))}
            else:
                opt = {'type': 'toggle', 'replaces': [], 'gives': keys[0], 'packages': packages,
                       'maxBySize': by_size(lambda mm, c: k * per_model(mm, c))}
        opt.update(size_limits(m))
        if needs:
            opt[needs[0]] = needs[1]
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


def companion_split(composition, equipped, tiers):
    """'3-6 Hunting Wolf / 3-6 Wolf Guard Headtaker' costed for 3, 6, 6 and 12 models: the unit is 3-6 of the main
    models, each optionally with one companion (3, 3+3, 6, 6+6). Two sizes with the same model count cannot be told
    apart, so the sizes become the main models only and the companions an option.
    → (main type, companion type, lo, hi) or None. The main type is the one with more equipment."""
    alts = parse_composition(composition)
    if len(alts) != 1 or len(alts[0]) != 2 or len(tiers) != 4:
        return None
    (lo1, hi1, t1), (lo2, hi2, t2) = alts[0]
    if (lo1, hi1) != (lo2, hi2) or list(tiers) != [lo1, 2 * lo1, hi1, 2 * hi1]:
        return None
    def gear(t):
        line = next((e for e in equipped if type_key(re.sub(r'^(?:Every|Each|The)\s+', '', e.split(' is equipped')[0])) == t), '')
        return line.count(';') + 1 if line else 0
    main, comp = (t1, t2) if gear(t1) >= gear(t2) else (t2, t1)
    return main, comp, lo1, hi1


def expand_conditional(options):
    """'If this unit contains 10 models:' (or 'For every 5 models in this unit:') followed by whole option sentences
    → one option per sentence, each with the condition ("If this unit contains 10 models, 1 Vespid Stingwing can
    replace …")."""
    out = []
    for i, o in enumerate(options):
        m = re.match(r'^(If this unit contains \d+ models|For every \d+ models in this unit):?$', o['text'].strip())
        if m and o['choices'] and all(re.search(r'\bcan\b', c) for c in o['choices']):
            out += [(f'o{i + 1}{chr(97 + k)}', {'text': f'{m.group(1)}, {c.strip()}', 'choices': []})
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


def equipped_items(unit, type_name, resolve):
    """Per-model equipment of one model type, from its "… is equipped with:" sentence (None if it has none)."""
    for e in unit.get('equipped', []):
        subject, _, rest = e.partition(' is equipped with')
        if rest and type_key(re.sub(r'^(?:Every|Each|The)\s+', '', subject)) == type_name:
            return [x for part in rest.split(':', 1)[-1].split(';') for x in items_of(part, resolve)]
    return None


def build(unit, model_sizes, global_weapons=(), faction_gear=None):
    """Add sizes[].loadout and wargear (new schema) to an imported unit. Returns the list of option
    texts that could not be structured."""
    resolve = make_resolver([w['id'] for w in unit['weapons']], global_weapons)
    raw_options = expand_conditional(unit.get('wargearOptions', []))
    companions = companion_split(unit.get('composition', []), unit.get('equipped', []), model_sizes)
    if companions:
        main, comp, lo, hi = companions
        model_sizes = [lo, hi]
        unit['sizes'] = [{'models': lo}, {'models': hi}]
        unit['composition'] = [f'{lo}-{hi} {e.split(" ", 1)[1]}' if type_key(e.split(' ', 1)[1]) == main else f'0-{hi} {e.split(" ", 1)[1]}'
                               for e in unit['composition']]
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

    # "Any number of Havocs can each have their Havoc autocannon or Havoc lascannon replaced with …", when the models
    # carry one or the other: one option per weapon (each limited by how many models carry it)
    split = []
    for oid, o in raw_options:
        m = re.match(r'^(Any number of .+? can each have their )(.+?) or (.+?)( replaced with .*)$', o['text'].strip())
        alts = [items_of(m.group(k), resolve) for k in (2, 3)] if m else []
        if alts and all(len(a) == 1 and any(a[0]['item'] in b for b in base.values()) for a in alts):
            split += [(f'{oid}{chr(97 + k)}', {**o, 'text': f'{m.group(1)}{m.group(k + 2)}{m.group(4)}'}) for k in range(2)]
        else:
            split.append((oid, o))
    raw_options = split

    # "For each Helbrute fist this model is equipped with, it can be equipped with one of the following": one option
    # per fist the model can carry (default ones and those other options give), each needing that many fists
    per_item = []
    for oid, o in raw_options:
        m = re.match(r'^For each (.+?) this model is equipped with, it can be equipped with (.*)$', o['text'].strip().rstrip('.'))
        item = items_of(m.group(1), resolve) if m else []
        if len(item) != 1:
            per_item.append((oid, o))
            continue
        i = item[0]['item']
        most = max(b.get(i, 0) for b in base.values()) + sum(
            1 for _, other in raw_options if other is not o and any(i in [x['item'] for x in items_of(c, resolve)] for c in other['choices']))
        per_item += [(f'{oid}{chr(97 + k)}', {**o, 'text': f'This model can be equipped with {m.group(2)}', 'needs': [{'item': i, 'n': k + 1}]})
                     for k in range(most)]
    raw_options = per_item

    def item_name(i):
        return names.get(i.removesuffix('-melee').removesuffix('-ranged')) or names.get(i) or \
            i.removeprefix('gear:').replace('-', ' ').capitalize()

    def pkg_label(p):
        merged = {}
        for x in p:  # net quantities; only what is gained is named
            if not x['item'].endswith(('-melee', '-ranged')) or x['item'] in names:
                merged[x['item']] = merged.get(x['item'], 0) + x['n']
        return ' + '.join(f'{n}× {item_name(i)}' if n > 1 else item_name(i) for i, n in merged.items() if n > 0)

    # the same piece of wargear spelled two ways ("pan spectral scanner" / "panspectral scanner"): its ability's id
    gear_ids = {compact(gear_id(a['name']['en'])): gear_id(a['name']['en']) for a in unit.get('wargearAbilities', [])}
    def canon(item):
        return gear_ids.get(compact(item), item) if item.startswith('gear:') else item
    for b in base.values():
        for i in [i for i in b if canon(i) != i]:
            b[canon(i)] = b.get(canon(i), 0) + b.pop(i)

    options, unparsed = [], []
    for oid, o in raw_options:
        opt = parse_option(o['text'], o['choices'], resolve, sizes_counts, base, unit.get('wargearNotes', []))
        if not opt:
            unparsed.append(o['text'])
            continue
        if o.get('needs'):
            opt['needs'] = o['needs']
        for x in opt['replaces'] + [x for pk in opt['packages'].values() for x in pk]:
            x['item'] = canon(x['item'])
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

    if companions:
        # one companion per main model, for the whole unit: what the companions carry, per model
        comp_line = next(e for e in unit.get('equipped', []) if type_key(re.sub(r'^(?:Every|Each|The)\s+', '', e.split(' is equipped')[0])) == comp)
        items = [x for part in comp_line.split(':', 1)[1].split(';') for x in items_of(part, resolve)]
        name = next(e.split(' ', 1)[1] for e in unit['composition'] if type_key(e.split(' ', 1)[1]) == comp)
        key = '+'.join(x['item'] for x in items)
        options.append({'id': f'o{len(raw_options) + 1}', 'label': {'en': f'{name}: add (all models)', 'es': f'{name}: añadir (todos los modelos)'},
                        'type': 'toggle', 'scope': 'all', 'replaces': [], 'gives': key, 'packages': {key: items},
                        'maxBySize': {str(m): 1 for m in model_sizes}, 'owner': re.sub(r'\s*models?$', '', name),
                        'labels': {key: ' + '.join(item_name(x['item']) for x in items)}})

    kc = unit.get('keywordChoice')
    if kc:
        packages = {o['keyword'].lower().replace(' ', '-'): items_of(o.get('equipment', ''), resolve) for o in kc['options']}
        keys = list(packages)
        effects = {k: o['effect'] for k, o in zip(keys, kc['options']) if o.get('effect')}  # "Khorne: Add 2 to …"
        options.append({'id': f'o{len(raw_options) + 1 + bool(companions)}', 'label': dict(kc['name']), 'name': kc['name'],
                        'type': 'swap', 'required': True, 'replaces': [], 'choices': [''] + keys, 'packages': packages,
                        'keywords': {k: o['keyword'] for k, o in zip(keys, kc['options'])},
                        **({'effects': effects} if effects else {}),
                        'labels': {'': '—', **{k: f"{o['keyword']}: {effects[k]['en'] if k in effects else ' + '.join(item_name(x['item']) for x in packages[k])}"
                                               for k, o in zip(keys, kc['options'])}}})

    # optional model types ("0-1 Chapter Ancient", "0-1 Chapter Champion" with "1-6 Victrix Honour Guard"): the sizes
    # count the main models, so each optional model is a toggle that takes the place of one of them (only the
    # equipment that differs is swapped)
    if not companions and not addon and len(alts) == 1:
        main = max(alts[0], key=lambda p: p[1])
        main_items = equipped_items(unit, main[2], resolve)
        next_id = len(raw_options) + 1 + bool(kc)
        for lo, hi, t in alts[0]:
            items = equipped_items(unit, t, resolve) if lo == 0 and t != main[2] else None
            if not items or not main_items:
                continue
            common = {x['item'] for x in items} & {x['item'] for x in main_items}
            gives = [x for x in items if x['item'] not in common]
            if not gives:
                continue
            key = '+'.join(x['item'] for x in gives)
            name = next(e.split(' ', 1)[1] for e in unit['composition'] if type_key(e.split(' ', 1)[1]) == t)
            options.append({'id': f'o{next_id}',
                            'label': {'en': f'{name}: add', 'es': f'{name}: añadir'}, 'type': 'toggle',
                            'replaces': [x for x in main_items if x['item'] not in common], 'gives': key, 'packages': {key: gives},
                            'maxBySize': {str(m): min(hi, sizes_counts[m].get(main[2], 0)) for m in model_sizes},
                            'owner': re.sub(r'\s*models?$', '', name), 'labels': {key: ' + '.join(item_name(x['item']) for x in gives)}})
            next_id += 1

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
    # an option that names the weapon differently from the weapon table (Chaos Lord: "Astartes chainsword" for the
    # "Astartes chainblade" profile): the only weapon nothing else mentions, if both names start the same way
    in_options = {x['item'] for o in options for p in o['packages'].values() for x in p}
    odd = [i for i in in_options if i.startswith('gear:') and i not in gear_ab and not any(i in b for b in base.values())]
    if len(odd) == 1 and len(unused) == 1 and compact(odd[0].removeprefix('gear:'))[:6] == compact(unused[0])[:6]:
        for o in options:
            for k, p in o['packages'].items():
                for x in p:
                    if x['item'] == odd[0]:
                        x['item'] = unused[0]
                o['labels'][k] = pkg_label(p)
        mentioned.add(unused[0])
        unused = []
    for m, b in base.items():
        unknown = [i for i in b if i.startswith('gear:') and i not in gear_ab]
        if unknown and len(unknown) == len(unused) and len({b[i] for i in unknown}) == 1:
            n = b[unknown[0]]
            for i in unknown:
                del b[i]
            for w in unused:
                b[w] = n
                twin = f'{w}-melee'  # the same name in both tables is one weapon with two profiles (Aeonstave)
                if any(x['id'] == twin for x in unit['weapons']):
                    b[twin] = n

    unit['wargear'] = options
    unit['sizes'] = [{**s, 'loadout': {i: c for i, c in base.get(s['models'], {}).items() if c}} for s in unit['sizes']]
    unit['loadout'] = sorted({i for b in base.values() for i in b})
    gw = gear_weapons(unit, resolve, faction_gear)
    if gw:
        unit['gearWeapons'] = gw
    aw = ability_weapons(unit, resolve)
    # "select up to two different C'tan Powers weapons (see left). Until the end of the phase, this model is equipped
    # with those weapons": the profiles nothing else gives belong to that ability
    if any('is equipped with those weapons' in a['text']['en'] for a in unit.get('abilities', [])):
        aw += [{'item': w, 'n': 1} for w in unused if not any(w in b for b in base.values())]
    if aw:
        unit['abilityWeapons'] = aw
    return unparsed
