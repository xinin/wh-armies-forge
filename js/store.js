// App state. Army lists are saved as JSON files through server.py (armies/<name>-<id>.json);
// if the app is served without that API they fall back to localStorage.
// Preferences (language, custom images) always live in localStorage.
// Lists only store ids + choices, never points, so a new points.json is picked up automatically.
const KEY = 'wh-army-forge-v1';
const API = 'api/lists';
const SAVE_DELAY = 400;

const uid = () => Math.random().toString(36).slice(2, 10);

const defaults = () => ({
  lang: (navigator.language || 'es').startsWith('es') ? 'es' : 'en',
  lists: [],
  activeId: null,
  customImages: {},
});

let state = defaults();
let backend = 'local'; // 'file' when server.py answers
const listeners = new Set();
const statusListeners = new Set();
const snapshots = new Map(); // list id → last saved JSON (without `updated`)
const timers = new Map();
let pending = 0;
let lastError = null;

const snap = list => JSON.stringify({ ...list, updated: undefined, file: undefined });

function readLocal() {
  try { return { ...defaults(), ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return defaults(); }
}

function savePrefs() {
  const { lang, customImages } = state;
  const payload = backend === 'file' ? { lang, customImages } : { lang, customImages, lists: state.lists };
  try { localStorage.setItem(KEY, JSON.stringify(payload)); return true; } catch { return false; /* private mode or quota */ }
}

export async function initStore() {
  const local = readLocal();
  state = { ...defaults(), lang: local.lang, customImages: local.customImages ?? {} };
  try {
    const res = await fetch(API, { cache: 'no-store' });
    if (!res.ok) throw new Error(res.status);
    state.lists = await res.json();
    backend = 'file';
    state.lists.forEach(l => snapshots.set(l.id, snap(l)));
    // one-off migration of lists created before the file backend existed
    const fresh = (local.lists ?? []).filter(l => !state.lists.some(x => x.id === l.id));
    if (fresh.length) {
      state.lists.push(...fresh);
      fresh.forEach(l => scheduleSave(l.id, 0));
    }
  } catch {
    backend = 'local';
    state.lists = local.lists ?? [];
  }
  savePrefs();
}

export const getBackend = () => backend;
export const getState = () => state;
export const subscribe = fn => listeners.add(fn);
export const onSaveStatus = fn => statusListeners.add(fn);
export const getSaveStatus = () => ({ backend, saving: pending > 0, error: lastError });
const emitStatus = () => statusListeners.forEach(fn => fn(getSaveStatus()));

function scheduleSave(id, delay = SAVE_DELAY) {
  clearTimeout(timers.get(id));
  if (!timers.has(id)) { pending++; emitStatus(); }
  timers.set(id, setTimeout(() => persist(id), delay));
}

// Requests for the same list run one after another, so a DELETE can never overtake a PUT
// that is still writing the file (which would bring the list back).
const chains = new Map();

function persist(id) {
  timers.delete(id);
  const run = (chains.get(id) ?? Promise.resolve()).then(() => send(id));
  chains.set(id, run);
  run.finally(() => { if (chains.get(id) === run) chains.delete(id); });
}

async function send(id) {
  const list = state.lists.find(l => l.id === id);
  try {
    const res = list
      ? await fetch(`${API}/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(list) })
      : await fetch(`${API}/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (list) list.file = (await res.json()).file;
    lastError = null;
  } catch (e) {
    lastError = e.message;
  } finally {
    pending--;
    emitStatus();
  }
}

// Detect which lists changed (or disappeared) since the last save and write only those.
function syncLists() {
  const ids = new Set(state.lists.map(l => l.id));
  for (const list of state.lists) {
    const s = snap(list);
    if (snapshots.get(list.id) === s) continue;
    snapshots.set(list.id, s);
    list.updated = Date.now();
    if (backend === 'file') scheduleSave(list.id);
  }
  for (const id of [...snapshots.keys()]) {
    if (ids.has(id)) continue;
    snapshots.delete(id);
    if (backend === 'file') scheduleSave(id, 0);
  }
}

export function update(fn) {
  fn(state);
  syncLists();
  const saved = savePrefs();
  listeners.forEach(l => l(state));
  return saved;
}

export function getActiveList() {
  return state.lists.find(l => l.id === state.activeId) ?? null;
}

export function createList({ factionId, edition, battleSize, pointsLimit, name }) {
  const list = {
    id: uid(),
    name,
    factionId,
    edition,
    battleSize,
    pointsLimit,
    detachments: [],
    units: [],
    created: Date.now(),
  };
  update(s => { s.lists.push(list); s.activeId = list.id; });
  return list;
}

export function deleteList(id) {
  update(s => {
    s.lists = s.lists.filter(l => l.id !== id);
    if (s.activeId === id) s.activeId = null;
  });
}

export function newRosterUnit(unitDef) {
  const wargear = {};
  for (const opt of unitDef.wargear ?? []) {
    if (opt.type === 'swap') wargear[opt.id] = '';
    else if (opt.type === 'pool') wargear[opt.id] = {};
    else if (opt.type === 'toggle') wargear[opt.id] = 0;
  }
  return {
    uid: uid(),
    unitId: unitDef.id,
    sizeIdx: 0,
    wargear,
    enhancement: null,
    warlord: false,
    attachedTo: null,
  };
}

export function cloneRosterUnit(ru) {
  return { ...structuredClone(ru), uid: uid(), warlord: false, enhancement: null, attachedTo: null };
}

export function importList(obj) {
  const { file, ...rest } = obj;
  const list = { ...rest, id: uid(), created: Date.now() };
  update(s => { s.lists.push(list); });
  return list;
}
