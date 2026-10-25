// Unit art: the user's own picture (this browser) → webstore URL (images.json) → generated emblem placeholder.
import { ICONS } from './icons.js';

export const ROLE_COLORS = {
  character: '#c9a227',
  battleline: '#7d8f4e',
  infantry: '#6f8a6a',
  vehicle: '#62707e',
  transport: '#4f7480',
  aircraft: '#4a6fa5',
  titanic: '#9b3434',
  mounted: '#8a6d4a',
  monster: '#8c4a7a',
  fortification: '#7a7468',
};


const cache = new Map();

export function placeholder(def) {
  if (cache.has(def.id)) return cache.get(def.id);
  const color = ROLE_COLORS[def.role] ?? '#777';
  const initials = (def.name.en || def.id).split(/[\s-]+/).filter(w => /^[A-Z]/i.test(w)).slice(0, 3).map(w => w[0].toUpperCase()).join('');
  // official faction emblem (winged skull) tinted with the role colour
  const emblem = (def.emblem ?? ICONS.emblem)
    .replace('<svg class="gw-icon" aria-hidden="true" ', '<svg x="10" y="24" width="80" height="44" ')
    .replaceAll('currentColor', color);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <defs><radialGradient id="g" cx="50%" cy="40%" r="75%"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="#101215"/></radialGradient></defs>
    <rect width="100" height="100" fill="url(#g)"/>
    <path d="M50 8 L92 50 L50 92 L8 50 Z" fill="none" stroke="${color}" stroke-opacity=".45" stroke-width="1.5"/>
    ${emblem}
    <text x="50" y="86" text-anchor="middle" font-family="Arial Narrow,Arial,sans-serif" font-size="11" font-weight="700" fill="#e9e4d4" letter-spacing="1.5">${initials}</text>
  </svg>`;
  const uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  cache.set(def.id, uri);
  return uri;
}

function sourcesOf(def, customImages) {
  return [customImages[def.id], def.storeImage].filter(Boolean);
}

// CSS class for the picture frame: store photos have a white background.
export function imgFrame(def, customImages = {}) {
  const first = sourcesOf(def, customImages)[0];
  return first && first === def.storeImage ? 'store' : '';
}

// Returns <img> markup that walks through the candidate sources and ends on the placeholder.
export function unitImg(def, customImages = {}, cls = '') {
  const fallback = placeholder(def);
  const sources = sourcesOf(def, customImages);
  if (!sources.length) return `<img class="${cls}" src="${fallback}" alt="" draggable="false">`;
  const chain = JSON.stringify([...sources.slice(1), fallback]).replace(/"/g, '&quot;');
  return `<img class="${cls}" src="${sources[0]}" alt="" loading="lazy" draggable="false" referrerpolicy="no-referrer" data-fallbacks="${chain}" onerror="window.__imgFallback(this)">`;
}

window.__imgFallback = img => {
  const rest = JSON.parse(img.dataset.fallbacks || '[]');
  if (!rest.length) { img.onerror = null; return; }
  img.dataset.fallbacks = JSON.stringify(rest.slice(1));
  img.src = rest[0];
};
