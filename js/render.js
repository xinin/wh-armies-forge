// HTML-string renderers. Interactive elements carry data-action; main.js handles them by delegation.
import { t, tr, getLang, LANGS } from './i18n.js';
import { unitImg, imgFrame, ROLE_COLORS } from './images.js';
import { icon } from './icons.js';
import {
  battleSizeOf, unitPoints, listPoints, detachmentPointsUsed, availableEnhancements,
  isLeader, leadersOf, canAttach, optionMax, hasKw, bodyguardLimits, isExtraCopy,
} from './rules.js';

export const ROLES = ['character', 'battleline', 'infantry', 'mounted', 'monster', 'vehicle', 'transport', 'aircraft', 'titanic', 'fortification'];

// Roster "datasheet" panels: global default + per-unit overrides set by the user (uid → open?)
export const sheetState = { show: true, overrides: new Map() };

export const brandHtml = () => `
  <a class="brand" href="#/" title="${t('home.back')}">
    <img class="brand-logo" src="assets/brand/wh40k-logo.webp" alt="Warhammer 40,000" width="147" height="32">
    <div class="brand-text"><div class="brand-title">${t('app.title')}</div><div class="brand-sub">${t('app.subtitle')}</div></div>
  </a>`;

const roleHead = (role, extra = '') => `<h3 class="role-head" style="--role:${ROLE_COLORS[role]}">${icon('diamond', 'role-diamond')}<span>${t('role.' + role)}</span>${extra}</h3>`;

const EMPTY_ART = `<img class="empty-aquila" src="assets/brand/aquila.webp" alt="" aria-hidden="true">`;

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const weaponName = (def, id) => tr(def.weaponMap.get(id)?.name) || id;

/* ---------- Header ---------- */

export function renderHeader(state, list, index, data, edition) {
  const pts = listPoints(list, data);
  const pct = Math.min(100, (pts / list.pointsLimit) * 100);
  const over = pts > list.pointsLimit;
  return `
  ${brandHtml()}
  <div class="list-switch">
    <a class="btn" href="#/" data-action="go-home">← ${t('home.back')}</a>
    <span id="save-status" class="save-status"></span>
  </div>
  <div class="header-actions">
    <a class="btn primary" href="#/list/${list.id}/view">${icon('emblem')}${t('overview.open')}</a>
    <button class="btn" data-action="copy-text">${t('list.copyText')}</button>
    <button class="btn" data-action="export" data-id="${list.id}">${t('list.export')}</button>
    <div class="lang-toggle" role="group" aria-label="${t('lang')}">
      ${LANGS.map(l => `<button class="${l === getLang() ? 'on' : ''}" data-action="set-lang" data-lang="${l}">${l.toUpperCase()}</button>`).join('')}
    </div>
  </div>
  <div class="list-bar">
    <input class="list-name" data-action="list-name" value="${esc(list.name)}" placeholder="${t('list.untitled')}">
    <div class="field"><span>${t('faction')}</span><span class="faction-name">${icon('emblemFull', 'faction-emblem')}${esc(tr(data.faction.name))}</span></div>
    <label class="field"><span>${t('battleSize')}</span>
      <select data-action="battle-size">${edition.battleSizes.map(b => `<option value="${b.id}" ${b.id === list.battleSize ? 'selected' : ''}>${esc(tr(b.name))} (${b.points})</option>`).join('')}</select>
    </label>
    <label class="field narrow"><span>${t('pointsLimit')}</span>
      <input type="number" min="100" step="50" data-action="points-limit" value="${list.pointsLimit}">
    </label>
    <div class="points-meter ${over ? 'over' : ''}" title="${pts} / ${list.pointsLimit}">
      <div class="points-num"><strong>${pts}</strong> / ${list.pointsLimit} ${t('points')}</div>
      <div class="points-track"><div class="points-fill" style="width:${pct}%"></div></div>
    </div>
  </div>`;
}

/* ---------- Catalog ---------- */

export function renderCatalog(data, ui, customImages) {
  return `
  <div class="panel-head">
    <h2>${icon('emblem', 'head-icon')}${t('catalog')}</h2>
    <input type="search" class="search" data-action="search" placeholder="${t('catalog.search')}" value="${esc(ui.search)}">
    <div class="chips">
      <button class="chip ${!ui.role ? 'on' : ''}" data-action="filter-role" data-role="">${t('catalog.all')}</button>
      ${ROLES.filter(r => data.units.some(u => u.role === r)).map(r => `
        <button class="chip ${ui.role === r ? 'on' : ''}" data-action="filter-role" data-role="${r}" style="--role:${ROLE_COLORS[r]}">${t('role.' + r)}</button>`).join('')}
    </div>
    <p class="hint">${t('catalog.hint')}</p>
  </div>
  <div class="catalog-list" id="catalog-list">${renderCatalogItems(data, ui, customImages)}</div>`;
}

export function renderCatalogItems(data, ui, customImages) {
  const q = ui.search.trim().toLowerCase();
  const units = data.units.filter(u =>
    (!ui.role || u.role === ui.role) &&
    (!q || tr(u.name).toLowerCase().includes(q) || u.name.en.toLowerCase().includes(q) || u.keywords.some(k => k.toLowerCase().includes(q))));
  return ROLES.map(role => {
    const group = units.filter(u => u.role === role);
    if (!group.length) return '';
    return `<div class="cat-group">${roleHead(role)}
      ${group.map(u => `
        <div class="cat-item" draggable="true" data-drag="cat:${u.id}" style="--role:${ROLE_COLORS[u.role]}">
          <div class="thumb ${imgFrame(u, customImages)}" data-img-drop="${u.id}" title="${t('unit.imageDrop')}">${unitImg(u, customImages)}</div>
          <div class="cat-info" data-action="details" data-unit="${u.id}">
            <div class="cat-name">${esc(tr(u.name))}${hasKw(u, 'EPIC HERO') ? ` <span class="tag epic">${t('unit.epicHero')}</span>` : ''}</div>
            <div class="cat-meta">${u.sizes.map(s => `${s.models}× <b>${s.points ?? '?'}</b>`).join(' · ')} ${t('points')}${u.pointsVerified ? '' : ' <span class="unverified" title="' + t('warn.pointsUnverified') + '">*</span>'}</div>
          </div>
          <button class="btn add" data-action="add-unit" data-unit="${u.id}" aria-label="+">＋</button>
        </div>`).join('')}
    </div>`;
  }).join('');
}

/* ---------- Roster ---------- */

export function renderRoster(list, data, edition, issues, customImages) {
  const flagged = new Set(issues.filter(i => i.level === 'error').flatMap(i => i.uids));
  const top = list.units.filter(u => !u.attachedTo);
  const body = top.length
    ? ROLES.map(role => {
        // a unit with attached leaders is shown led by its character, so it lives in the character group
        const roleOf = u => leadersOf(u.uid, list).length ? 'character' : data.unitsById.get(u.unitId)?.role;
        const group = top.filter(u => roleOf(u) === role);
        if (!group.length) return '';
        const pts = group.reduce((s, u) => s + unitPoints(u, data, list) + leadersOf(u.uid, list).reduce((a, l) => a + unitPoints(l, data, list), 0), 0);
        return `<section class="roster-group">${roleHead(role, `<span class="role-pts">${pts} ${t('points')}</span>`)}
          ${group.map(u => renderRosterUnit(u, list, data, edition, flagged, customImages)).join('')}
        </section>`;
      }).join('')
    : `<div class="empty">${EMPTY_ART}<p>${t('roster.empty')}</p></div>`;
  return `<div class="panel-head"><h2>${icon('emblemFull', 'head-icon')}${t('roster')}</h2>
      <span class="head-tools">
        ${list.units.length ? `<button class="btn small ${sheetState.show ? 'on' : ''}" data-action="toggle-sheets" aria-pressed="${sheetState.show}">${t(sheetState.show ? 'roster.hideDetails' : 'roster.showDetails')}</button>` : ''}
        <span class="count">${list.units.length}</span>
      </span></div>
    <div class="roster-body" data-drop="roster">${body}</div>`;
}

function renderRosterUnit(ru, list, data, edition, flagged, customImages) {
  const def = data.unitsById.get(ru.unitId);
  if (!def) return '';
  const leaders = leadersOf(ru.uid, list);
  const combined = unitPoints(ru, data, list) + leaders.reduce((a, l) => a + unitPoints(l, data, list), 0);
  const leaderUnit = isLeader(ru, data);
  const dropHint = `<div class="drop-hint">${t('roster.dropLeader')}</div>`;
  if (!leaders.length) {
    return `
  <article class="ru ${flagged.has(ru.uid) ? 'invalid' : ''}" data-uid="${ru.uid}" data-drop="unit" ${leaderUnit ? `draggable="true" data-drag="ru:${ru.uid}"` : ''} style="--role:${ROLE_COLORS[def.role]}">
    ${renderUnitCore(ru, def, list, data, edition, customImages, false)}
    ${dropHint}
  </article>`;
  }
  // Attached unit: leader(s) on top in large, the led unit below
  const invalid = [ru, ...leaders].some(u => flagged.has(u.uid));
  return `
  <article class="ru combo ${invalid ? 'invalid' : ''}" data-uid="${ru.uid}" data-drop="unit" style="--role:${ROLE_COLORS.character}">
    ${leaders.map(l => `<div class="leader-main ${flagged.has(l.uid) ? 'invalid' : ''}" data-uid="${l.uid}" draggable="true" data-drag="ru:${l.uid}">
      ${renderUnitCore(l, data.unitsById.get(l.unitId), list, data, edition, customImages, true)}</div>`).join('')}
    <div class="led">
      <div class="attached-label">${t('unit.leading')}
        <span class="leader-slots ${leaders.length >= bodyguardLimits(def, edition).maxLeaders ? 'full' : ''}">${t('roster.leaderSlots', { n: leaders.length, max: bodyguardLimits(def, edition).maxLeaders })}</span></div>
      <div class="ru-sub ${flagged.has(ru.uid) ? 'invalid' : ''}" data-uid="${ru.uid}" style="--role:${ROLE_COLORS[def.role]}">
        ${renderUnitCore(ru, def, list, data, edition, customImages, false)}
      </div>
    </div>
    <div class="combined">${t('total')}: <b>${combined}</b> ${t('points')}</div>
    ${dropHint}
  </article>`;
}

function renderUnitCore(ru, def, list, data, edition, customImages, attached) {
  const isChar = hasKw(def, 'CHARACTER');
  const enhs = availableEnhancements(ru, list, data);
  const targets = !attached && isLeader(ru, data)
    ? list.units.filter(b => b.uid !== ru.uid && !isLeader(b, data) && canAttach(ru, b, list, data, edition))
    : [];
  return `
  <div class="ru-main">
    <div class="thumb ${imgFrame(def, customImages)}" data-action="details" data-unit="${def.id}" data-img-drop="${def.id}" title="${t('unit.imageDrop')}">${unitImg(def, customImages)}</div>
    <div class="ru-info">
      <div class="ru-title">
        <span class="ru-name" data-action="details" data-unit="${def.id}">${esc(tr(def.name))}</span>
        ${ru.warlord ? `<span class="tag warlord">${icon('emblem')}${t('unit.warlord')}</span>` : ''}
        ${isExtraCopy(ru, data, list) ? `<span class="tag extra-copy" title="${t('unit.extraCopyHelp')}">${t('unit.extraCopy')}</span>` : ''}
        <span class="ru-pts">${unitPoints(ru, data, list)} ${t('points')}</span>
      </div>
      <div class="ru-controls">
        ${def.sizes.length > 1 ? `<select data-action="size" data-uid="${ru.uid}">
          ${def.sizes.map((s, i) => `<option value="${i}" ${i === ru.sizeIdx ? 'selected' : ''}>${s.models} ${t(s.models === 1 ? 'unit.model' : 'unit.models')} · ${s.points ?? '?'} ${t('points')}</option>`).join('')}
        </select>` : `<span class="muted">${def.sizes[0].models} ${t(def.sizes[0].models === 1 ? 'unit.model' : 'unit.models')}</span>`}
        ${enhs.length || ru.enhancement ? `<select data-action="enhancement" data-uid="${ru.uid}" class="${ru.enhancement ? 'has-enh' : ''}">
          <option value="">${t('unit.enhancement')}: ${t('unit.none')}</option>
          ${enhs.map(e => `<option value="${e.id}" ${e.id === ru.enhancement ? 'selected' : ''}>${e.type === 'upgrade' ? '⬆ ' : '✦ '}${esc(tr(e.name))} (+${e.points})</option>`).join('')}
          ${ru.enhancement && !enhs.some(e => e.id === ru.enhancement) ? `<option value="${ru.enhancement}" selected>⚠ ${esc(tr(data.enhancements.get(ru.enhancement)?.name))}</option>` : ''}
        </select>` : ''}
        ${isChar ? `<button class="btn small ${ru.warlord ? 'on' : ''}" data-action="warlord" data-uid="${ru.uid}" title="${t('unit.warlord')}">${icon('emblem')}</button>` : ''}
        ${targets.length ? `<select data-action="attach" data-uid="${ru.uid}"><option value="">${t('unit.attachTo')}</option>
          ${targets.map(b => `<option value="${b.uid}">${esc(tr(data.unitsById.get(b.unitId).name))}</option>`).join('')}</select>` : ''}
        ${attached ? `<button class="btn small" data-action="detach" data-uid="${ru.uid}">${t('unit.detach')}</button>` : ''}
      </div>
      ${def.wargear?.length ? renderWargear(ru, def, data) : ''}
    </div>
    <div class="ru-actions">
      <button class="btn icon small" data-action="duplicate-unit" data-uid="${ru.uid}" title="${t('unit.duplicate')}">⧉</button>
      <button class="btn icon small danger" data-action="remove" data-uid="${ru.uid}" title="${t('unit.remove')}">✕</button>
    </div>
  </div>
  ${renderSheet(ru, def, data)}`;
}

// Effective weapons after swaps / pools / toggles: [{ id, name, count, changed }]
export function loadoutOf(ru, def, data) {
  const items = [];
  const swapped = new Map();
  const add = (id, count, changed) => items.push({ id, name: `${count > 1 ? count + '× ' : ''}${weaponName(def, id)}`, count, changed });
  for (const opt of def.wargear ?? []) {
    const v = ru.wargear?.[opt.id] ?? opt.default;
    if (opt.type === 'swap' && v !== opt.default) {
      swapped.set(opt.default, v);
      if (!opt.default && v) add(v, 1, true);
    }
  }
  for (const w of def.loadout) {
    if (swapped.has(w)) { const v = swapped.get(w); if (v) add(v, 1, true); }
    else add(w, 1, false);
  }
  for (const opt of def.wargear ?? []) {
    const v = ru.wargear?.[opt.id];
    if (opt.type === 'pool') for (const [w, n] of Object.entries(v ?? {})) if (n > 0) add(w, n, true);
    if (opt.type === 'toggle' && v > 0) {
      if (opt.gives) add(opt.gives, v, true);
      else items.push({ id: null, name: `${v > 1 ? v + '× ' : ''}${tr(opt.label).replace(/\s*\(.*\)/, '')}`, count: v, changed: true });
    }
  }
  return items;
}

export function statRows(def) {
  const named = def.stats.length > 1;
  return `<table class="mini-stats"><tr>${named ? '<th></th>' : ''}<th>M</th><th>T</th><th>SV</th><th>W</th><th>LD</th><th>OC</th>${def.stats.some(s => s.inv) ? '<th>INV</th>' : ''}</tr>
    ${def.stats.map(s => `<tr>${named ? `<td class="sname">${esc(tr(s.name))}</td>` : ''}<td>${s.M}</td><td>${s.T}</td><td>${s.Sv}</td><td>${s.W}</td><td>${s.Ld}</td><td>${s.OC}</td>${def.stats.some(x => x.inv) ? `<td class="inv">${s.inv ?? '–'}</td>` : ''}</tr>`).join('')}
  </table>`;
}

export function weaponTable(ru, def, data) {
  const items = loadoutOf(ru, def, data);
  // merge duplicates (e.g. default lasguns + nothing else), keep the "changed" flag
  const rows = new Map();
  for (const i of items) {
    if (!i.id || !def.weaponMap.get(i.id)) continue;
    const r = rows.get(i.id);
    if (r) { r.count += i.count; r.changed ||= i.changed; } else rows.set(i.id, { ...i });
  }
  const section = type => [...rows.values()].filter(r => def.weaponMap.get(r.id).type === type).flatMap(r => {
    const w = def.weaponMap.get(r.id);
    return w.profiles.map((p, k) => `<tr class="${r.changed ? 'changed' : ''} ${k ? 'subprofile' : ''}">
      <td class="wname">${w.profiles.length > 1 ? icon('profileArrow', 'parrow') : ''}${k ? '' : `${r.count > 1 ? `<b>${r.count}×</b> ` : ''}${esc(tr(w.name))}`}${p.mode ? ` <small>(${esc(tr(p.mode))})</small>` : ''}${p.keywords.length ? `<div class="wkw">${p.keywords.map(esc).join(', ')}</div>` : ''}</td>
      <td>${esc(p.range === 'Melee' ? '—' : p.range)}</td><td>${esc(p.A)}</td><td>${esc(p.skill)}</td><td>${esc(p.S)}</td><td>${esc(p.AP)}</td><td>${esc(p.D)}</td></tr>`);
  }).join('');
  const ranged = section('ranged'), melee = section('melee');
  const head = (label, skill, ic) => `<tr class="whead"><th class="wname">${icon(ic)}${label}</th><th>${t('stats.rangeShort')}</th><th>A</th><th>${skill}</th><th>S</th><th>AP</th><th>D</th></tr>`;
  const other = items.filter(i => !i.id || !def.weaponMap.get(i.id));
  return `<div class="table-wrap"><table class="mini-weapons">
      ${ranged ? head(t('unit.ranged'), 'BS', 'ranged') + ranged : ''}${melee ? head(t('unit.melee'), 'WS', 'melee') + melee : ''}
    </table></div>
    ${other.length ? `<div class="loadout">${other.map(i => `<span class="weapon changed">${esc(i.name)}</span>`).join('')}</div>` : ''}`;
}

export function abilitiesBlock(def) {
  const tags = [...(def.core ?? []).map(c => `<span class="tag core">${esc(c)}</span>`), ...(def.factionAbilities ?? []).map(f => `<span class="tag faction">${esc(f)}</span>`)];
  const list = [...(def.abilities ?? []), ...(def.wargearAbilities ?? [])];
  if (def.damaged) list.push({ name: { en: `${t('unit.damaged')} (${tr(def.damaged.name)})` }, text: def.damaged.text });
  if (!tags.length && !list.length) return '';
  return `<div class="mini-abilities">
    ${tags.length ? `<div class="ability-tags">${tags.join('')}</div>` : ''}
    ${list.map(a => `<p><b>${esc(tr(a.name))}:</b> ${esc(tr(a.text))}</p>`).join('')}
    ${def.ordersText ? `<p class="orders-line"><b>${t('unit.orders')}:</b> ${esc(tr(def.ordersText))}</p>` : ''}
  </div>`;
}

function renderSheet(ru, def, data) {
  const open = sheetState.overrides.get(ru.uid) ?? sheetState.show;
  return `<div class="sheet">
    ${statRows(def)}
    <details class="sheet-more" data-sheet="${ru.uid}" ${open ? 'open' : ''}>
      <summary>${t('unit.sheet')}</summary>
      ${weaponTable(ru, def, data)}
      ${abilitiesBlock(def)}
    </details>
  </div>`;
}

function renderWargear(ru, def, data) {
  const models = def.sizes[ru.sizeIdx]?.models ?? 1;
  const rows = def.wargear.map(opt => {
    const v = ru.wargear?.[opt.id] ?? opt.default;
    if (opt.type === 'swap') {
      return `<label class="wg-row"><span>${esc(tr(opt.label))}</span>
        <select data-action="wg-swap" data-uid="${ru.uid}" data-opt="${opt.id}">
          ${opt.choices.map(c => `<option value="${c}" ${c === v ? 'selected' : ''}>${c ? esc(weaponName(def, c)) : t('unit.none')}</option>`).join('')}
        </select></label>`;
    }
    const max = optionMax(opt, models);
    if (opt.type === 'pool') {
      const used = Object.values(v ?? {}).reduce((a, b) => a + b, 0);
      return `<div class="wg-row pool"><span>${esc(tr(opt.label))} <b class="${used > max ? 'bad' : ''}">${used}/${max}</b></span>
        <div class="pool-items">${opt.choices.map(c => `<label class="stepper">${esc(weaponName(def, c))}
          <input type="number" min="0" max="${max}" value="${v?.[c] ?? 0}" data-action="wg-pool" data-uid="${ru.uid}" data-opt="${opt.id}" data-weapon="${c}"></label>`).join('')}
        </div></div>`;
    }
    return `<label class="wg-row"><span>${esc(tr(opt.label))}</span>
      ${max > 1
        ? `<input type="number" min="0" max="${max}" value="${v ?? 0}" data-action="wg-toggle" data-uid="${ru.uid}" data-opt="${opt.id}">`
        : `<input type="checkbox" ${v ? 'checked' : ''} data-action="wg-toggle" data-uid="${ru.uid}" data-opt="${opt.id}">`}
    </label>`;
  }).join('');
  return `<details class="wargear"><summary>${t('unit.wargear')}</summary>${rows}</details>`;
}

/* ---------- Sidebar ---------- */

export function renderSidebar(list, data, edition, issues) {
  const bs = battleSizeOf(list, edition);
  const dp = detachmentPointsUsed(list, data);
  const errors = issues.filter(i => i.level === 'error');
  const warns = issues.filter(i => i.level === 'warn');
  const ar = data.faction.armyRule;
  return `
  <section class="side-block">
    <div class="panel-head"><h2>${icon('diamond', 'head-icon')}${t('validation')}</h2></div>
    ${errors.length ? `<ul class="issues">${errors.map(i => `<li class="err">${esc(i.msg)}</li>`).join('')}</ul>`
      : `<div class="ok">${icon('stratPloy')}${t('validation.ok')}</div>`}
    ${warns.length ? `<ul class="issues">${warns.map(i => `<li class="warn">${esc(i.msg)}</li>`).join('')}</ul>` : ''}
  </section>
  <section class="side-block">
    <div class="panel-head"><h2>${icon('stratTactic', 'head-icon')}${t('detachments')}</h2>
      <span class="dp ${dp > bs.detachmentPoints ? 'over' : ''}" title="${t('detachmentPoints')}">${dp}/${bs.detachmentPoints} DP</span></div>
    <div class="detachments">
      ${data.faction.detachments.map(d => {
        const on = list.detachments.includes(d.id);
        const disabled = !on && dp + d.cost > bs.detachmentPoints;
        return `<div class="det ${on ? 'on' : ''} ${disabled ? 'disabled' : ''}">
          <button class="det-head" data-action="toggle-detachment" data-id="${d.id}" aria-pressed="${on}">
            <span class="det-check">${icon(on ? 'stratPloy' : 'diamond')}</span>
            <span class="det-name">${esc(tr(d.name))}</span>
            <span class="det-cost">${d.cost} DP</span>
          </button>
          <details><summary>${esc(tr(d.rule.name))}</summary>
            <p>${esc(tr(d.rule.text))}</p>
            <ul class="enh-list">${d.enhancements.map(e => {
              const enh = data.enhancements.get(e.id);
              return `<li><b>${esc(tr(e.name))}</b> <span class="muted">${enh.points} ${t('points')}${enh.type === 'upgrade' ? ' · ' + t('unit.upgrade') : ''}</span><br><small>${esc(tr(e.text))}</small></li>`;
            }).join('')}</ul>
          </details>
        </div>`;
      }).join('')}
    </div>
  </section>
  <section class="side-block">
    <div class="panel-head"><h2>${icon('emblem', 'head-icon')}${t('rules.armyRule')}</h2></div>
    <details class="army-rule"><summary>${esc(tr(ar.name))}</summary>
      <p>${esc(tr(ar.text))}</p>
      <ul class="orders">${(ar.orders ?? []).map(o => `<li><b>${esc(tr(o.name))}</b> ${esc(tr(o.text))}</li>`).join('')}</ul>
    </details>
    <p class="data-meta">${t('data.version')}: ${esc(data.pointsMeta.version)}</p>
    <p class="disclaimer">${t('disclaimer')}</p>
  </section>`;
}

/* ---------- Datasheet modal ---------- */

function weaponRows(weapons, type) {
  return weapons.filter(w => w.type === type).flatMap(w => w.profiles.map((p, k) => `
      <tr class="${k ? 'subprofile' : ''}"><td class="wname">${w.profiles.length > 1 ? icon('profileArrow', 'parrow') : ''}${esc(tr(w.name))}${p.mode ? ` <small>– ${esc(tr(p.mode))}</small>` : ''}${p.keywords.length ? ` <span class="wkw">[${p.keywords.map(esc).join(', ')}]</span>` : ''}</td>
      <td>${esc(p.range)}</td><td>${esc(p.A)}</td><td>${esc(p.skill)}</td><td>${esc(p.S)}</td><td>${esc(p.AP)}</td><td>${esc(p.D)}</td></tr>`)).join('');
}

const abilityList = list => `<ul class="abilities">${list.map(a => `<li><b>${esc(tr(a.name))}:</b> ${esc(tr(a.text))}</li>`).join('')}</ul>`;
const dsHead = (label, ic = null) => `<h3 class="ds-head">${ic ? icon(ic) : ''}<span>${label}</span></h3>`;

export function renderModal(def, data, customImages) {
  const weapons = [...def.weaponMap.values()];
  const ranged = weaponRows(weapons, 'ranged');
  const melee = weaponRows(weapons, 'melee');
  const head = (label, ic, skill) => `<tr class="whead"><th>${icon(ic)}${label}</th><th>${t('stats.range')}</th><th>A</th><th>${skill}</th><th>S</th><th>AP</th><th>D</th></tr>`;
  const tags = [...(def.core ?? []).map(c => `<span class="tag core">${esc(c)}</span>`), ...(def.factionAbilities ?? []).map(f => `<span class="tag faction">${esc(f)}</span>`)];
  const named = def.stats.length > 1;
  return `
  <div class="modal-card datasheet" role="dialog" aria-modal="true" aria-label="${esc(tr(def.name))}" style="--role:${ROLE_COLORS[def.role]}">
    <button class="btn icon close" data-action="close-modal" aria-label="${t('close')}">✕</button>
    <header class="ds-banner">
      <div class="ds-banner-text">
        <h2>${esc(tr(def.name))}</h2>
        ${def.stats.map(s => `<div class="ds-stats">
          ${['M', 'T', 'Sv', 'W', 'Ld', 'OC'].map(k => `<div class="ds-stat"><span>${k.toUpperCase()}</span><b>${s[k]}</b></div>`).join('')}
          ${s.inv ? `<div class="ds-stat inv"><span>INV</span><b>${s.inv}</b></div>` : ''}
          ${named ? `<div class="ds-stat-name">${esc(tr(s.name))}</div>` : ''}
        </div>`).join('')}
      </div>
      <div class="ds-art ${imgFrame(def, customImages)}" data-img-drop="${def.id}">${unitImg(def, customImages)}</div>
    </header>
    <div class="ds-body">
      <div class="ds-sizes">${def.sizes.map(s => `<span class="size-pill">${s.models} ${t(s.models === 1 ? 'unit.model' : 'unit.models')} · <b>${s.points ?? '?'}</b> ${t('points')}</span>`).join('')}
        ${tags.length ? `<span class="ability-tags">${tags.join('')}</span>` : ''}</div>
      <div class="table-wrap"><table class="weapons">${ranged ? head(t('unit.ranged'), 'ranged', 'BS') + ranged : ''}${melee ? head(t('unit.melee'), 'melee', 'WS') + melee : ''}</table></div>
      ${def.ordersText ? `<p class="orders-text">${icon('emblem')}<b>${t('unit.orders')}:</b> ${esc(tr(def.ordersText))}</p>` : def.orders ? `<p class="orders-text">${icon('emblem')}<b>${t('unit.orders')}:</b> ${def.orders}</p>` : ''}
    ${def.abilities?.length ? `${dsHead(t('unit.abilities'))}${abilityList(def.abilities)}` : ''}
    ${def.wargearAbilities?.length ? `${dsHead(t('unit.wargearAbilities'))}${abilityList(def.wargearAbilities)}` : ''}
    ${def.damaged ? `${dsHead(`${t('unit.damaged')}: ${esc(tr(def.damaged.name))}`)}<p>${esc(tr(def.damaged.text))}</p>` : ''}
    ${def.wargearOptions?.length ? `${dsHead(t('unit.wargearOptions'))}<ul class="wg-text">${def.wargearOptions.map(o => `<li>${esc(o.text)}${o.choices.length ? `<ul>${o.choices.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}</li>`).join('')}</ul>` : ''}
    ${def.composition?.length || def.equipped?.length ? `${dsHead(t('unit.composition'))}
      ${def.composition?.length ? `<p>${def.composition.map(esc).join(' · ')}</p>` : ''}
      ${(def.equipped ?? []).map(e => `<p class="muted">${esc(e)}</p>`).join('')}` : ''}
    ${def.leader ? `${dsHead(t('unit.leads'))}<p>${def.leader.canLead.map(id => esc(tr(data.unitsById.get(id)?.name) || id)).join(', ')}</p>` : ''}
    ${def.attachRule ? `<p class="muted">${esc(def.attachRule)}</p>` : ''}
    ${def.transport ? `${dsHead(t('unit.transport'))}<p>${esc(tr(def.transport))}</p>` : ''}
    ${def.lore ? `<blockquote class="lore">${esc(tr(def.lore))}</blockquote>` : ''}
    </div>
    <footer class="ds-keywords">
      <div class="ds-kw"><span>${t('unit.keywords')}:</span> ${def.keywords.map(esc).join(', ')}</div>
      <div class="ds-kw-emblem">${icon('emblemFull')}</div>
      <div class="ds-kw faction"><span>${t('unit.factionKeywords')}:</span> ${esc(tr(data.faction.name))}</div>
    </footer>
    <div class="ds-extra">
      ${def.source ? `<p class="data-meta">${t('unit.source')}: ${esc(def.source)}</p>` : ''}
      <label class="field img-field"><span>${t('unit.storeImage')}</span>
        <div class="img-row">
          <input type="url" data-action="image-url" data-unit="${def.id}" value="${esc(def.storeImage ?? '')}" placeholder="https://www.warhammer.com/app/resources/catalog/product/...">
          <label class="btn">${t('unit.imageUpload')}<input type="file" accept="image/*" data-action="image-file" data-unit="${def.id}" hidden></label>
          ${customImages[def.id] ? `<button class="btn danger" data-action="image-clear" data-unit="${def.id}">${t('unit.imageClear')}</button>` : ''}
        </div>
        <small class="img-help">${t('unit.storeImageHelp')}</small>
      </label>
    </div>
  </div>`;
}

/* ---------- Text export ---------- */

export function listToText(list, data, edition) {
  const bs = battleSizeOf(list, edition);
  const lines = [
    `${list.name || t('list.untitled')} — ${listPoints(list, data)}/${list.pointsLimit} ${t('points')}`,
    `${tr(data.faction.name)} · ${tr(bs.name)} · ${list.detachments.map(id => tr(data.detachmentsById.get(id)?.name)).join(', ')}`,
    '',
  ];
  const describe = (ru, indent) => {
    const def = data.unitsById.get(ru.unitId);
    const size = def.sizes[ru.sizeIdx];
    const enh = ru.enhancement && data.enhancements.get(ru.enhancement);
    lines.push(`${indent}${tr(def.name)}${size.models > 1 ? ` (${size.models})` : ''} — ${unitPoints(ru, data, list)} ${t('points')}${ru.warlord ? ` [${t('unit.warlord')}]` : ''}`);
    if (enh) lines.push(`${indent}  ✦ ${tr(enh.name)} (+${enh.points})`);
    lines.push(`${indent}  • ${loadoutOf(ru, def, data).map(i => i.name).join(', ')}`);
  };
  for (const role of ROLES) {
    const group = list.units.filter(u => !u.attachedTo && data.unitsById.get(u.unitId)?.role === role);
    if (!group.length) continue;
    lines.push(t('role.' + role).toUpperCase());
    for (const ru of group) {
      describe(ru, '');
      for (const l of leadersOf(ru.uid, list)) describe(l, `  ↳ `);
    }
    lines.push('');
  }
  return lines.join('\n');
}
