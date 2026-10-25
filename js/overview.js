// "Army overview": read-only view of a finished list — every unit with its wargear and abilities,
// the chosen detachments (rule, enhancements, stratagems), the army rule and the core stratagems.
import { t, tr } from './i18n.js';
import { icon } from './icons.js';
import { unitImg, imgFrame, ROLE_COLORS } from './images.js';
import { battleSizeOf, listPoints, unitPoints, leadersOf, validate } from './rules.js';
import { esc, brandHtml, statRows, weaponTable, abilitiesBlock, ROLES } from './render.js';
import { langToggle } from './home.js';

const para = text => esc(tr(text)).split('\n').map(l => `<p>${l}</p>`).join('');

export function renderOverviewHeader(list) {
  return `${brandHtml()}
  <div class="list-switch">
    <a class="btn" href="#/">← ${t('home.back')}</a>
    <a class="btn" href="#/list/${list.id}">✎ ${t('overview.edit')}</a>
  </div>
  <div class="header-actions">
    <button class="btn" data-action="print">⎙ ${t('overview.print')}</button>
    ${langToggle()}
  </div>`;
}

export function renderOverview(list, data, edition, customImages) {
  const bs = battleSizeOf(list, edition);
  const pts = listPoints(list, data);
  const errors = validate(list, data, edition).filter(i => i.level === 'error');
  const warlord = list.units.find(u => u.warlord);
  const top = list.units.filter(u => !u.attachedTo);
  const roleOf = u => leadersOf(u.uid, list).length ? 'character' : data.unitsById.get(u.unitId)?.role;
  const dets = list.detachments.map(id => data.detachmentsById.get(id)).filter(Boolean);
  const models = list.units.reduce((n, u) => n + (data.unitsById.get(u.unitId)?.sizes[u.sizeIdx]?.models ?? 0), 0);

  return `
  <div class="ov-inner">
    <section class="ov-hero">
      <div class="ov-hero-emblem">${icon('emblemFull')}</div>
      <div class="ov-hero-text">
        <div class="ov-kicker">${esc(tr(data.faction.name))} · ${esc(tr(bs.name))}</div>
        <h1>${esc(list.name || t('list.untitled'))}</h1>
        <div class="ov-facts">
          <span class="ov-fact ${pts > list.pointsLimit ? 'bad' : ''}"><b>${pts}</b> / ${list.pointsLimit} ${t('points')}</span>
          <span class="ov-fact"><b>${list.units.length}</b> ${t('home.units')} · <b>${models}</b> ${t('unit.models')}</span>
          ${dets.map(d => `<span class="ov-fact det">${icon('stratTactic')}${esc(tr(d.name))}</span>`).join('')}
          ${warlord ? `<span class="ov-fact">${icon('emblem')}${t('unit.warlord')}: <b>${esc(tr(data.unitsById.get(warlord.unitId)?.name))}</b></span>` : ''}
          <span class="ov-fact ${errors.length ? 'bad' : 'good'}">${errors.length ? `${icon('diamond')}${errors.length} ${t('overview.errors')}` : `${icon('stratPloy')}${t('validation.ok')}`}</span>
        </div>
      </div>
    </section>

    <nav class="ov-nav">
      <a href="#ov-units" data-action="ov-jump">${t('overview.units')}</a>
      <a href="#ov-detachments" data-action="ov-jump">${t('detachments')}</a>
      <a href="#ov-army-rule" data-action="ov-jump">${t('rules.armyRule')}</a>
      <a href="#ov-core" data-action="ov-jump">${t('overview.coreStratagems')}</a>
    </nav>

    ${errors.length ? `<ul class="issues ov-issues">${errors.map(i => `<li class="err">${esc(i.msg)}</li>`).join('')}</ul>` : ''}

    <section id="ov-units" class="ov-section">
      <h2 class="ov-title">${icon('emblemFull')}${t('overview.units')}</h2>
      ${ROLES.map(role => {
        const group = top.filter(u => roleOf(u) === role);
        if (!group.length) return '';
        return `<h3 class="role-head" style="--role:${ROLE_COLORS[role]}">${icon('diamond', 'role-diamond')}<span>${t('role.' + role)}</span></h3>
          <div class="ov-units">${group.map(u => unitBlock(u, list, data, customImages)).join('')}</div>`;
      }).join('')}
      ${top.length ? '' : `<p class="muted">${t('roster.empty')}</p>`}
    </section>

    <section id="ov-detachments" class="ov-section">
      <h2 class="ov-title">${icon('stratTactic')}${t('detachments')}</h2>
      ${dets.length ? dets.map(d => detachmentBlock(d, list, data)).join('') : `<p class="muted">${t('err.noDetachment')}</p>`}
    </section>

    <section id="ov-army-rule" class="ov-section">
      <h2 class="ov-title">${icon('emblem')}${t('rules.armyRule')}: ${esc(tr(data.faction.armyRule.name))}</h2>
      <div class="ov-rule">
        ${para(data.faction.armyRule.text)}
        <div class="ov-orders">${(data.faction.armyRule.orders ?? []).map(o => `<div class="ov-order"><b>${esc(tr(o.name))}</b><span>${esc(tr(o.text))}</span></div>`).join('')}</div>
      </div>
    </section>

    <section id="ov-core" class="ov-section">
      <h2 class="ov-title">${icon('stratPloy')}${t('overview.coreStratagems')}</h2>
      <div class="strat-grid">${(edition.coreStratagems ?? []).map(stratCard).join('') || `<p class="muted">${t('overview.noStratagems')}</p>`}</div>
    </section>
  </div>`;
}

function unitCard(ru, def, data, customImages, list, extraClass = '') {
  const size = def.sizes[ru.sizeIdx];
  const enh = ru.enhancement && data.enhancements.get(ru.enhancement);
  return `
  <article class="ov-unit ${extraClass}" style="--role:${ROLE_COLORS[def.role]}">
    <header class="ov-unit-head">
      <div class="thumb ${imgFrame(def, customImages)}" data-action="details" data-unit="${def.id}">${unitImg(def, customImages)}</div>
      <div class="ov-unit-title">
        <h4 data-action="details" data-unit="${def.id}">${esc(tr(def.name))}</h4>
        <div class="ov-unit-meta">${size.models} ${t(size.models === 1 ? 'unit.model' : 'unit.models')}
          ${ru.warlord ? `<span class="tag warlord">${icon('emblem')}${t('unit.warlord')}</span>` : ''}</div>
      </div>
      <div class="ov-unit-pts">${unitPoints(ru, data, list)}<small>${t('points')}</small></div>
    </header>
    ${statRows(def)}
    ${weaponTable(ru, def, data)}
    ${enh ? `<div class="ov-enh">${icon(enh.type === 'upgrade' ? 'stratPloy' : 'diamond')}<div><b>${esc(tr(enh.name))}</b> <small>(+${enh.points} ${t('points')} · ${esc(tr(data.detachmentsById.get(enh.detachmentId)?.name))})</small><p>${esc(tr(enh.full ?? enh.text))}</p></div></div>` : ''}
    ${abilitiesBlock(def)}
  </article>`;
}

function unitBlock(ru, list, data, customImages) {
  const def = data.unitsById.get(ru.unitId);
  if (!def) return '';
  const leaders = leadersOf(ru.uid, list);
  if (!leaders.length) return unitCard(ru, def, data, customImages, list);
  const total = unitPoints(ru, data, list) + leaders.reduce((a, l) => a + unitPoints(l, data, list), 0);
  const names = [...leaders.map(l => tr(data.unitsById.get(l.unitId)?.name)), tr(def.name)];
  return `
  <section class="ov-attached">
    <div class="ov-attached-head">${icon('emblemFull')}<span>${t('overview.attachedUnit')}: <b>${esc(names.join(' + '))}</b></span><span class="ov-attached-pts">${total} ${t('points')}</span></div>
    ${leaders.map(l => unitCard(l, data.unitsById.get(l.unitId), data, customImages, list, 'leader')).join('')}
    <div class="ov-led-label">${t('unit.leading')}</div>
    ${unitCard(ru, def, data, customImages, list, 'led')}
  </section>`;
}

function detachmentBlock(det, list, data) {
  const strats = data.stratagems?.[det.id] ?? [];
  const takenBy = id => list.units.filter(u => u.enhancement === id).map(u => tr(data.unitsById.get(u.unitId)?.name));
  return `
  <article class="ov-det">
    <header class="ov-det-head">${icon('stratTactic')}<h3>${esc(tr(det.name))}</h3><span class="ov-det-cost">${det.cost} DP</span></header>
    <div class="ov-rule">
      <h4>${t('rules.detachmentRule')}: ${esc(tr(det.rule.name))}</h4>
      ${para(det.rule.full ?? det.rule.text)}
    </div>
    <h4 class="ov-sub">${t('overview.enhancements')}</h4>
    <div class="ov-enh-list">
      ${det.enhancements.map(e => {
        const enh = data.enhancements.get(e.id);
        const who = takenBy(e.id);
        return `<div class="ov-enh-item ${who.length ? 'taken' : ''}">
          <div class="ov-enh-name">${icon(who.length ? 'stratPloy' : 'diamond')}<b>${esc(tr(e.name))}</b><span>${enh.points} ${t('points')}${enh.type === 'upgrade' ? ` · ${t('unit.upgrade')}` : ''}</span></div>
          ${who.length ? `<div class="ov-enh-who">${t('overview.takenBy')}: ${esc(who.join(', '))}</div>` : ''}
          <p>${esc(tr(e.full ?? e.text))}</p>
        </div>`;
      }).join('')}
    </div>
    <h4 class="ov-sub">${t('overview.stratagems')}</h4>
    <div class="strat-grid">${strats.map(stratCard).join('') || `<p class="muted">${t('overview.noStratagems')}</p>`}</div>
  </article>`;
}

function stratCard(s) {
  const kindIcon = /tactic/i.test(s.kind ?? '') ? 'stratTactic' : 'stratPloy';
  return `
  <article class="strat turn-${s.turn ?? 'either'}">
    <header class="strat-head">
      <div class="strat-icon">${icon(kindIcon)}</div>
      <div class="strat-title"><h5>${esc(tr(s.name))}</h5>
        <div class="strat-type">${esc(s.kind ? `${s.source} – ${s.kind}` : s.source)}</div></div>
      <div class="strat-cp">${s.cp}<small>CP</small></div>
    </header>
    <div class="strat-tags">
      ${s.phase ? `<span>${t('phase.' + s.phase)}</span>` : ''}
      ${s.turn ? `<span class="turn">${t('turn.' + s.turn)}</span>` : ''}
    </div>
    ${s.legend ? `<p class="strat-legend">${esc(tr(s.legend))}</p>` : ''}
    <dl>
      ${['when', 'target', 'effect', 'restrictions'].filter(k => s[k]).map(k => `<dt>${t('strat.' + k)}</dt><dd>${esc(tr(s[k]))}</dd>`).join('')}
    </dl>
  </article>`;
}
