# Army Forge (wh_army)

Warhammer 40,000 11th edition army list builder: a personal, non-commercial university project. It is a static
vanilla-JS app (ES modules, no build step, no dependencies) served by `server.py`. All game data is imported from
Wahapedia with the scripts in `tools/`. The UI and all game texts exist in Spanish and English.

- **The user writes in Spanish: always reply in Spanish.** Code, comments and commit messages are in English.
- The goal is to load every faction. Never delete a faction.
- Detailed process docs: [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md) (adding a faction, step by step) and
  [docs/RECURSOS.md](docs/RECURSOS.md) (sources and tools). Keep them in sync when a process changes.

## Run

```sh
./serve.sh                       # http://localhost:8000 (python3 server.py [port] [--armies DIR])
```

`server.py` serves the app and saves each list as `armies/<name>-<id>.json`. File names are transliterated
(`Tiránidos 2000` → `tiranidos-2000-<id>.json`) and the `file` path is computed on read, not stored. `armies/` is
gitignored. After changing `server.py` the user must restart `./serve.sh`; after JS/CSS changes, reload with Cmd+Shift+R.

## Python

- `python3` on this machine is **PyPy**: Pillow/pypdf/pymupdf do not build on it. Use a CPython venv for the tools:
  `/usr/bin/python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt`. Scripts without dependencies
  (`check_app.py`, `translations.py`) run with plain `python3`.
- Under PyPy, `open(p, 'w').write(...)` is not flushed until the process exits: use `with open(...)` when a script
  writes and then re-reads a file.
- Wahapedia pages are cached in `.cache/wahapedia/` (`--refresh` re-downloads).

## Layout

```
index.html, css/styles.css, i18n/{es,en}.json      UI shell, styles, UI strings
js/data.js       loads index/edition/factions (on demand, promise-cached); merges a Chapter with its parent
js/rules.js      points, loadouts (loadoutCounts), validation, leaders/support, enhancements eligibility
js/render.js     builder views; js/overview.js army view (tabs, printable); js/home.js home + faction picker
js/main.js       routing (#/, #/list/<id>, #/list/<id>/view), actions, drag & drop; js/store.js lists + saving
data/editions/11th.json                 battle sizes and recruitment rules (Onslaught values unconfirmed)
data/editions/11th.i18n.es.json         core stratagems + texts shared by several factions + glossary "terms"
data/factions/index.json                factions: alliance (imperium/chaos/xenos), color, unit/detachment counts,
                                        "parent" for a Space Marine Chapter
data/factions/<f>/                      faction.json, units.json, weapons.json, points.json, rules.json,
                                        stratagems.json, images.json, i18n.es.json, emblem.svg
tools/                                  importers, audit and checks (see below)
```

## Conventions

- **No compatibility layers or aliases.** If ids or file names change, migrate saved lists/files directly.
- Only official datasheets: **no Forge World or Warhammer Legends** (they go to `units.json` → `excluded`).
- Data is never hand-written when an importer can produce it. When something is misread, fix the parser
  (`tools/wargear.py` for wargear, `tools/import_wahapedia_datasheets.py` for the page), not the data, so the fix
  applies to every faction.
- Game texts are stored in English; Spanish comes from `i18n.es.json` dictionaries keyed by the English text.
  UPPERCASE keywords stay in English. Translations are our own (unofficial); use GW Spanish terminology
  ("modelo", "fuerza inicial", "chequeo de acobardamiento", "PM", "dentro del alcance de combate", "No Hay Dolor",
  "Despliegue Rápido", weapon abilities in brackets in Spanish: `[IMPACTOS LETALES]`).
- Unit pictures are store URLs in `images.json` (never local files). Get them only with `tools/store_images.py`,
  which opens a **visible** Chrome (the user solves captchas). Never scrape image search engines, never download from
  the warhammer.com CDN directly and never work around site protections.
- Don't kill processes that aren't ours (e.g. Okta Verify listens on port 8769). Test servers: use a free port,
  stop them afterwards.
- Don't commit unless the user asks.

## Adding a faction (summary of docs/NUEVA-FACCION.md)

```sh
.venv/bin/python tools/bootstrap_faction.py <wahapedia-id> --alliance xenos --color "#hex"   # faction.json, index entry
.venv/bin/python tools/import_wahapedia_datasheets.py <f> --list                              # core / legends / fw
.venv/bin/python tools/import_wahapedia_datasheets.py <f> --all                               # datasheets + points
.venv/bin/python tools/audit_units.py <f>                                                     # must be 0 errors
.venv/bin/python tools/import_wahapedia_rules.py <f>                                          # rules.json, stratagems
.venv/bin/python tools/store_images.py <f> <warhammer.com en-GB store URL>                    # images.json
.venv/bin/python tools/pdf_vector_icon.py <datasheet.pdf> 0 data/factions/<f>/emblem.svg --bbox 290,295,362,357 --mono
python3 tools/translations.py pending   →  translate .cache/translations/<f>.tsv  →  translations.py apply …
python3 tools/check_app.py <f>                                                                # must be 0 failures
```

Review after each step (details in the doc):
- `faction.json` enhancement `requires`/`excludes` (alternatives with `/` or "or"; exclusions only right after
  "only"), `type: upgrade`, `grantsLead`, detachment `tags` (one detachment per tag), `unitAbilities`.
- Pages that also list another faction's datasheets (Chaos Daemons → HERETIC ASTARTES): `bootstrap_faction.py
  --other-faction "HERETIC ASTARTES"` (stored in `faction.json` → `wahapedia.otherFactions`) so `--all` skips them.
- Datasheets where the player picks a keyword ("must select one of the keywords below", Daemon Prince): parsed as
  `keywordChoice` → a required swap option whose choices add `keywords`; the list is invalid until one is chosen.
- `CHECK` lines of the importer (unparsed wargear options, unknown leader targets).
- Images: unmatched units and dubious matches; some units are only sold in boxes and stay without picture.
- Emblem: rendered check. PDFs come from the user's public Drive folder (`tools/download_drive_folder.py`,
  root id `11h099eTJtxY0yShZ8wcGNpngwmo8b0f3`, Imperium/Chaos/Xenos subfolders). Logos not in the PDFs:
  `tools/image_to_emblem.py <logo.png> <emblem.svg>` (traces a one-colour picture into the diamond frame).
- Spanish faction name in `faction.json` and `index.json`.

Translations: delegate them to the `traductor` subagent (`.claude/agents/traductor.md`: GW Spanish terminology,
file format, self-checks). Run `pending`, split the `.tsv` into blocks of ~150-200 lines and launch one `traductor`
per block in parallel, each writing `.cache/translations/<f>.es.<N>.txt`; pass the names already decided (units,
detachments) as fixed names. The agents never apply: you align the "names coined" of their reports, apply each
block with `translations.py apply`, check `pending` is 0 and run `check_app.py`.
`python3 tools/translations.py lookup "<English words>"` shows how a term was translated before.

## Space Marines and Chapters

Wahapedia keeps all Marines on one page with chapter masks (`data-f="CH:<hex>"`). In the app, `space-marines` is the
base faction (`bootstrap_faction.py space-marines --chapter-bit 10`) and each Chapter is a child
(`--source space-marines --chapter "Blood Angels"`, `--chapter-bit 40` for Deathwatch) with `"parent"` in `index.json`.

- A Chapter stores **only its own data**; `js/data.js` (`mergeChapter`) and `tools/factions.py` (`merge`) combine it
  with the parent the same way. Keep both in sync.
- Chapter versions of generic datasheets (different points or leader targets) are kept as overrides with the same id;
  identical ones are dropped by the importer (`drop_inherited`).
- `faction.json` of a Chapter: `parentExcludes` (rules/detachments/units/unitKeywords it cannot use) and
  `keywordRules` (keywords its rules give, e.g. DEATHWING), parsed from its army rules.
- Python tools that need the faction as the app sees it use `tools/factions.py` (`load`, `raw`, `refresh_counts`).
- Translations of texts the parent has belong to the parent's `i18n.es.json`.

## Data model notes

- Wargear (`tools/wargear.py` docstring): `sizes[].loadout`, options `swap`/`pool`/`toggle` with `replaces`,
  `packages`, `maxBySize`, `needs`/`needsNot` (shown disabled while unmet), `scope: all`, `owner`; `gearWeapons`,
  `abilityWeapons`, `uniqueGear`, `exclusiveGear`. Optional "0-1" model types and companion models become toggles.
- Points (`points.json`): `units`, `unitsExtraCopies` (dearer from the Nth copy), `wargearCosts` (charged per piece
  carried, default equipment included — literal reading of Wahapedia, unconfirmed), `enhancements`, `unitAbilities`.
- 11th edition SUPPORT datasheets: `leader.support: true`; a bodyguard takes its Leader(s) plus one Support unit.
- Detachment `unitAbilities` (Pantheon of Woe): automatic abilities for named datasheets with extra points.
- Saved lists store ids only; on load the app drops unknown units and invalid wargear choices.

## Checks (run before reporting a task as done)

```sh
.venv/bin/python tools/audit_units.py                       # every faction: 0 errors, 0 warnings
for f in $(python3 -c "import json;print(' '.join(f['id'] for f in json.load(open('data/factions/index.json'))['factions']))"); do
  .venv/bin/python tools/import_wahapedia_datasheets.py $f --all --check; done   # "no changes" everywhere
python3 tools/translations.py pending                       # 0 pending everywhere
python3 tools/check_app.py                                  # 0 failures (ES + EN, ~2 min per language)
```

- `audit_units.py` compares each imported unit with its cached datasheet (weapons, abilities, composition, loadout,
  reachable weapons, options, costs) and checks the `index.json` counts and alliance.
- `--check` re-imports with the current code without writing: after changing an importer or `wargear.py`, previous
  factions must report `no changes`.
- `check_app.py` builds a test list per faction in a temp folder, runs the server with `--armies`, and walks the
  home, faction picker, builder, every datasheet and every overview tab in headless Chrome: JS errors, missing
  units, `undefined`/`NaN`, text in the wrong language. `--keep` leaves the dumps.
- For UI changes, also take a headless Chrome screenshot of the affected view and look at it.

## Known gaps

- Allies (Deathwatch Support, Imperial Agents, Freeblades, the HERETIC ASTARTES units of the Chaos Daemons Shadow
  Legion) are not modelled.
- Onslaught (3000 pts) limits in `11th.json` are unconfirmed; wargear costs on default equipment unconfirmed.
- Some units have no store picture (sold only in boxes or not sold).
- Chapter emblems of Ultramarines, Imperial Fists, Iron Hands, Raven Guard, Salamanders and White Scars are hand-drawn
  SVGs; the user may provide official logos to trace with `image_to_emblem.py`.
