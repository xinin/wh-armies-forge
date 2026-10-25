// UI strings live in i18n/<lang>.json.
// Game texts are imported in English ({en} objects or plain strings) and translated with dictionaries:
//   data/factions/<f>/i18n.<lang>.json   { texts: { "<English text>": "<translation>" } }
//   data/editions/<ed>.i18n.<lang>.json  { terms: { "rapid fire": "Fuego Rápido", … }, texts: { core stratagems… } }
// Terms translate rule keywords that carry a value: "Rapid Fire 2" → "Fuego Rápido 2", "Anti-Infantry 4+" → …
// Anything without a translation is shown in English.
export const LANGS = ['es', 'en'];

let lang = 'es';
let dict = {};
const gameTexts = {};
const terms = {};

export async function loadLang(l) {
  lang = LANGS.includes(l) ? l : 'es';
  dict = await fetch(`i18n/${lang}.json`).then(r => r.json());
  document.documentElement.lang = lang;
}

export const getLang = () => lang;

export function t(key, vars = {}) {
  const s = dict[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
}

export function addGameTexts(l, texts = {}, glossary = {}) {
  Object.assign(gameTexts[l] ??= {}, texts);
  for (const [k, v] of Object.entries(glossary)) (terms[l] ??= {})[k.toLowerCase()] = v;
}

// Rule term, optionally followed by a value: "Sustained Hits 1", "Feel No Pain 5+", "Scouts 6\"", "Anti-Infantry 4+".
function term(en) {
  const g = terms[lang];
  if (!g) return null;
  const exact = g[en.toLowerCase()];
  if (exact) return exact;
  const m = en.match(/^(.+?)\s+((?:\d|D\d|\d\+)[^\s]*)$/i);
  if (m && g[m[1].toLowerCase()]) return `${g[m[1].toLowerCase()]} ${m[2]}`;
  const anti = en.match(/^anti-(.+?)\s+(\d\+)$/i);
  if (anti && g['anti-']) return `${g['anti-']}${g[anti[1].toLowerCase()] ?? anti[1].toUpperCase()} ${anti[2]}`;
  return null;
}

// Plain English game string → current language.
export function trs(en) {
  if (lang === 'en' || !en) return en ?? '';
  return gameTexts[lang]?.[en] ?? term(en) ?? en;
}

// {en, es?} object (or English string) → current language.
export function tr(obj) {
  if (obj == null) return '';
  if (typeof obj === 'string') return trs(obj);
  if (lang !== 'en' && obj[lang] && obj[lang] !== obj.en) return obj[lang];
  return trs(obj.en ?? Object.values(obj)[0] ?? '');
}
