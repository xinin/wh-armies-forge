"""Create the data folder of a new faction from its Wahapedia (11th edition) page.

Usage:
    python3 tools/bootstrap_faction.py <wahapedia-faction-slug> --alliance xenos [--color "#8a1c1c"] [--html FILE] [--force]
    python3 tools/bootstrap_faction.py space-marines --chapter-bit 10
    python3 tools/bootstrap_faction.py space-wolves --source space-marines --chapter "Space Wolves"

Which part of the page is the faction's is its scope (tools/page_scope.py). Chapters: Wahapedia's space-marines
page marks content with data-f="CH:<hex mask>", one bit per Chapter. --chapter-bit 10 makes the base army: what the
page shows without a Chapter (generic army rules and detachments). --source/--chapter makes a Chapter of that base
faction (index.json "parent", see tools/factions.py): only the army rules and detachments of that Chapter alone,
plus what it cannot use from the parent ("parentExcludes": parent rules/detachments without its bit, and "Your army
cannot include …" in its rules) and the keywords its rules give ("keywordRules": "The following friendly ADEPTUS
ASTARTES units have DEATHWING: …"). The Chapter's bit comes from its filter header (<div class="DetFilterGroupHeader"
data-f="CH:801">Space Wolves</div>, without bit 1), or from --chapter-bit when the header covers several
(Deathwatch: 40). faction.json records the scope in "wahapedia" for the other importers.

--force regenerates faction.json (and enhancement points) of an existing faction, keeping its name; units/images
are kept. The Wahapedia options it was created with (--source, --chapter, --chapter-bit, --other-faction) are read
from faction.json → wahapedia, so `bootstrap_faction.py <faction> --force` works for every faction. --check does the
same in memory and lists what would change (nothing, when the importer has not changed): no faction.json is
hand-edited.

    e.g. python3 tools/bootstrap_faction.py adeptus-custodes --color "#b8923a"

Writes data/factions/<slug>/ (faction.json is built as a tools/faction_model.py Faction):
    faction.json   army rule (+ items: named entries listed in it, Astra Militarum Orders) + detachments (DP cost,
                   tags, rule summary, keywordGrants, minUnits) + enhancements (requirements, type)
                   + unitAbilities: abilities listed with points under the detachment's own heading instead of
                   "Enhancements" (Pantheon of Woe: "Necrodermal Binding Abilities"); each named datasheet gets its
                   ability automatically and costs that much more
    units.json     empty, with an "excluded" list for Forge World / Legends datasheets
    weapons.json   empty (datasheets carry their own weapon profiles)
    points.json    enhancement (and unitAbilities) points; unit points are added by import_wahapedia_datasheets.py
    images.json    empty (fill with tools/store_images.py)
and registers the faction in data/factions/index.json (with its detachment count; import_wahapedia_datasheets.py
keeps the unit count).
Next steps: import_wahapedia_datasheets.py --all, import_wahapedia_rules.py (see docs/NUEVA-FACCION.md).
"""
import argparse
import difflib
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_wahapedia_rules import BASE, clean, enhancements_pos, fetch, key, rule_lines, section_at, slug, strip_errata, strip_fluff  # noqa: E402
from factions import refresh_counts  # noqa: E402
from faction_model import (Detachment, Enhancement, Faction, ForbiddenChoice, Item, KeywordGrant,  # noqa: E402
                           KeywordRule, MinUnits, ParentExcludes, PointsCap, Rule, Text, UnitAbility, UnitKeywordChoice)
from page_scope import make_scope  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def chapter_rules(rules):
    """What a Chapter's army rules say about the units of the army:
    'Your army cannot include any ADEPTUS ASTARTES PSYKER models'          → unitKeywords [['PSYKER']]
    'Your army cannot include the following datasheets from Codex: Space Marines: GLADIATOR LANCER; …'
    'Your army cannot include the following ADEPTUS ASTARTES units: SCOUT SQUAD units. …'   → units [ids]
    'The following friendly ADEPTUS ASTARTES units have DEATHWING: TERMINATOR units. LAND RAIDER, … units.'
                                                                           → keywordRules (keyword groups as words)
    Returns (ParentExcludes, [KeywordRule])."""
    excludes, keyword_rules = ParentExcludes(), []
    for r in rules:
        t = re.sub(r'\s+', ' ', r.text.en)
        for m in re.finditer(r'cannot include any (?:ADEPTUS ASTARTES )?([A-Z][A-Z \-]+?) models', t):
            excludes.unit_keywords.append(m.group(1).split())
        for m in re.finditer(r'cannot include the following datasheets from [^:]+:[^:]+:\s*([^.]+)\.', t):
            excludes.units.extend(slug(n) for n in m.group(1).split(';') if n.strip())
        for m in re.finditer(r"cannot include the following ADEPTUS ASTARTES units:\s*((?:[A-Z][A-Z’' \-]+ units\.\s*)+)", t):
            excludes.units.extend(slug(n) for n in re.findall(r"([A-Z][A-Z’' \-]+?) units\.", m.group(1)))
        for m in re.finditer(r'The following friendly ADEPTUS ASTARTES units have ([A-Z]+):\s*((?:[^.:]+ units\.\s*)+)', t):
            groups = [item.split() for sentence in re.findall(r'([^.]+?) units\.', m.group(2))
                      for item in re.split(r',\s*|\s+and\s+', sentence.strip()) if item.strip()]
            keyword_rules.append(KeywordRule(m.group(1), groups))
    return excludes, keyword_rules


def singular(word):
    return re.sub(r'IES$', 'Y', word) if word.endswith('IES') else re.sub(r'S$', '', word)


def detachment_tags(page):
    """Tags over the detachment headings (<div class="H2Unique">UNIQUE: SHIELD HOST</div><h2 id="Dread-Host">): an army
    can only take one detachment with the same tag. → {key(heading id): ['SHIELD HOST']}"""
    return {key(m.group(2)): [t.strip() for t in clean(m.group(1)).replace('UNIQUE:', '').split(',') if t.strip()]
            for m in re.finditer(r'<div class="H2Unique">(.*?)</div>\s*<h2 id="([^"]+)"', page, re.S)}


NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
KW = r"[A-Z][A-Z’'-]*(?: [A-Z][A-Z’'-]*)*"
NAMES = rf"{KW}(?:(?:, | and | or |/){KW})*"


def without_faction(names, faction_keywords):
    """The words of a keyword list without the faction keywords (whole phrases: "CHAOS LORD" keeps CHAOS when the
    faction keyword is HERETIC ASTARTES, even if the page is "Chaos Space Marines")."""
    names = names.upper()
    for kw in sorted(faction_keywords, key=len, reverse=True):
        names = re.sub(rf"(?<![\w’'-]){re.escape(kw)}(?![\w’'-])", ' ', names)
    return names.split()


def detachment_keywords(rule, faction_keywords):
    """Keywords a detachment rule gives to units, and the units it requires (faction keywords dropped; a group of
    words matches a unit with all of them in its keywords or name, as in requirements()).
    'WAR DOG units from your army have the BATTLELINE keyword.'      → KeywordGrant('BATTLELINE', [['WAR', 'DOG']])
    'MAWLOC and TRYGON units from your army have the BURROWER …'     → one group per name: [['MAWLOC'], ['TRYGON']]
    '… select three WAR DOG units from your army. … those units have the CHARACTER keyword.' (or "select one or more
    TITANIC units … to gain the CHARACTER keyword", "up to 2 TRYGON models … The selected units gain …")
                                                                     → KeywordGrant(…, chosen=True, max=3): the player
                                                                       picks them (no max for "one or more")
    'Your army must include three or more WAR DOG units.'           → MinUnits([['WAR', 'DOG']], 3)
    Returns ([KeywordGrant], [MinUnits])."""
    def groups(names):
        return [without_faction(alt, faction_keywords) for alt in re.split(r', | and | or |/', names)]

    def count(s):
        n = re.sub(r'^up to ', '', s)
        return int(n) if n.isdigit() else NUMBERS.get(n)

    grants, min_units = [], []
    for m in re.finditer(rf"({NAMES}) (?:units|models) from your army (?:have|gain) the ({KW}) keyword", rule):
        grants.append(KeywordGrant(m.group(2), groups(m.group(1))))
    for m in re.finditer(rf"select (one or more|up to \w+|\w+) ({NAMES}) (?:units|models) from your army"
                         rf"(?: to gain the ({KW}) keyword)?", rule):
        kw = m.group(3) or next(iter(re.findall(rf"(?:[Tt]hose|[Tt]he selected) units (?:have|gain) the ({KW}) keyword",
                                                rule[m.end():m.end() + 200])), None)
        if kw:
            n = None if m.group(1) == 'one or more' else count(m.group(1))
            grants.append(KeywordGrant(kw, groups(m.group(2)), chosen=True, max=n))
    for m in re.finditer(rf"Your army must include (\w+) or more ({NAMES}) units", rule):
        min_units.append(MinUnits(groups(m.group(2)), count(m.group(1))))
    return grants, min_units


def unit_keyword_choice(rule, faction_keywords):
    """A keyword each unit must take (Pactbound Zealots "Marks of Chaos"):
    '… if that unit is not an EPIC HERO and does not already have one of the following keywords, you must select one
    for that unit and note it on your Army Roster: KHORNE. TZEENTCH, NURGLE, SLAANESH, CHAOS UNDIVIDED.'
    'You cannot select the KHORNE keyword for a PSYKER unit.'                 → forbidden
    'A CHARACTER/EPIC HERO unit can only be attached to a unit if both units share the same keyword from the list
    above.'                                                                  → same_for_attached
    Returns a UnitKeywordChoice or None."""
    m = re.search(rf"if that unit is not an? ({KW}) and does not already have one of the following keywords, you must "
                  rf"select one for that unit[^:]*:\s*({KW}(?![a-z])(?:[.,] (?:or )?{KW}(?![a-z]))*)", rule)
    if not m:
        return None
    return UnitKeywordChoice(
        [k.strip() for k in re.split(r'[.,] (?:or )?', m.group(2))], [without_faction(m.group(1), faction_keywords)],
        [ForbiddenChoice(f.group(1), [without_faction(f.group(2), faction_keywords)])
         for f in re.finditer(rf"You cannot select the ({KW}) keyword for an? ({KW}) unit", rule)],
        bool(re.search(r'can only be attached to a unit if both units share the same keyword', rule)))


def points_cap(rule, faction_keywords):
    """'… you can include any of the following units in your army …: KHORNE BERZERKERS (see World Eaters) …
    The combined points value of such units … Incursion: Up to 250 pts Strike Force: Up to 500 pts …' → PointsCap."""
    m = re.search(r'you can include any of the following units in your army[^:]*:\s*(.+?)\s*The combined points value '
                  r'of such units[^:]*:\s*(.+)', rule, re.S)
    sizes = re.findall(r'(Incursion|Strike Force|Onslaught): Up to (\d+) pts', m.group(2)) if m else []
    if not sizes:
        return None
    units = [without_faction(re.sub(r'\(.*?\)', '', u), faction_keywords) for u in re.split(r'\n|,', m.group(1))]
    return PointsCap([u for u in units if u], {slug(s): int(p) for s, p in sizes})


def rule_items(rule_html):
    """Named entries listed inside an army rule (Astra Militarum Orders: <p class="impact18">Move! Move! Move!</p>
    <p>[characteristic badge] Add 3" to the Move characteristic…</p>) → (rule html without them, [Item])."""
    items = []

    def take(m):
        items.append(Item(Text(clean(m.group(1))),
                          Text(clean(re.sub(r'<div class="dsCharWrap".*?</div></div></div></div>', '', m.group(2), flags=re.S)))))
        return ''
    body = re.sub(r'<p[^>]*class="impact18">(.*?)</p>\s*<p>(.*?)</p>', take, rule_html, flags=re.S)
    return body, items


def summary(text, limit=320):
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + '…'


def requirements(body, faction_keywords):
    """Who can take an enhancement, from the start of its text. Faction keywords are dropped.
    'INFANTRY OFFICER model only.'              → requires [['INFANTRY', 'OFFICER']]
    'GHOSTKEEL BATTLESUIT/PATHFINDER TEAM …'     → one alternative per '/' (or ' or ')
    'Kroot War Shaper model only.'               → the datasheet name: [['KROOT', 'WAR', 'SHAPER']]
    '… only (excluding KROOT SHAPER models).'    → excludes [['KROOT', 'SHAPER']] (only right after "only": later
                                                   exclusions are about the units the rule affects); also before it
                                                   ('… model (excluding DAMNED models) only'), and with "and"
    '… model with the Deep Strike ability only' → ability 'Deep Strike'
    Returns (requires, excludes, ability)."""
    def groups(names, requires=False):
        alts = re.split(r'/| or | and ', names)
        # "INFANTRY/MOUNTED THOUSAND SONS PSYKER": what follows the faction keyword applies to every alternative
        last = alts[-1].upper()
        for kw in faction_keywords:
            tail = re.search(rf"(?<![\w’'-]){re.escape(kw)} (.+)$", last)
            if len(alts) > 1 and tail:
                alts = [a if a is alts[-1] else f'{a} {tail.group(1)}' for a in alts]
                break
        out = [without_faction(alt, faction_keywords) for alt in alts]
        # "THOUSAND SONS or LORD OF CHANGE model only": any model of the faction can take it
        if requires and any(not words for words in out):
            return []
        return [words for words in out if words]
    name = r"[A-Z][\w'’-]*(?:(?:[ /]| or | and )[A-Z][\w'’-]*)*"
    body = re.sub(r'^Friendly ', '', body)
    m = re.match(rf"^({name})\s+(?:(?:model|unit)s?\s+)?(?:\(excluding ({name}) (?:model|unit)s?\)\s+)?"
                 rf"(?:with the ([A-Z][\w ]*?) ability\s+)?only\b(?:\s*\(excluding ({name}) (?:model|unit)s?\))?", body)
    if not m:
        return [], [], None
    exclusions = m.group(2) or m.group(4)
    return groups(m.group(1), requires=True), groups(exclusions) if exclusions else [], m.group(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('faction')
    ap.add_argument('--color', default='#6b7d4a')
    ap.add_argument('--alliance', choices=['imperium', 'chaos', 'xenos'],
                    help='group of the faction picker (a new faction needs it; a Chapter takes its parent\'s)')
    ap.add_argument('--html')
    ap.add_argument('--force', action='store_true', help='regenerate an existing faction (its Wahapedia options are '
                                                        'read from faction.json → wahapedia)')
    ap.add_argument('--check', action='store_true', help='regenerate in memory and list what would change; writes nothing')
    ap.add_argument('--source', help='Wahapedia faction page the Chapter belongs to (space-marines)')
    ap.add_argument('--chapter', help='Chapter name as shown on that page ("Space Wolves")')
    ap.add_argument('--other-faction', action='append', metavar='KEYWORD',
                    help='faction keyword of datasheets on the page that belong to another faction (repeatable; kept '
                         'in faction.json → wahapedia.otherFactions, the datasheet importer skips them)')
    ap.add_argument('--group', help='faction the new one is shown with in the faction picker (index.json "group": the '
                                    'Chaos Legions with chaos-space-marines); its data is its own')
    ap.add_argument('--chapter-bit', help='hex bit of the Chapter (or 10: the base army without Chapter) in the CH masks')
    args = ap.parse_args()

    fdir = ROOT / 'data' / 'factions' / args.faction
    if (fdir / 'faction.json').exists() and not (args.force or args.check):
        sys.exit(f'{fdir}/faction.json already exists (use --force to overwrite)')
    old = json.loads((fdir / 'faction.json').read_text()) if (fdir / 'faction.json').exists() else {}
    # options of an existing faction: the ones it was created with, unless given again
    cfg = old.get('wahapedia', {})
    source = args.source or cfg.get('faction') or args.faction
    chapter = args.chapter or (old['name']['en'] if cfg.get('chapter') else None)
    chapter_hex = args.chapter_bit or cfg.get('chapterBit')
    page = Path(args.html).read_text() if args.html else fetch(f'{BASE}/factions/{source}/')
    try:
        scope = make_scope(source, chapter, int(chapter_hex, 16) if chapter_hex else None,
                           args.other_faction or cfg.get('otherFactions', []), page)
    except ValueError as e:
        sys.exit(str(e))

    title = re.search(r'<title>(.*?)</title>', page, re.S)
    name = re.sub(r'\[.*?\]', '', clean(title.group(1))).split('|')[0].split('–')[0].strip() if title else args.faction.replace('-', ' ').title()
    if chapter:
        name = chapter
    faction_keywords = scope.faction_keywords(name)

    # army rule: first heading after "Army Rules" (an <h3> in most factions, its own <h2> in some); the other army
    # rules ("Shadow in the Warp", "Librarius", "Curse of the Wulfen"…) go to extraRules, and a Chapter only has
    # extra rules (the army rule is its parent's). "FAQ" / "Errata" headings are not rules.
    a = page.find('id="Army-Rules"')
    army_html = page[page.find('</h2>', a) + 5:page.find('<h2', a + 20)]
    heads = list(re.finditer(r'<(h[23])[^>]*>(.*?)</\1>(.*?)(?=<h[23]|\Z)', army_html, re.S))
    if not heads:  # the army rule is its own <h2> right after "Army Rules" (Imperial Knights)
        army_html = page[page.find('<h2', a + 20):]
        heads = list(re.finditer(r'<(h2)[^>]*>(.*?)</\1>(.*?)(?=<h[23]|\Z)', army_html, re.S))[:1]
    rules, denied_rules, prev = [], [], 0
    for h in heads:
        masks = re.findall(r'data-f="([^"]*)"', army_html[prev:h.start()])
        prev = h.start(3)
        if re.fullmatch(r'(FAQ|Errata)( / (FAQ|Errata))?', clean(h.group(2))):
            continue
        body, items = rule_items(h.group(3))
        rule = Rule(Text(clean(h.group(2))), Text(clean(strip_fluff(body))), items)
        if scope.keeps(masks[-1] if masks else ''):
            rules.append(rule)
        elif scope.denies(masks[-1] if masks else ''):
            denied_rules.append(rule.name.en)
    if scope.is_chapter:
        army_rule, extra_rules = None, rules
    else:
        army_rule = rules[0] if rules else Rule(Text('Army rule'), Text(''))
        extra_rules = rules[1:]

    det_tags = [(tag, n, dp) for tag, n, dp in re.findall(r'(<[^<>]*data-det-name="([^"]+)" data-dp-base="(\d+)"[^<>]*>)', page)]
    attrs_of = lambda tag: re.search(r'data-f="([^"]*)"', tag).group(1) if 'data-f=' in tag else ''  # noqa: E731
    dets_dp = [(n, dp) for tag, n, dp in det_tags if scope.keeps(attrs_of(tag))]
    fk = re.search(r"If your Army Faction is ([A-Z][A-Z’' -]+?)[,.]", army_rule.text.en if army_rule else '')
    if fk:
        faction_keywords.add(fk.group(1))
    for r in ([army_rule] if army_rule else []) + extra_rules:
        r.points_cap = points_cap(r.text.en, faction_keywords)
    denied_dets = sorted({slug(clean(n)) for tag, n, dp in det_tags if scope.denies(attrs_of(tag))})
    heads = [(m.start(), m.group(1)) for m in re.finditer(r'<h2[^>]*id="([^"]+)"', page)]
    detachments, enh_points, ability_points = [], {}, {}
    tags = detachment_tags(page)
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
        e_pos = enhancements_pos(sec)
        rule_text = rule_lines(section_at(sec, r_pos.start() if r_pos else None))
        # "LEGIONES DAEMONICA units from your army gain the SHADOW LEGION keyword": every unit of the faction has it
        # in this detachment, so it is not a requirement of its enhancements
        det_keywords = set(faction_keywords)
        for m in re.finditer(r"([A-Z][A-Z’' ]+) units from your army gain the ([A-Z][A-Z’' ]+?) keyword", ' '.join(rule_text)):
            if m.group(1).strip() in faction_keywords:
                det_keywords.add(m.group(2))
        # tags over the heading, or only in the rule ("This detachment has the WAR DOGS tag and cannot be taken with
        # another WAR DOGS detachment": Chaos Knights appendix detachments)
        own_tags = list(tags.get(key(det_name), []))
        for tag in re.findall(r"has the ([A-Z][A-Z’' ]+?) tag and cannot be taken", ' '.join(rule_text)):
            if not any(singular(tag) == singular(o) for o in own_tags):  # AUXILIARY / AUXILIARIES
                own_tags.append(tag)
        kw_grants, min_units = detachment_keywords('\n'.join(rule_text), faction_keywords)
        det = Detachment(did, int(dp), own_tags, Text(det_name),
                         Rule(Text(rule_text[0] if rule_text else det_name), Text(summary(' '.join(rule_text[1:])))),
                         keyword_grants=kw_grants, min_units=min_units,
                         unit_keyword_choice=unit_keyword_choice('\n'.join(rule_text), faction_keywords))
        ens_html = section_at(sec, e_pos)
        automatic = not ens_html.startswith('id="Enhancements')
        for m in re.finditer(r'<ul class="EnhancementsPts"><li><span>(.*?)</span>\s*<span>(\d+) pts</span></li></ul>(.*?)(?=<ul class="EnhancementsPts"|\Z)', ens_html, re.S):
            upgrade = 'EnhUpgrade' in m.group(1)
            ename = re.sub(r'\(Aura\)|UPGRADE', '', clean(re.sub(r'<span class="EnhUpgrade">.*?</span>', '', m.group(1)))).strip()
            # "SUPPORT: OPHYDIAN DESTROYERS, …" (or LEADER:): the bearer can also be attached to those datasheets
            grants = re.search(r'<span class="kwb">(?:LEADER|SUPPORT):</span>(.*?)</div>', m.group(3), re.S)
            body = strip_errata(clean(strip_fluff(m.group(3).replace(grants.group(0), '') if grants else m.group(3))))
            eid = slug(ename)
            if eid in enh_points or eid in ability_points:  # same name in two detachments
                eid = f'{eid}-{did}'
            requires, excludes, ability = requirements(body, det_keywords)
            if automatic and requires:
                ability_points[eid] = int(m.group(2))
                det.unit_abilities.append(UnitAbility(eid, slug(' '.join(requires[0])), Text(ename), Text(summary(body, 200))))
                continue
            enh_points[eid] = int(m.group(2))
            det.enhancements.append(Enhancement(
                eid, requires, Text(ename), Text(summary(body, 200)), excludes,
                [slug(d) for d in clean(grants.group(1)).split(',') if d.strip()] if grants else [],
                'upgrade' if upgrade else None, ability))
        detachments.append(det)
        print(f'{did:28} {dp} DP  enhancements={len(det.enhancements)}' +
              (f'  unit abilities={len(det.unit_abilities)}' if det.unit_abilities else ''))

    src = f'{BASE}/factions/{source}/'
    faction = Faction(args.faction, Text(**old['name']) if old.get('name') else Text(name, name), src,
                      army_rule, extra_rules, scope.config(args.faction), detachments=detachments)
    if scope.is_chapter:
        excludes, faction.keyword_rules = chapter_rules(extra_rules)
        excludes.rules, excludes.detachments = denied_rules, denied_dets
        faction.parent_excludes = excludes or None
    new_faction = json.dumps(faction.to_json(), ensure_ascii=False, indent=1) + '\n'
    # --force only regenerates faction.json and the enhancement points: imported units, unit points
    # and images are never overwritten
    points_path = fdir / 'points.json'
    new_points = None
    if points_path.exists():
        pts = json.loads(points_path.read_text())
        pts['enhancements'] = enh_points
        if ability_points:
            pts['unitAbilities'] = ability_points
        new_points = json.dumps(pts, ensure_ascii=False, indent=1) + '\n'
    if args.check:
        changes = [(p, text) for p, text in ((fdir / 'faction.json', new_faction), (points_path, new_points))
                   if text is not None and (not p.exists() or p.read_text() != text)]
        for p, text in changes:
            diff = list(difflib.unified_diff(p.read_text().splitlines() if p.exists() else [], text.splitlines(), lineterm='', n=0))
            print(f'CHANGE {p.relative_to(ROOT)}: {sum(1 for d in diff[2:] if d[:1] in "+-")} lines')
            for line in [d for d in diff[2:] if d[:1] in '+-'][:12]:
                print(f'    {line[:150]}')
        print(f'{args.faction}: {"no changes" if not changes else f"{len(changes)} files would change"}')
        return
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / 'faction.json').write_text(new_faction)
    if new_points is not None:
        points_path.write_text(new_points)
    for fname, content in {
        'units.json': {'_note': 'Datasheets. Points live in points.json.', 'excluded': {'_note': 'Forge World and Warhammer Legends datasheets: never imported.', 'ids': []}, 'units': []},
        'weapons.json': {'_note': 'Shared weapon profiles for hand-written datasheets; imported datasheets carry their own.', 'weapons': {}},
        'points.json': {'_note': 'Edit when a new Munitorum Field Manual comes out.', 'version': datetime.date.today().isoformat(), 'source': src,
                        'verified': ['all-enhancements'], 'units': {}, 'enhancements': enh_points,
                        **({'unitAbilities': ability_points} if ability_points else {})},
        'images.json': {'_note': 'Unit picture URLs (webstore). Fill with tools/store_images.py or from the app.', 'units': {}},
    }.items():
        if not (fdir / fname).exists():
            (fdir / fname).write_text(json.dumps(content, ensure_ascii=False, indent=1) + '\n')

    index_path = ROOT / 'data' / 'factions' / 'index.json'
    index = json.loads(index_path.read_text())
    entry = next((f for f in index['factions'] if f['id'] == args.faction), None)
    if not entry:
        if not scope.is_chapter and not args.alliance:
            sys.exit('a new faction needs --alliance imperium|chaos|xenos')
        entry = {'id': args.faction, 'name': faction.name.to_json(), 'edition': '11th', **({} if scope.is_chapter else {'alliance': args.alliance}),
                 'path': args.faction, 'color': args.color}
        # a Chapter goes after its parent and the parent's other Chapters
        family = [i for i, f in enumerate(index['factions']) if source in (f['id'], f.get('parent'))] if scope.is_chapter else []
        index['factions'].insert(family[-1] + 1 if family else len(index['factions']), entry)
    if scope.is_chapter:
        entry['parent'] = source
    if args.group:
        entry['group'] = args.group
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    refresh_counts(source if scope.is_chapter else args.faction)
    print(f'{name}: {len(detachments)} detachments → {fdir}')


if __name__ == '__main__':
    main()
