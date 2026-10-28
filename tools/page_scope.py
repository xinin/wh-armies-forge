"""Which part of a Wahapedia faction page belongs to one of our factions.

Most factions are a whole page of their own (PageScope). Wahapedia keeps every Space Marine on one page and marks
army rules, detachments, cost rows and leader targets with data-f="CH:<hex mask>", one bit per Chapter:
    ChapterBase   the base army (bit 10: what the page shows without a Chapter): generic rules and datasheets
    Chapter       one Chapter (its own bit): only what the base army does not have; the parent's content without
                  the Chapter's bit is what the Chapter cannot use (faction.json → parentExcludes)
A page can also list datasheets of other factions (Chaos Daemons: the HERETIC ASTARTES units of the Shadow Legion);
their faction keywords are the scope's other_factions and they are never imported.

faction.json → "wahapedia" stores the scope, so every importer reads the page the same way:
    {"faction": <page>, "chapter": <CHAPTER KEYWORD>, "chapterBit": <hex>, "otherFactions": [keyword…]}
(none for a faction that is a whole page of its own and has no other factions' datasheets).
"""
import json
import re
from pathlib import Path

from faction_model import Source

FACTIONS = Path(__file__).resolve().parent.parent / 'data' / 'factions'
ASTARTES = 'ADEPTUS ASTARTES'


def mask(attrs):
    """The Chapter bits of a data-f attribute ("CH:801"), or None for content shown to every Chapter."""
    m = re.search(r'CH:([0-9a-f]+)', attrs or '')
    return int(m.group(1), 16) if m else None


class PageScope:
    """A whole Wahapedia faction page: every rule, detachment and datasheet row on it is the faction's."""
    chapters = False    # the page is split by Chapter masks
    is_chapter = False  # a Chapter of a base faction (index.json "parent")
    chapter = None      # CHAPTER keyword
    bit = None

    def __init__(self, page, other_factions=()):
        self.page = page  # Wahapedia faction slug
        self.other_factions = list(other_factions)

    def keeps(self, attrs):
        """Is this army rule or detachment (by its data-f attribute) the faction's?"""
        return True

    def denies(self, attrs):
        """Is it parent content the faction cannot use?"""
        return False

    def datasheet(self, html):
        """A datasheet page without the rows (costs, leader targets) shown only for other Chapters."""
        return html

    def classify(self, tag, faction_keywords):
        """core / legends / fw → 'other factions' for a core datasheet of a faction in other_factions."""
        return 'other factions' if tag == 'core' and faction_keywords & set(self.other_factions) else tag

    def faction_keywords(self, name):
        """Faction keywords (whole phrases) dropped from requirements ("ASTRA MILITARUM INFANTRY model only" →
        INFANTRY); the page's own faction keyword ("If your Army Faction is HERETIC ASTARTES") is added by the caller."""
        return {name.upper()}

    def config(self, faction_id):
        """faction.json → wahapedia (None: nothing to store: the faction is the page of the same name)."""
        return Source(self.page, other_factions=self.other_factions) if self.other_factions or self.page != faction_id else None


class ChapterBase(PageScope):
    """The base army of a page split by Chapters: what the page shows with `bit` (10: no Chapter selected)."""
    chapters = True

    def __init__(self, page, bit, other_factions=()):
        super().__init__(page, other_factions)
        self.bit = bit

    def keeps(self, attrs):
        m = mask(attrs)
        return m is None or bool(m & self.bit)

    def datasheet(self, html):
        def row(m):
            return m.group(0) if int(m.group(2), 16) & self.bit else ''
        return re.sub(r'<(tr|li) class="clFlCH" data-f="CH:([0-9a-f]+)[^"]*">.*?</\1>', row, html, flags=re.S)

    def allowed(self):
        """Faction keywords of the datasheets it imports: the generic ones, and the Chapter's own."""
        return {ASTARTES}

    def classify(self, tag, faction_keywords):
        if tag == 'core' and not faction_keywords <= self.allowed():
            return 'other chapters'
        return super().classify(tag, faction_keywords)

    def faction_keywords(self, name):
        return super().faction_keywords(name) | {ASTARTES}

    def config(self, faction_id):
        return Source(self.page, chapter_bit=f'{self.bit:x}', other_factions=self.other_factions)


class Chapter(ChapterBase):
    """One Chapter: the content with its bit that the base army (parent_bit) does not have."""
    is_chapter = True

    def __init__(self, page, chapter, bit, parent_bit, other_factions=()):
        super().__init__(page, bit, other_factions)
        self.chapter = chapter
        self.parent_bit = parent_bit

    def keeps(self, attrs):
        m = mask(attrs)
        return m is not None and bool(m & self.bit) and not m & self.parent_bit

    def denies(self, attrs):
        m = mask(attrs)
        return m is not None and bool(m & self.parent_bit) and not m & self.bit

    def allowed(self):
        return {ASTARTES, self.chapter}

    def config(self, faction_id):
        return Source(self.page, chapter=self.chapter, chapter_bit=f'{self.bit:x}', other_factions=self.other_factions)


def make_scope(page, chapter=None, bit=None, other_factions=(), html=None):
    """The scope of a faction read from `page`: a Chapter (chapter: its name on the page, "Space Wolves"; its bit
    comes from the page's filter header when not given), a base army (bit only) or a whole page."""
    if not chapter:
        return ChapterBase(page, bit, other_factions) if bit is not None else PageScope(page, other_factions)
    if bit is None:
        hm = re.search(rf'DetFilterGroupHeader[^>]*data-f="[^"]*CH:([0-9a-f]+)[^"]*">\s*{re.escape(chapter)}\s*<', html or '')
        if not hm:
            raise ValueError(f'chapter "{chapter}" not found on {page}')
        bit = int(hm.group(1), 16) & ~1  # without bit 1
        if bin(bit).count('1') != 1:
            raise ValueError(f'the filter header of "{chapter}" covers several Chapters (CH:{hm.group(1)}): give --chapter-bit')
    parent = FACTIONS / page / 'faction.json'
    if not parent.exists():
        raise ValueError(f'create the base faction first: bootstrap_faction.py {page} --chapter-bit <hex>')
    parent_bit = int(json.loads(parent.read_text())['wahapedia']['chapterBit'], 16)
    return Chapter(page, chapter.upper(), bit, parent_bit, other_factions)


def scope_of(faction_id):
    """The scope stored in data/factions/<faction_id>/faction.json."""
    cfg = json.loads((FACTIONS / faction_id / 'faction.json').read_text()).get('wahapedia', {})
    bit = int(cfg['chapterBit'], 16) if cfg.get('chapterBit') else None
    return make_scope(cfg.get('faction', faction_id), cfg.get('chapter'), bit, cfg.get('otherFactions', []))
