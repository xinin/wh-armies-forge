import { loadLang, t, tr } from './i18n.js';
import { loadIndex, loadEdition, loadFaction, loadEmblem } from './data.js';
import {
  initStore, getState, subscribe, update, getActiveList, createList, deleteList, newRosterUnit, cloneRosterUnit,
  importList, onSaveStatus, getSaveStatus, getBackend,
} from './store.js';
import { renderHome, renderHomeHeader, renderFactionPicker } from './home.js';
import { setFactionEmblem } from './icons.js';
import { renderOverview, renderOverviewHeader, OV_TABS } from './overview.js';
import { validate, canAttach, isLeader, battleSizeOf, optionMax, optionMaxEach, tagRival } from './rules.js';
import {
  renderHeader, renderCatalog, renderCatalogItems, renderRoster, renderSidebar, renderModal, sheetState,
} from './render.js';

const $ = sel => document.querySelector(sel);
const ui = { view: 'home', search: '', role: '', modalUnit: null, tab: 'roster', ovTab: OV_TABS[0] };
let index, edition, data;
const editions = new Map();
const factions = new Map(); // faction id → data, only for the factions loaded so far

/* ---------- Boot ---------- */

async function boot() {
  try { sheetState.show = localStorage.getItem('wh-army-forge-sheets') !== '0'; } catch { /* storage unavailable */ }
  await initStore();
  await loadLang(getState().lang);
  index = await loadIndex();
  await Promise.all([...new Set(index.factions.map(f => f.edition))].map(async id => editions.set(id, await loadEdition(id))));
  subscribe(() => render());
  onSaveStatus(renderSaveStatus);
  bindEvents();
  window.addEventListener('hashchange', route);
  await route();
}

// #/ → home, #/list/<id> → builder, #/list/<id>/view → army overview
async function route() {
  const m = location.hash.match(/^#\/list\/([a-z0-9]+)(\/view)?/);
  const list = m && getState().lists.find(l => l.id === m[1]);
  if (list) {
    getState().activeId = list.id;
    await loadForActive();
    ui.view = m[2] ? 'overview' : 'builder';
    ui.modalUnit = null;
  } else {
    if (location.hash && location.hash !== '#/') history.replaceState(null, '', '#/');
    getState().activeId = null;
    ui.view = 'home';
    await ensureFactions(getState().lists.map(l => l.factionId));
  }
  render();
  window.scrollTo(0, 0);
}

const openList = id => { location.hash = `#/list/${id}`; };

// Factions are loaded on demand: the home needs those of the saved lists, the builder the one of its list.
async function ensureFactions(ids) {
  await Promise.all([...new Set(ids)].map(async id => {
    const entry = index.factions.find(f => f.id === id);
    if (entry && !factions.has(id)) factions.set(id, await loadFaction(entry));
  }));
}

// New list for the chosen faction (Strike Force by default; size and name can be changed in the builder).
function createListFor(factionId) {
  const entry = index.factions.find(f => f.id === factionId) ?? index.factions[0];
  const ed = editions.get(entry.edition);
  const bs = ed.battleSizes.find(b => b.id === 'strike-force') ?? ed.battleSizes[0];
  const list = createList({
    factionId: entry.id, edition: entry.edition, battleSize: bs.id,
    name: `${tr(entry.name)} ${bs.points}`,
  });
  closeDialog();
  openList(list.id);
}

async function openFactionPicker() {
  const emblems = new Map(await Promise.all(index.factions.map(async f => [f.id, await loadEmblem(f)])));
  const el = $('#dialog');
  el.innerHTML = renderFactionPicker(index, emblems);
  el.hidden = false;
  el.onclick = e => { if (e.target === el) closeDialog(); };
  el.querySelector('.faction-tile')?.focus();
}

function closeDialog() {
  const el = $('#dialog');
  el.hidden = true;
  el.innerHTML = '';
}

async function loadForActive() {
  const list = getActiveList();
  const entry = index.factions.find(f => f.id === list.factionId) ?? index.factions[0];
  [edition, data] = await Promise.all([loadEdition(list.edition ?? entry.edition), loadFaction(entry)]);
  factions.set(entry.id, data);
  setFactionEmblem(data.emblem);
  // datasheets may have been re-imported since the list was saved: drop units that no longer exist
  // and wargear choices that are no longer valid (saved straight away)
  if (list.units.some(u => !data.unitsById.has(u.unitId)) || list.units.some(u => clampWargear(structuredClone(u)))) {
    update(() => {
      list.units = list.units.filter(u => data.unitsById.has(u.unitId));
      list.units.forEach(u => { if (u.attachedTo && !list.units.some(b => b.uid === u.attachedTo)) u.attachedTo = null; });
      list.units.forEach(u => clampWargear(u));
    });
  }
}

function renderSaveStatus() {
  const el = $('#save-status');
  if (!el) return;
  const st = getSaveStatus();
  const list = getActiveList();
  if (st.backend !== 'file') { el.className = 'save-status warn'; el.textContent = t('save.local'); return; }
  if (st.error) { el.className = 'save-status bad'; el.textContent = `${t('save.error')} (${st.error})`; return; }
  el.className = `save-status ${st.saving ? 'saving' : 'ok'}`;
  el.textContent = st.saving ? t('save.saving') : t('save.saved');
  el.title = list?.file ?? '';
}

/* ---------- Render ---------- */

function render() {
  const state = getState();
  document.body.dataset.view = ui.view;
  if (ui.view === 'home') return renderHomeView(state);
  if (ui.view === 'overview') return renderOverviewView(state);
  const list = getActiveList();
  if (!list || !data) return;
  const issues = validate(list, data, edition);
  document.title = `${list.name || t('list.untitled')} · ${t('app.title')}`;
  $('#header').innerHTML = renderHeader(state, list, index, data, edition);
  const catScroll = $('#catalog-list')?.scrollTop ?? 0;
  $('#catalog').innerHTML = renderCatalog(data, ui, state.customImages);
  $('#catalog-list').scrollTop = catScroll;
  const rosterScroll = $('#roster .roster-body')?.scrollTop ?? 0;
  const openWargear = [...document.querySelectorAll('#roster details.wargear[open]')].map(d => d.closest('[data-uid]')?.dataset.uid);
  $('#roster').innerHTML = renderRoster(list, data, edition, issues, state.customImages);
  $('#roster .roster-body').scrollTop = rosterScroll;
  openWargear.forEach(uid => { const d = document.querySelector(`#roster [data-uid="${uid}"] > .ru-main details.wargear`); if (d) d.open = true; });
  const openDet = [...document.querySelectorAll('#sidebar details[open]')].map(d => d.closest('.det')?.querySelector('[data-id]')?.dataset.id ?? 'army');
  $('#sidebar').innerHTML = renderSidebar(list, data, edition, issues);
  openDet.forEach(id => {
    const d = id === 'army' ? document.querySelector('#sidebar .army-rule') : document.querySelector(`#sidebar [data-id="${id}"]`)?.closest('.det').querySelector('details');
    if (d) d.open = true;
  });
  const errCount = issues.filter(i => i.level === 'error').length;
  $('#tabbar').innerHTML = ['catalog', 'roster', 'sidebar'].map(tab => `
    <button class="${ui.tab === tab ? 'on' : ''}" data-action="tab" data-tab="${tab}">
      ${tab === 'catalog' ? t('catalog') : tab === 'roster' ? t('roster') : t('rules')}
      ${tab === 'sidebar' && errCount ? `<span class="badge">${errCount}</span>` : ''}
    </button>`).join('');
  document.body.dataset.tab = ui.tab;
  renderModalLayer(state);
  renderSaveStatus();
}

function renderOverviewView(state) {
  const list = getActiveList();
  if (!list || !data) return;
  document.title = `${list.name || t('list.untitled')} · ${t('app.title')}`;
  $('#header').innerHTML = renderOverviewHeader(list);
  $('#overview').innerHTML = renderOverview(list, data, edition, state.customImages, ui.ovTab);
  renderModalLayer(state);
}

function renderHomeView(state) {
  setFactionEmblem(null);
  document.title = t('app.title');
  $('#header').innerHTML = renderHomeHeader();
  $('#home').innerHTML = renderHome(state.lists, { index, editions, factions, backend: getBackend() }, state.customImages);
  $('#modal').hidden = true;
}

function renderModalLayer(state) {
  const layer = $('#modal');
  const def = ui.modalUnit && data.unitsById.get(ui.modalUnit);
  layer.hidden = !def;
  layer.innerHTML = def ? renderModal(def, data, state.customImages) : '';
}

/* ---------- In-app dialogs ---------- */
// Native confirm()/prompt() are silently blocked in some embedded browsers (e.g. VS Code's Simple Browser),
// so the app uses its own dialog.

function openDialog(html) {
  const el = $('#dialog');
  el.innerHTML = `<div class="dialog-card" role="alertdialog" aria-modal="true">${html}</div>`;
  el.hidden = false;
  return el;
}

function askConfirm(message, okLabel) {
  return new Promise(resolve => {
    const el = openDialog(`
      <p>${message.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))}</p>
      <div class="dialog-actions">
        <button class="btn" data-answer="no">${t('dialog.cancel')}</button>
        <button class="btn danger-solid" data-answer="yes">${okLabel}</button>
      </div>`);
    const done = answer => {
      el.hidden = true;
      el.innerHTML = '';
      document.removeEventListener('keydown', onKey, true);
      resolve(answer);
    };
    const onKey = e => {
      if (e.key === 'Escape') { e.stopPropagation(); done(false); }
    };
    el.onclick = e => {
      const b = e.target.closest('[data-answer]');
      if (b) done(b.dataset.answer === 'yes');
      else if (e.target === el) done(false);
    };
    document.addEventListener('keydown', onKey, true);
    el.querySelector('[data-answer="yes"]').focus();
  });
}

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 2200);
}

/* ---------- Mutations ---------- */

const withList = fn => update(s => fn(s.lists.find(l => l.id === s.activeId), s));
const findRu = (list, uid) => list.units.find(u => u.uid === uid);

function addUnit(unitId, attachTo = null) {
  const def = data.unitsById.get(unitId);
  const ru = newRosterUnit(def);
  withList(list => {
    list.units.push(ru);
    const bg = attachTo && findRu(list, attachTo);
    if (bg && canAttach(ru, bg, list, data, edition)) ru.attachedTo = bg.uid;
  });
  toast(`+ ${tr(def.name)}`);
}

function removeUnit(list, uid) {
  list.units = list.units.filter(u => u.uid !== uid);
  list.units.forEach(u => { if (u.attachedTo === uid) u.attachedTo = null; });
}

function attach(leaderUid, bgUid) {
  withList(list => {
    const leader = findRu(list, leaderUid);
    const bg = findRu(list, bgUid);
    if (leader && bg && canAttach(leader, bg, list, data, edition)) {
      leader.attachedTo = bg.uid;
      // a leader can't keep its own followers
      list.units.forEach(u => { if (u.attachedTo === leader.uid) u.attachedTo = null; });
    }
  });
}

/* ---------- Events ---------- */

function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('input', e => {
    if (e.target.dataset.action === 'search') {
      ui.search = e.target.value;
      $('#catalog-list').innerHTML = renderCatalogItems(data, ui, getState().customImages);
    }
  });
  // remember datasheet panels the user opened/closed by hand across re-renders
  document.addEventListener('toggle', e => {
    const uid = e.target.dataset?.sheet;
    if (uid) sheetState.overrides.set(uid, e.target.open);
  }, true);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && $('#dialog .picker')) return closeDialog();
    if (e.key === 'Escape' && ui.modalUnit) { ui.modalUnit = null; render(); }
    if (e.key === 'Enter' && e.target.matches?.('.list-card')) openList(e.target.dataset.id);
  });
  $('#modal').addEventListener('click', e => { if (e.target.id === 'modal') { ui.modalUnit = null; render(); } });
  bindDnd();
}

async function onClick(e) {
  const el = e.target.closest('[data-action]');
  if (!el || el.tagName === 'SELECT' || el.tagName === 'INPUT') return;
  const { action, uid } = el.dataset;
  switch (action) {
    case 'print': return window.print();
    case 'open-faction-picker': return openFactionPicker();
    case 'close-picker': return closeDialog();
    case 'pick-faction': return createListFor(el.dataset.id);
    case 'ov-tab': {
      // if the tab bar is stuck at the top, show the new tab from its start
      const stuck = $('.ov-nav').getBoundingClientRect().top <= 1;
      ui.ovTab = el.dataset.tab;
      render();
      if (stuck) document.getElementById(`ov-${ui.ovTab}`)?.scrollIntoView({ block: 'start' });
      return;
    }
    case 'add-unit': return addUnit(el.dataset.unit);
    case 'details': ui.modalUnit = el.dataset.unit; return render();
    case 'close-modal': ui.modalUnit = null; return render();
    case 'tab': ui.tab = el.dataset.tab; return render();
    case 'toggle-sheets':
      sheetState.show = !sheetState.show;
      sheetState.overrides.clear();
      try { localStorage.setItem('wh-army-forge-sheets', sheetState.show ? '1' : '0'); } catch { /* storage unavailable */ }
      return render();
    case 'filter-role': ui.role = el.dataset.role; return render();
    case 'remove': return withList(list => removeUnit(list, uid));
    case 'duplicate-unit': return withList(list => {
      const ru = findRu(list, uid);
      const copy = cloneRosterUnit(ru);
      list.units.splice(list.units.indexOf(ru) + 1, 0, copy);
    });
    case 'warlord': return withList(list => {
      const ru = findRu(list, uid);
      const next = !ru.warlord;
      list.units.forEach(u => { u.warlord = false; });
      ru.warlord = next;
    });
    case 'detach': return withList(list => { findRu(list, uid).attachedTo = null; });
    case 'toggle-detachment': return withList(list => {
      const id = el.dataset.id;
      if (list.detachments.includes(id)) {
        list.detachments = list.detachments.filter(d => d !== id);
      } else {
        const bs = battleSizeOf(list, edition);
        const used = list.detachments.reduce((s, d) => s + data.detachmentsById.get(d).cost, 0);
        const det = data.detachmentsById.get(id);
        if (used + det.cost <= bs.detachmentPoints && !tagRival(list, data, det)) list.detachments.push(id);
      }
    });
    case 'open-list': return openList(el.dataset.id);
    case 'duplicate-list': {
      const src = getState().lists.find(l => l.id === el.dataset.id);
      importList({ ...structuredClone(src), name: `${src.name} (2)` });
      return toast(t('list.duplicated'));
    }
    case 'delete-list': {
      const target = getState().lists.find(l => l.id === el.dataset.id);
      if (!target || !await askConfirm(t('list.deleteConfirm', { name: target.name }), t('list.delete'))) return;
      deleteList(target.id);
      return toast(t('list.deleted'));
    }
    case 'battle-size-pick': return withList(list => { list.battleSize = el.dataset.size; });
    case 'set-lang':
      await loadLang(el.dataset.lang);
      return update(s => { s.lang = el.dataset.lang; });
    case 'image-clear': return update(st => { delete st.customImages[el.dataset.unit]; });
    case 'export': return exportJson(getState().lists.find(l => l.id === el.dataset.id));
  }
}

async function onChange(e) {
  const el = e.target;
  const { action, uid, opt } = el.dataset;
  if (!action) return;
  switch (action) {
    case 'list-name': return withList(list => { list.name = el.value.trim(); });
    case 'battle-size': return withList(list => { list.battleSize = edition.battleSizes[+el.value].id; });
    case 'size': return withList(list => {
      const ru = findRu(list, uid);
      ru.sizeIdx = +el.value;
      clampWargear(ru);
    });
    case 'enhancement': return withList(list => {
      const ru = findRu(list, uid);
      ru.enhancement = el.value || null;
      // losing an enhancement that granted Leader can invalidate the attachment
      const bg = ru.attachedTo && findRu(list, ru.attachedTo);
      if (bg && !canAttach(ru, bg, list, data, edition)) ru.attachedTo = null;
    });
    case 'attach': return el.value && attach(uid, el.value);
    case 'wg-swap': return withList(list => { findRu(list, uid).wargear[opt] = el.value; });
    case 'wg-toggle': return withList(list => {
      findRu(list, uid).wargear[opt] = el.type === 'checkbox' ? (el.checked ? 1 : 0) : Math.max(0, +el.value || 0);
      clampWargear(findRu(list, uid));
    });
    case 'wg-pool': return withList(list => {
      const ru = findRu(list, uid);
      ru.wargear[opt] = { ...ru.wargear[opt], [el.dataset.weapon]: Math.max(0, +el.value || 0) };
      clampWargear(ru, el.dataset.weapon);
    });
    case 'image-url': return setStoreImage(el.dataset.unit, el.value.trim());
    case 'image-file': return setImageFromFile(el.dataset.unit, el.files[0]);
    case 'import': return importJson(el.files[0]);
  }
}

// Keep pool/toggle counts within the limits for the current unit size.
// Keep the wargear choices of a unit valid for its datasheet and size: unknown options/choices are dropped,
// counts are capped (the value just edited is kept, the others are trimmed first). Returns true if anything changed.
function clampWargear(ru, lastChanged) {
  const def = data.unitsById.get(ru.unitId);
  if (!def) return false;
  const models = def.sizes[ru.sizeIdx]?.models ?? def.sizes[0].models;
  const before = JSON.stringify(ru.wargear ?? {});
  const next = {};
  for (const opt of def.wargear ?? []) {
    const v = ru.wargear?.[opt.id];
    const max = optionMax(opt, models);
    if (opt.type === 'swap') {
      next[opt.id] = opt.choices.includes(v) && !(opt.minModels && models < opt.minModels) ? v : '';
    } else if (opt.type === 'toggle') {
      next[opt.id] = Math.min(Number(v) || 0, opt.scope === 'all' ? 1 : max);
    } else if (opt.type === 'pool') {
      const pool = {};
      for (const c of opt.choices) if (v?.[c] > 0) pool[c] = Math.min(Number(v[c]), optionMaxEach(opt, models, c));
      let total = Object.values(pool).reduce((a, b) => a + b, 0);
      for (const k of Object.keys(pool).sort((a, b) => (a === lastChanged) - (b === lastChanged))) {
        if (total <= max) break;
        const cut = Math.min(pool[k], total - max);
        pool[k] -= cut;
        total -= cut;
      }
      next[opt.id] = pool;
    }
  }
  ru.wargear = next;
  return JSON.stringify(next) !== before;
}

/* ---------- Drag & drop ---------- */

let dragging = null; // { kind: 'cat' | 'ru', id }

function bindDnd() {
  document.addEventListener('dragstart', e => {
    const src = e.target.closest?.('[data-drag]');
    if (!src) return;
    const [kind, id] = src.dataset.drag.split(':');
    dragging = { kind, id };
    e.dataTransfer.setData('text/plain', src.dataset.drag);
    e.dataTransfer.effectAllowed = kind === 'cat' ? 'copy' : 'move';
    e.stopPropagation();
    highlightTargets();
    // defer styling of the source so the browser's drag image is taken from the unstyled card
    requestAnimationFrame(() => {
      document.body.classList.add('dragging');
      src.classList.add('drag-src');
    });
  });
  document.addEventListener('dragend', () => {
    dragging = null;
    document.body.classList.remove('dragging');
    document.querySelectorAll('.drag-src, .can-drop, .drop-over').forEach(n => n.classList.remove('drag-src', 'can-drop', 'drop-over'));
  });
  document.addEventListener('dragover', e => {
    if (!dragging && isFileDrag(e)) {
      // always cancel, otherwise dropping a file outside a zone makes the browser open it
      e.preventDefault();
      const zone = e.target.closest?.('[data-img-drop]');
      e.dataTransfer.dropEffect = zone ? 'copy' : 'none';
      document.querySelectorAll('.img-over').forEach(n => n !== zone && n.classList.remove('img-over'));
      zone?.classList.add('img-over');
      return;
    }
    if (!dragging) return;
    const target = dropTarget(e.target);
    if (!target) return;
    e.preventDefault();
    document.querySelectorAll('.drop-over').forEach(n => n !== target && n.classList.remove('drop-over'));
    target.classList.add('drop-over');
  });
  document.addEventListener('dragleave', e => {
    if (e.target.classList?.contains('img-over') && !e.target.contains(e.relatedTarget)) e.target.classList.remove('img-over');
  });
  document.addEventListener('drop', e => {
    if (!dragging && isFileDrag(e)) {
      e.preventDefault();
      document.querySelectorAll('.img-over').forEach(n => n.classList.remove('img-over'));
      const zone = e.target.closest?.('[data-img-drop]');
      const file = [...e.dataTransfer.files].find(f => f.type.startsWith('image/'));
      if (zone && file) setImageFromFile(zone.dataset.imgDrop, file);
      return;
    }
    if (!dragging) return;
    const target = dropTarget(e.target);
    if (!target) return;
    e.preventDefault();
    const { kind, id } = dragging;
    if (target.dataset.drop === 'catalog') {
      if (kind === 'ru') withList(list => removeUnit(list, id));
    } else if (target.dataset.drop === 'unit') {
      if (kind === 'cat') addUnit(id, target.dataset.uid);
      else attach(id, target.dataset.uid);
    } else if (target.dataset.drop === 'roster') {
      if (kind === 'cat') addUnit(id);
      else withList(list => { findRu(list, id).attachedTo = null; });
    }
  });
}

// The innermost valid drop zone under the pointer for what's being dragged.
function dropTarget(node) {
  const card = node.closest?.('article.ru[data-uid]');
  if (card) {
    const list = getActiveList();
    if (leaderProbe() && canAttach(leaderProbe(), findRu(list, card.dataset.uid), list, data, edition)) return card;
    // a full or invalid bodyguard is not a drop zone (falling through to the roster would detach the leader)
    if (dragging.kind === 'ru') return null;
  }
  if (dragging.kind === 'ru' && node.closest?.('#catalog')) return $('#catalog');
  return node.closest?.('[data-drop="roster"]') ?? null;
}

// The unit being dragged, if it is a leader (a fresh one when it comes from the catalog).
function leaderProbe() {
  if (!dragging) return null;
  if (!dragging.probe) {
    dragging.probe = dragging.kind === 'cat'
      ? newRosterUnit(data.unitsById.get(dragging.id))
      : findRu(getActiveList(), dragging.id);
  }
  return dragging.probe && isLeader(dragging.probe, data) ? dragging.probe : null;
}

function highlightTargets() {
  const list = getActiveList();
  const probe = leaderProbe();
  if (!probe) return;
  document.querySelectorAll('#roster article.ru[data-uid]').forEach(card => {
    const bg = list.units.find(u => u.uid === card.dataset.uid);
    if (canAttach(probe, bg, list, data, edition)) card.classList.add('can-drop');
  });
}

/* ---------- Unit images ---------- */

const isFileDrag = e => [...(e.dataTransfer?.types ?? [])].includes('Files');

// Downscale to keep localStorage usage small (~20-40 KB per image).
async function imageToDataUrl(file, max = 400) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
  const webp = canvas.toDataURL('image/webp', 0.85);
  return webp.startsWith('data:image/webp') ? webp : canvas.toDataURL('image/jpeg', 0.85);
}

async function setImageFromFile(unitId, file) {
  if (!file?.type.startsWith('image/')) return;
  try {
    const url = await imageToDataUrl(file);
    const prev = getState().customImages[unitId];
    const saved = update(st => { st.customImages[unitId] = url; });
    if (!saved) {
      update(st => { if (prev) st.customImages[unitId] = prev; else delete st.customImages[unitId]; });
      throw new Error('quota');
    }
    toast(t('unit.imageSaved'));
  } catch {
    toast(t('unit.imageError'));
  }
}

// Webstore picture URLs are shared data: saved by server.py into data/factions/<f>/images.json.
// Without the server they can only be kept in this browser.
async function setStoreImage(unitId, url) {
  if (getBackend() !== 'file') {
    return update(s => { if (url) s.customImages[unitId] = url; else delete s.customImages[unitId]; });
  }
  try {
    const res = await fetch(`api/images/${data.entry.path}/${unitId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error(res.status);
    data.unitsById.get(unitId).storeImage = url || null;
    render();
    toast(t('unit.imageSaved'));
  } catch {
    toast(t('unit.imageError'));
  }
}

/* ---------- Import / export ---------- */

function exportJson(list) {
  const blob = new Blob([JSON.stringify({ format: 'wh-army-forge/1', list }, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${(list.name || 'army').replace(/[^\w-]+/g, '_')}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importJson(file) {
  if (!file) return;
  try {
    const obj = JSON.parse(await file.text());
    const list = obj.list ?? obj;
    if (!Array.isArray(list.units) || !list.factionId) throw new Error('bad format');
    await ensureFactions([list.factionId]);
    importList(list);
    toast(t('list.imported'));
  } catch {
    toast(t('list.importError'));
  }
}

$('#catalog').dataset.drop = 'catalog';
boot().catch(err => {
  console.error(err);
  document.body.innerHTML = `<pre class="fatal">${err.message}\n\nStart the app with ./serve.sh (python3 server.py)</pre>`;
});
