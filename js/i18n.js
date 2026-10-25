// UI strings live in i18n/<lang>.json; data strings are {en, es} objects resolved with tr().
export const LANGS = ['es', 'en'];

let lang = 'es';
let dict = {};

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

export function tr(obj) {
  if (obj == null) return '';
  if (typeof obj === 'string') return obj;
  return obj[lang] ?? obj.en ?? Object.values(obj)[0] ?? '';
}
