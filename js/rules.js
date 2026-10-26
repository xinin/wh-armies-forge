// Army construction rules: points, eligibility and validation. Pure functions over (list, data, edition).
import { t, tr } from './i18n.js';

export const hasKw = (unitDef, kw) => unitDef.keywords.includes(kw);

export function battleSizeOf(list, edition) {
  return edition.battleSizes.find(b => b.id === list.battleSize) ?? edition.battleSizes[1];
}

// Position of this unit among the copies of the same datasheet in the list (0-based).
export const copyIndex = (ru, list) => list.units.filter(u => u.unitId === ru.unitId).findIndex(u => u.uid === ru.uid);

// Is this copy paying the 11th-edition extra cost ("YOUR 3RD+ UNIT COSTS", sometimes from the 2nd)?
export function isExtraCopy(ru, data, list) {
  const def = data.unitsById.get(ru.unitId);
  const size = def?.sizes[ru.sizeIdx];
  return Boolean(list && size?.extraPoints != null && def.extraFrom && copyIndex(ru, list) >= def.extraFrom - 1);
}

export const slugify = str => String(str).toLowerCase().replace(/[’']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
// gear ids are singular ("servo-scribe"), the wargear ability may be plural ("Servo-scribes") or tagged
// ("Command-link Drone (Aura)")
export const gearSlug = name => slugify(name.replace(/\s*\(.*?\)/g, '')).split('-').map(w => w.replace(/s$/, '')).join('-');

/* Equipment counts of a roster unit: the default loadout of its size after the chosen options (per-model options
   first, "all models" swaps last on what is left), plus the weapons given by its wargear (drones) and abilities.
   → { counts: {item: n}, base: {item: n} } (base = the size's default loadout, with what it gives) */
export function loadoutCounts(ru, def) {
  const size = def.sizes[ru.sizeIdx] ?? def.sizes[0];
  const models = size?.models ?? 1;
  const counts = { ...(size?.loadout ?? {}) };
  const add = (c, item, n) => { c[item] = Math.max(0, (c[item] ?? 0) + n); };
  const apply = (opt, key, times) => {
    if (!times) return;
    for (const r of opt.replaces ?? []) add(counts, r.item, -r.n * times);
    for (const x of opt.packages?.[key] ?? []) add(counts, x.item, x.n * times);
  };
  const available = opt => (opt.replaces?.length
    ? Math.min(...opt.replaces.map(r => Math.floor((counts[r.item] ?? 0) / r.n)))
    : models);
  const options = (def.wargear ?? []).filter(o => !(o.minModels && models < o.minModels));
  for (const opt of [...options.filter(o => o.scope !== 'all'), ...options.filter(o => o.scope === 'all')]) {
    const v = ru.wargear?.[opt.id];
    if (opt.needs?.some(x => (counts[x.item] ?? 0) < x.n)) continue; // "if this model is equipped with …"
    if (opt.needsNot?.some(x => counts[x.item])) continue; // "if this model is not equipped with …"
    if (opt.type === 'swap' && v) apply(opt, v, opt.scope === 'all' ? available(opt) : 1);
    if (opt.type === 'pool') for (const [key, n] of Object.entries(v ?? {})) apply(opt, key, Number(n) || 0);
    if (opt.type === 'toggle' && v) apply(opt, opt.gives, opt.scope === 'all' ? available(opt) : Number(v));
  }
  const withGiven = c => {
    const out = { ...c };
    for (const [gear, weapons] of Object.entries(def.gearWeapons ?? {})) {
      for (const w of weapons) if (c[gear]) add(out, w.item, c[gear] * w.n);
    }
    for (const w of def.abilityWeapons ?? []) add(out, w.item, w.n);
    return out;
  };
  return { counts: withGiven(counts), base: withGiven(size?.loadout ?? {}) };
}

// Name of a loadout item: a weapon of the datasheet, or gear ("gear:vox-caster" → its wargear ability name).
export function itemName(def, id) {
  if (!id.startsWith('gear:')) return tr(def.weaponMap.get(id)?.name) || id;
  const g = gearSlug(id.slice(5));
  const ability = [...(def.wargearAbilities ?? []), ...(def.abilities ?? [])].find(a => gearSlug(a.name.en) === g);
  return ability ? tr(ability.name) : id.slice(5).replace(/-/g, ' ').replace(/^./, c => c.toUpperCase());
}

export function unitPoints(ru, data, list = null) {
  const def = data.unitsById.get(ru.unitId);
  const size = def?.sizes[ru.sizeIdx];
  const base = (isExtraCopy(ru, data, list) ? size.extraPoints : size?.points) ?? 0;
  const enh = ru.enhancement ? data.enhancements.get(ru.enhancement)?.points ?? 0 : 0;
  // 11th edition "per <wargear>" costs, for every piece the unit carries
  const costs = def?.wargearCosts ?? {};
  const counts = Object.keys(costs).length ? loadoutCounts(ru, def).counts : {};
  const gear = Object.entries(costs).reduce((sum, [item, pts]) => sum + (counts[item] ?? 0) * pts, 0);
  const abilities = detachmentAbilities(ru, list, data).reduce((sum, a) => sum + a.points, 0);
  return base + enh + gear + abilities;
}

// Abilities a chosen detachment gives to this datasheet, each with its extra cost (Pantheon of Woe: "each NECRONS
// MONSTER unit has the relevant Necrodermal Binding ability … increase the points cost of each of those units")
export const detachmentAbilities = (ru, list, data) => (list?.detachments ?? [])
  .flatMap(id => data.detachmentsById.get(id)?.unitAbilities ?? [])
  .filter(a => a.unit === ru.unitId);

export const listPoints = (list, data) => list.units.reduce((sum, ru) => sum + unitPoints(ru, data, list), 0);

export const detachmentPointsUsed = (list, data) =>
  list.detachments.reduce((sum, id) => sum + (data.detachmentsById.get(id)?.cost ?? 0), 0);

// Max count for a 'pool' or 'toggle' option, scaling with model count when `per` is set.
// How many models can take a pool/toggle option at this unit size (0 when the size doesn't allow it).
export function optionMax(opt, models) {
  if (opt.minModels && models < opt.minModels) return 0;
  return opt.maxBySize?.[models] ?? 1;
}

// Footnote limits such as "you cannot select the same weapon more than once (twice with 20 models)", or of one
// choice ("it cannot take duplicates of this piece of wargear").
export const optionMaxEach = (opt, models, key = null) =>
  Math.min(opt.maxEachBySize?.[models] ?? Infinity, (key && opt.maxEachChoice?.[key]?.[models]) ?? Infinity);

function canBeCharacter(def, list, data) {
  if (hasKw(def, 'CHARACTER')) return true;
  return hasKw(def, 'TITANIC') && list.detachments.some(id => data.detachmentsById.get(id)?.titanicCanBeCharacter);
}

export function enhancementFits(enh, def, list, data) {
  if (enh.type !== 'upgrade') {
    if (!canBeCharacter(def, list, data) || hasKw(def, 'EPIC HERO')) return false;
  }
  // "… (excluding KROOT SHAPER models)"
  if (enh.excludes?.some(group => group.every(kw => kwMatch(def, kw)))) return false;
  if (!enh.requires?.length) return true;
  return enh.requires.some(group => group.every(kw => kwMatch(def, kw)));
}

// Requirements imported from "X Y model only" are split into words; a word also matches when it is part of a
// multi-word keyword ("VON RYAN'S LEAPERS", "VANGUARD INVADER") or is its plural ("STEALTH BATTLESUITS" units).
// The datasheet name counts as a keyword too ("WOLF PRIEST model only": 11th-edition datasheets omit it).
const kwMatch = (def, kw) => {
  const w = normKw(kw);
  return hasKw(def, kw) || kwWords(def).has(w) || (w.endsWith('S') && kwWords(def).has(w.slice(0, -1)));
};
const normKw = kw => kw.toUpperCase().replace(/[’‘]/g, "'");
const kwWordCache = new WeakMap();
function kwWords(def) {
  if (!kwWordCache.has(def)) kwWordCache.set(def, new Set([...def.keywords, def.name.en].flatMap(k => normKw(k).split(/\s+/))));
  return kwWordCache.get(def);
}

export function availableEnhancements(ru, list, data) {
  const def = data.unitsById.get(ru.unitId);
  return list.detachments
    .flatMap(id => data.detachmentsById.get(id)?.enhancements ?? [])
    .map(e => data.enhancements.get(e.id))
    .filter(e => enhancementFits(e, def, list, data));
}

function leadTargets(leaderRu, data) {
  const def = data.unitsById.get(leaderRu.unitId);
  const targets = [...(def.leader?.canLead ?? [])];
  const enh = leaderRu.enhancement && data.enhancements.get(leaderRu.enhancement);
  if (enh?.grantsLead) targets.push(...enh.grantsLead);
  return targets;
}

export const isLeader = (ru, data) => leadTargets(ru, data).length > 0;

// 11th edition SUPPORT datasheets attach like leaders, but in their own slot: a bodyguard can have its Leader
// unit(s) and one Support unit
export const isSupport = (ru, data) => !!data.unitsById.get(ru.unitId)?.leader?.support;

export const leadersOf = (bodyguardUid, list) => list.units.filter(u => u.attachedTo === bodyguardUid);

export function bodyguardLimits(bgDef, edition) {
  return {
    maxLeaders: bgDef.bodyguard?.maxLeaders ?? edition.rules.defaultMaxLeadersPerBodyguard,
    maxWithKeyword: bgDef.bodyguard?.maxWithKeyword ?? {},
    maxSupport: edition.rules.maxSupportPerBodyguard,
  };
}

// Can `leaderRu` be attached to `bgRu`, given the leaders already on it (excluding itself)?
export function canAttach(leaderRu, bgRu, list, data, edition) {
  if (!bgRu || leaderRu.uid === bgRu.uid || bgRu.attachedTo) return false;
  if (!leadTargets(leaderRu, data).includes(bgRu.unitId)) return false;
  const bgDef = data.unitsById.get(bgRu.unitId);
  const leaderDef = data.unitsById.get(leaderRu.unitId);
  const support = isSupport(leaderRu, data);
  const others = leadersOf(bgRu.uid, list).filter(u => u.uid !== leaderRu.uid && isSupport(u, data) === support);
  const { maxLeaders, maxWithKeyword, maxSupport } = bodyguardLimits(bgDef, edition);
  if (others.length >= (support ? maxSupport : maxLeaders)) return false;
  for (const [kw, max] of Object.entries(maxWithKeyword)) {
    if (!hasKw(leaderDef, kw)) continue;
    const n = others.filter(o => hasKw(data.unitsById.get(o.unitId), kw)).length;
    if (n >= max) return false;
  }
  return true;
}

export function validate(list, data, edition) {
  const issues = [];
  const err = (key, vars = {}, uids = []) => issues.push({ level: 'error', msg: t(key, vars), uids });
  const bs = battleSizeOf(list, edition);
  const nameOf = ru => tr(data.unitsById.get(ru.unitId)?.name);

  const pts = listPoints(list, data);
  if (pts > bs.points) err('err.overPoints', { n: pts - bs.points });

  if (!list.detachments.length) err('err.noDetachment');
  const dp = detachmentPointsUsed(list, data);
  if (dp > bs.detachmentPoints) err('err.overDP', { used: dp, max: bs.detachmentPoints });

  // Wargear footnotes: "cannot have duplicates of these pieces of wargear", "no model can be equipped with both …"
  for (const ru of list.units) {
    const def = data.unitsById.get(ru.unitId);
    if (!def || !(def.uniqueGear || def.exclusiveGear)) continue;
    const models = def.sizes[ru.sizeIdx]?.models ?? 1;
    const { counts } = loadoutCounts(ru, def);
    for (const item of def.uniqueGear ?? []) {
      if ((counts[item] ?? 0) > models) err('err.duplicateGear', { unit: nameOf(ru), item: itemName(def, item) }, [ru.uid]);
    }
    for (const [a, b] of def.exclusiveGear ?? []) {
      if ((counts[a] ?? 0) + (counts[b] ?? 0) > models) {
        err('err.exclusiveGear', { unit: nameOf(ru), a: itemName(def, a), b: itemName(def, b) }, [ru.uid]);
      }
    }
  }

  // Unit limits per datasheet
  const byUnit = new Map();
  for (const ru of list.units) byUnit.set(ru.unitId, [...(byUnit.get(ru.unitId) ?? []), ru]);
  for (const [unitId, rus] of byUnit) {
    const def = data.unitsById.get(unitId);
    if (!def) continue;
    if (hasKw(def, 'EPIC HERO')) {
      if (rus.length > edition.rules.epicHeroLimit) err('err.epicHero', { name: tr(def.name) }, rus.map(r => r.uid));
      continue;
    }
    const mult = Math.max(1, ...Object.entries(edition.rules.unitLimitMultiplierKeywords)
      .filter(([kw]) => hasKw(def, kw)).map(([, m]) => m));
    const max = bs.unitLimit * mult;
    if (rus.length > max) err('err.unitLimit', { name: tr(def.name), max, n: rus.length }, rus.map(r => r.uid));
  }

  // Enhancements & upgrades
  const withEnh = list.units.filter(ru => ru.enhancement);
  const enhCount = new Map();
  let enhTotal = 0;
  for (const ru of withEnh) {
    const enh = data.enhancements.get(ru.enhancement);
    if (!enh) continue;
    const def = data.unitsById.get(ru.unitId);
    enhCount.set(enh.id, (enhCount.get(enh.id) ?? 0) + 1);
    if (enh.type !== 'upgrade' || edition.rules.upgradesCountTowardEnhancementLimit) enhTotal++;
    if (!list.detachments.includes(enh.detachmentId)) err('err.enhNotInDetachment', { enh: tr(enh.name) }, [ru.uid]);
    else if (!enhancementFits(enh, def, list, data)) err('err.enhInvalid', { enh: tr(enh.name), unit: tr(def.name) }, [ru.uid]);
  }
  if (enhTotal > bs.enhancementLimit) err('err.enhLimit', { n: enhTotal, max: bs.enhancementLimit }, withEnh.map(r => r.uid));
  for (const [id, n] of enhCount) {
    const enh = data.enhancements.get(id);
    if (enh.type === 'upgrade') {
      if (n > edition.rules.maxSameUpgrade) err('err.upgradeLimit', { name: tr(enh.name), max: edition.rules.maxSameUpgrade });
    } else if (n > 1) {
      err('err.enhDuplicate', { name: tr(enh.name) }, withEnh.filter(r => r.enhancement === id).map(r => r.uid));
    }
  }

  // Attached units: leaders validity + one enhancement per combined unit
  for (const bg of list.units.filter(u => !u.attachedTo)) {
    const leaders = leadersOf(bg.uid, list);
    if (!leaders.length) continue;
    const bgDef = data.unitsById.get(bg.unitId);
    const { maxLeaders, maxWithKeyword, maxSupport } = bodyguardLimits(bgDef, edition);
    const leading = leaders.filter(l => !isSupport(l, data));
    if (leading.length > maxLeaders) err('err.tooManyLeaders', { unit: nameOf(bg) }, [bg.uid]);
    if (leaders.length - leading.length > maxSupport) err('err.tooManySupport', { unit: nameOf(bg) }, [bg.uid]);
    for (const [kw, max] of Object.entries(maxWithKeyword)) {
      if (leading.filter(l => hasKw(data.unitsById.get(l.unitId), kw)).length > max) {
        err('err.leaderKeyword', { unit: nameOf(bg), kw }, [bg.uid]);
      }
    }
    for (const l of leaders) {
      if (!leadTargets(l, data).includes(bg.unitId)) err('err.leaderInvalid', { leader: nameOf(l), unit: nameOf(bg) }, [l.uid]);
    }
    const enhs = [bg, ...leaders].filter(u => u.enhancement && data.enhancements.get(u.enhancement)?.type !== 'upgrade');
    if (enhs.length > edition.rules.maxEnhancementsPerUnit) err('err.enhPerUnit', { unit: nameOf(bg) }, enhs.map(u => u.uid));
  }

  // Warlord
  const warlords = list.units.filter(u => u.warlord);
  if (list.units.length && edition.rules.warlordRequired && !warlords.length) err('err.noWarlord');
  if (warlords.length > 1) err('err.multiWarlord', {}, warlords.map(u => u.uid));

  if (list.units.some(ru => !data.unitsById.get(ru.unitId)?.pointsVerified)) {
    issues.push({ level: 'warn', msg: t('warn.pointsUnverified'), uids: [] });
  }
  return issues;
}
