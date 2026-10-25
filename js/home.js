// Home screen: create a new army list or open / manage the saved ones.
import { t, tr, getLang, LANGS } from './i18n.js';
import { unitImg, imgFrame, ROLE_COLORS } from './images.js';
import { battleSizeOf, listPoints, validate } from './rules.js';
import { esc, brandHtml } from './render.js';
import { icon, factionEmblem } from './icons.js';

export const langToggle = () => `
  <div class="lang-toggle" role="group" aria-label="${t('lang')}">
    ${LANGS.map(l => `<button class="${l === getLang() ? 'on' : ''}" data-action="set-lang" data-lang="${l}">${l.toUpperCase()}</button>`).join('')}
  </div>`;

export function renderHomeHeader() {
  return `${brandHtml()}
  <div></div>
  <div class="header-actions">${langToggle()}</div>`;
}

function relDate(ts) {
  if (!ts) return '';
  const diff = (ts - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(getLang(), { numeric: 'auto' });
  for (const [unit, secs] of [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(diff) >= secs) return rtf.format(Math.round(diff / secs), unit);
  }
  return rtf.format(0, 'minute');
}

// ctx: { index, editions: Map(id → edition), factions: Map(id → data), backend }
export function renderHome(lists, ctx, customImages) {
  const sorted = [...lists].sort((a, b) => (b.updated ?? b.created ?? 0) - (a.updated ?? a.created ?? 0));
  return `
  <div class="home-inner">
    <section class="home-hero">
      <div class="hero-art" aria-hidden="true"></div>
      <img class="hero-logo" src="assets/brand/wh40k-logo.webp" alt="Warhammer 40,000">
      <h1>${t('home.title')}</h1>
      <p>${t('home.subtitle')}</p>
      <div class="hero-actions">
        <button class="btn primary hero-cta" data-action="open-faction-picker">＋ ${t('list.new')}</button>
        <label class="btn hero-cta">⤒ ${t('list.import')}<input type="file" accept="application/json" data-action="import" hidden></label>
      </div>
      ${ctx.backend === 'file' ? '' : `<p class="storage warn">⚠ ${t('home.storageLocal')}</p>`}
    </section>

    <section class="saved">
      <h2>${icon('emblemFull', 'head-icon')}${t('home.saved')} <span class="count">${lists.length}</span></h2>
      ${sorted.length ? factionGroups(sorted, ctx).map(({ data, color, lists: group }) => `
        <div class="faction-group" style="--faction:${color}">
          <h3 class="faction-group-head">${factionEmblem(data, 'fg-emblem')}<span>${esc(tr(data.faction.name))}</span> <span class="count">${group.length}</span></h3>
          <div class="list-grid">${group.map(l => listCard(l, ctx, customImages)).join('')}</div>
        </div>`).join('')
        : `<div class="empty"><img class="empty-aquila" src="assets/brand/aquila.webp" alt="" aria-hidden="true"><p>${t('home.empty')}</p>
            <button class="btn primary" data-action="open-faction-picker">＋ ${t('list.new')}</button></div>`}
    </section>
  </div>`;
}

// Saved lists grouped by faction (alphabetical); each group keeps the most recently edited list first.
function factionGroups(sorted, ctx) {
  const groups = new Map();
  for (const l of sorted) {
    const data = ctx.factions.get(l.factionId);
    if (!data) continue;
    if (!groups.has(l.factionId)) {
      groups.set(l.factionId, { data, color: ctx.index.factions.find(f => f.id === l.factionId)?.color ?? '#6b7d4a', lists: [] });
    }
    groups.get(l.factionId).lists.push(l);
  }
  return [...groups.values()].sort((a, b) => tr(a.data.faction.name).localeCompare(tr(b.data.faction.name), getLang()));
}

function listCard(list, ctx, customImages) {
  const data = ctx.factions.get(list.factionId);
  const edition = ctx.editions.get(list.edition);
  if (!data || !edition) return '';
  const pts = listPoints(list, data);
  const bs = battleSizeOf(list, edition);
  const over = pts > bs.points;
  const errors = validate(list, data, edition).filter(i => i.level === 'error').length;
  // show characters first, then the most expensive units
  const defs = list.units.map(u => data.unitsById.get(u.unitId)).filter(Boolean);
  const showcase = [...new Map(defs.map(d => [d.id, d])).values()]
    .sort((a, b) => (b.role === 'character') - (a.role === 'character') || (b.sizes[0].points ?? 0) - (a.sizes[0].points ?? 0))
    .slice(0, 4);
  const detachments = list.detachments.map(id => tr(data.detachmentsById.get(id)?.name)).filter(Boolean);
  return `
  <article class="list-card" data-action="open-list" data-id="${list.id}" tabindex="0" style="--faction:${ctx.index.factions.find(f => f.id === list.factionId)?.color ?? '#6b7d4a'}">
    <div class="lc-art">
      ${showcase.length ? showcase.map(d => `<div class="lc-thumb ${imgFrame(d, customImages)}" style="--role:${ROLE_COLORS[d.role]}">${unitImg(d, customImages)}</div>`).join('')
        : `<div class="lc-empty">${t('home.noUnits')}</div>`}
    </div>
    <div class="lc-body">
      <div class="lc-title">${factionEmblem(data, 'lc-emblem')}<h3>${esc(list.name || t('list.untitled'))}</h3>
        <span class="lc-status ${errors ? 'bad' : 'good'}">${errors ? `${icon('diamond')}${errors}` : icon('stratPloy')}</span></div>
      <div class="lc-meta">${esc(tr(data.faction.name))} · ${esc(tr(bs.name))}${detachments.length ? ` · ${esc(detachments.join(', '))}` : ''}</div>
      <div class="lc-points ${over ? 'over' : ''}">
        <span><b>${pts}</b> / ${bs.points} ${t('points')}</span>
        <span class="muted">${list.units.length} ${t('home.units')}</span>
      </div>
      <div class="points-track"><div class="points-fill" style="width:${Math.min(100, pts / bs.points * 100)}%"></div></div>
      <div class="lc-foot">
        <span class="muted" title="${list.file ? esc(list.file) : ''}">${t('home.updated')} ${relDate(list.updated ?? list.created)}</span>
        <span class="lc-actions">
          <button class="btn icon small" data-action="duplicate-list" data-id="${list.id}" title="${t('list.duplicate')}">⧉</button>
          <button class="btn icon small" data-action="export" data-id="${list.id}" title="${t('list.export')}">⤓</button>
          <button class="btn icon small danger" data-action="delete-list" data-id="${list.id}" title="${t('list.delete')}">🗑</button>
        </span>
      </div>
    </div>
  </article>`;
}

// Pop-up to pick the faction of a new list: one tile per faction with its emblem and colour.
export function renderFactionPicker(index, factions) {
  return `
  <div class="dialog-card picker" role="dialog" aria-modal="true" aria-labelledby="picker-title">
    <header class="picker-head">
      <h2 id="picker-title">${icon('emblemFull', 'head-icon')}${t('picker.title')}</h2>
      <button class="btn icon" data-action="close-picker" aria-label="${t('close')}">✕</button>
    </header>
    <div class="faction-grid">
      ${index.factions.map(f => {
        const data = factions.get(f.id);
        return `<button class="faction-tile" data-action="pick-faction" data-id="${f.id}" style="--faction:${f.color ?? '#6b7d4a'}">
          <span class="ft-emblem">${factionEmblem(data)}</span>
          <span class="ft-name">${esc(tr(f.name))}</span>
          ${data ? `<span class="ft-meta">${data.units.length} ${t('home.units')} · ${data.faction.detachments.length} ${t('picker.detachments')}</span>` : ''}
        </button>`;
      }).join('')}
    </div>
  </div>`;
}
