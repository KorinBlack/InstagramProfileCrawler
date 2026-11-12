"use strict";

/* ====================================================================
   Profile Crawler GUI - vanilla JS, hash routes, no build step.
   ==================================================================== */

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = new Intl.NumberFormat("it-IT");
const fmtInt = (n) => nf.format(n || 0);

const state = { schema: null, meta: null, dirty: false, cleanup: null, lastHash: location.hash };

/* ------------------------------------------------------------------ */
/* API                                                                 */
/* ------------------------------------------------------------------ */

async function api(path, { method = "GET", body } = {}) {
  const headers = { "x-requested-with": "crawler-gui" };
  if (body !== undefined) headers["content-type"] = "application/json";
  const res = await fetch("/api" + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let msg = res.statusText;
    try { const data = await res.json(); msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail); } catch (_) { /* keep statusText */ }
    throw new Error(msg || `Errore ${res.status}`);
  }
  return res.json();
}

async function schema() {
  if (!state.schema) state.schema = await api("/schema");
  return state.schema;
}

/* ------------------------------------------------------------------ */
/* Formatting                                                          */
/* ------------------------------------------------------------------ */

const MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return `oggi, ${hm}`;
  if (sameDay(d, yesterday)) return `ieri, ${hm}`;
  const year = d.getFullYear() !== now.getFullYear() ? ` ${d.getFullYear()}` : "";
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${year}, ${hm}`;
}

function fmtDuration(start, end) {
  if (!start) return "";
  const s = Math.max(0, Math.round(((end ? new Date(end) : new Date()) - new Date(start)) / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${s % 60} s`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

const STATUS = {
  queued: ["neutral", "In coda"],
  running: ["live", "In corso"],
  ok: ["ok", "Completata"],
  partial: ["warn", "Parziale"],
  failed: ["bad", "Fallita"],
  cancelled: ["neutral", "Interrotta"],
  interrupted: ["warn", "Interrotta dal server"],
};
const statusPill = (s) => { const [cls, label] = STATUS[s] || ["neutral", s]; return `<span class="pill ${cls}">${esc(label)}</span>`; };
const isActive = (s) => s === "queued" || s === "running";

const SOURCE_LABEL = { job: "job", global: "globale", env: ".env", default: "predefinito" };
const STAGE_LABEL = { scrape: "Scraping", download: "Download", filter: "Filtro", optimize: "Ottimizzazione", caption: "Caption", profile: "Profilo" };
const CHOICE_LABEL = {
  engine: { ollama: "Ollama", "llama.cpp": "llama.cpp", strata: "Strata" },
  process_scope: { new: "Solo nuove", all: "Tutto il dataset" },
  caption_format: { text: ".txt", json: ".json", pairs: "Coppie .json" },
};
const SOURCE_KIND = { post: "post", highlight: "in evidenza", story: "storia" };

function plural(n, one, many) { return `${fmtInt(n)} ${n === 1 ? one : many}`; }

/* API keys come back from the server as "__secret__:…abcd": the real value never reaches the page */
const SECRET = "__secret__:";
const isMasked = (v) => typeof v === "string" && v.startsWith(SECRET);
const secretLabel = (v) => (isMasked(v) ? `impostata (${v.slice(SECRET.length)})` : v ? "impostata" : "nessuna");

/* ------------------------------------------------------------------ */
/* Icons (16px outline, 1.5 stroke)                                    */
/* ------------------------------------------------------------------ */

const ICON = {
  home: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M2.5 7 8 2.5 13.5 7v6.5h-3.5v-4h-4v4H2.5z"/></svg>',
  filter: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M2.5 3h11l-4.2 5v4.5l-2.6 1V8z"/></svg>',
  jobs: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M8 2 14 5 8 8 2 5Z"/><path d="m2 8 6 3 6-3M2 11l6 3 6-3"/></svg>',
  runs: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1.5"/></svg>',
  data: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><rect x="2" y="2.5" width="12" height="11" rx="2"/><path d="m2.5 11 3.5-3.5 3 3 1.5-1.5 3 3"/><circle cx="10.5" cy="5.8" r="1"/></svg>',
  settings: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 4.5h7M12 4.5h2M2 11.5h2M7 11.5h7"/><circle cx="10.5" cy="4.5" r="1.5"/><circle cx="5.5" cy="11.5" r="1.5"/></svg>',
  account: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.75 13.5c.8-2.4 2.8-3.5 5.25-3.5s4.45 1.1 5.25 3.5"/></svg>',
  play: '<svg viewBox="0 0 14 14" fill="currentColor"><path d="M4 2.5v9l7.5-4.5z"/></svg>',
  close: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="m5 5 10 10M15 5 5 15"/></svg>',
};

/* ------------------------------------------------------------------ */
/* UI helpers                                                          */
/* ------------------------------------------------------------------ */

let toastTimer;
function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), error ? 5000 : 2600);
}

function confirmDialog({ title, body, confirm = "Conferma", danger = false }) {
  const dlg = $("#dialog");
  dlg.innerHTML = `
    <form method="dialog">
      <div class="d-body"><h2>${esc(title)}</h2><p>${body}</p></div>
      <div class="d-foot">
        <button class="btn" value="cancel">Annulla</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" value="ok">${esc(confirm)}</button>
      </div>
    </form>`;
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true }));
}

function setCrumbs(items) {
  $("#crumbs").innerHTML = items.map((c, i) => {
    const last = i === items.length - 1;
    const part = last ? `<span class="here">${esc(c.label)}</span>` : `<a href="${c.href}">${esc(c.label)}</a>`;
    return part + (last ? "" : '<span class="sep">/</span>');
  }).join("");
  document.title = `${items[items.length - 1].label} · Profile Crawler`;
}

function errorBox(message, retry) {
  return `<div class="error-box"><span class="pill bad">Errore</span><span class="msg">${esc(message)}</span>${retry ? '<button class="link-btn" data-retry>Riprova</button>' : ""}</div>`;
}

function datasetFigures(s) {
  const total = (s.images || 0) + (s.rejected || 0);
  const pct = (n) => (total ? (100 * n) / total : 0);
  const cap = s.captioned || 0;
  const nocap = Math.max(0, (s.images || 0) - cap);
  return `
    <div class="funnel" role="img" aria-label="${fmtInt(s.images)} nel dataset, di cui ${fmtInt(cap)} con caption; ${fmtInt(s.rejected)} scartate">
      <i class="f-cap" style="width:${pct(cap)}%"></i><i class="f-nocap" style="width:${pct(nocap)}%"></i><i class="f-rej" style="width:${pct(s.rejected)}%"></i>
    </div>`;
}

function datasetCell(s) {
  if (!s || ((s.images || 0) + (s.rejected || 0)) === 0) return '<span class="dash">—</span>';
  return `<div class="dataset-cell">
      <div class="figures"><span>${fmtInt(s.images)}</span><span class="muted">immagini · ${fmtInt(s.captioned)} con caption</span></div>
      ${datasetFigures(s)}
    </div>`;
}

const FUNNEL_LEGEND = `<div class="funnel-legend"><span><i class="f-cap"></i>Con caption</span><span><i class="f-nocap"></i>Senza caption</span><span><i class="f-rej"></i>Scartate</span></div>`;

function usernamesPreview(list, max = 3) {
  if (!list || !list.length) return "nessun profilo";
  const shown = list.slice(0, max).map((u) => "@" + u).join(", ");
  return list.length > max ? `${shown} +${list.length - max}` : shown;
}

function markDirty(flag) {
  state.dirty = flag;
}

/* ------------------------------------------------------------------ */
/* Shell: nav, worker status                                           */
/* ------------------------------------------------------------------ */

const NAV = [
  { href: "#/home", label: "Home", icon: ICON.home, match: /^\/home/ },
  { href: "#/jobs", label: "Job", icon: ICON.jobs, match: /^\/jobs/ },
  { href: "#/runs", label: "Esecuzioni", icon: ICON.runs, match: /^\/runs/, count: true },
  { href: "#/datasets", label: "Dataset", icon: ICON.data, match: /^\/datasets/ },
  { section: "Configurazione" },
  { href: "#/settings", label: "Impostazioni globali", icon: ICON.settings, match: /^\/settings/ },
  { href: "#/accounts", label: "Account Instagram", icon: ICON.account, match: /^\/accounts/ },
];

function renderNav(path) {
  const active = (state.meta && (state.meta.current_run ? 1 : 0) + state.meta.queued) || 0;
  $("#nav").innerHTML = NAV.map((n) => {
    if (n.section) return `<div class="nav-label">${esc(n.section)}</div>`;
    const current = n.match.test(path) ? ' aria-current="page"' : "";
    const count = n.count && active ? `<span class="count" title="Esecuzioni in corso o in coda">${active}</span>` : "";
    return `<a href="${n.href}"${current}>${n.icon}<span>${esc(n.label)}</span>${count}</a>`;
  }).join("");
}

async function refreshMeta() {
  try {
    state.meta = await api("/meta");
  } catch (_) { return; }
  const w = $("#worker");
  const run = state.meta.current_run;
  if (run) {
    w.classList.add("busy");
    w.href = `#/runs/${run.id}`;
    w.querySelector(".label-text").textContent = `In corso: ${run.job_name}`;
  } else {
    w.classList.remove("busy");
    w.href = "#/runs";
    w.querySelector(".label-text").textContent = state.meta.queued ? `${state.meta.queued} in coda` : "Nessuna esecuzione";
  }
  const parts = state.meta.data_dir.split(/[\\/]/).filter(Boolean);
  const short = parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : state.meta.data_dir;
  $("#sidebar-foot").innerHTML = `Dati in <span class="mono" title="${esc(state.meta.data_dir)}">${esc(short)}</span> · v${esc(state.meta.version)}`;
  renderNav(currentPath().path);
}

/* ------------------------------------------------------------------ */
/* Router                                                              */
/* ------------------------------------------------------------------ */

function currentPath() {
  const raw = location.hash.replace(/^#/, "") || "/home";
  const [path, query = ""] = raw.split("?");
  return { path, query: new URLSearchParams(query) };
}

const ROUTES = [
  [/^\/home$/, () => viewHome()],
  [/^\/jobs$/, () => viewJobs()],
  [/^\/jobs\/new$/, () => viewJob(null)],
  [/^\/jobs\/([a-z0-9]+)$/, (m) => viewJob(m[1])],
  [/^\/runs$/, () => viewRuns()],
  [/^\/runs\/([a-z0-9]+)$/, (m) => viewRun(m[1])],
  [/^\/datasets$/, () => viewDatasets()],
  [/^\/datasets\/([a-z0-9]+)\/([A-Za-z0-9._]+)$/, (m, q) => viewGallery(m[1], m[2], q)],
  [/^\/settings$/, () => viewSettings()],
  [/^\/accounts$/, () => viewAccounts()],
];

async function route() {
  if (state.dirty && location.hash !== state.lastHash) {
    if (!window.confirm("Ci sono modifiche non salvate. Uscire comunque?")) {
      history.replaceState(null, "", state.lastHash || "#/home");
      return;
    }
  }
  markDirty(false);
  state.lastHash = location.hash;
  if (state.cleanup) { state.cleanup(); state.cleanup = null; }
  $("#shell").classList.remove("menu-open");
  $("#menu-btn").setAttribute("aria-expanded", "false");

  const { path, query } = currentPath();
  renderNav(path);
  const view = $("#view");
  for (const [re, fn] of ROUTES) {
    const m = path.match(re);
    if (m) {
      view.innerHTML = "";
      $("#sheet").scrollTop = 0;
      try {
        const cleanup = await fn(m, query);
        if (typeof cleanup === "function") state.cleanup = cleanup;
      } catch (e) {
        view.innerHTML = errorBox(e.message, true);
        const retry = $("[data-retry]", view);
        if (retry) retry.onclick = route;
      }
      return;
    }
  }
  location.hash = "#/home";
}

/* ------------------------------------------------------------------ */
/* Settings editor (global and job)                                    */
/* ------------------------------------------------------------------ */

/**
 * mode "job":    inherited = global effective, overrides = job overrides
 * mode "global": inherited = .env / default,   overrides = global overrides
 */
function settingsEditor({ fields, groups, inherited, overrides, mode, accounts, jobId, onChange }) {
  const ov = { ...overrides };
  const root = document.createElement("div");
  let activeGroup = groups[0].id;
  const ownLabel = mode === "job" ? "personalizzato nel job" : "impostato qui";
  const resetHint = (f) => {
    const inh = inherited[f.key];
    return `Ripristina (${SOURCE_LABEL[inh.source]}: ${esc(shortValue(f, inh.value))})`;
  };

  function shortValue(f, v) {
    if (f.type === "bool") return v ? "sì" : "no";
    if (f.type === "secret") return secretLabel(v);
    if (f.type === "account") return accountLabel(v);
    if (f.type === "choice") return (CHOICE_LABEL[f.key] || {})[v] || v;
    if (f.type === "text") return v ? `${String(v).trim().split("\n")[0].slice(0, 28)}${String(v).length > 28 ? "…" : ""}` : "vuoto";
    if (v === "" || v === null || v === undefined) return "vuoto";
    return String(v);
  }

  function accountLabel(id) {
    if (!id) return accounts.some((a) => a.id === "env") ? "sessione .env" : "nessuno";
    const a = accounts.find((x) => x.id === id);
    return a ? a.label : "account rimosso";
  }

  function control(f, value, locked) {
    const id = `f-${f.key}`;
    const dis = locked ? " disabled" : "";
    switch (f.type) {
      case "bool":
        return `<label class="switch"><input type="checkbox" id="${id}" data-key="${f.key}"${value ? " checked" : ""}${dis}><span class="track"></span><span class="switch-text">${value ? "Attivo" : "Disattivo"}</span></label>`;
      case "int":
      case "float": {
        const step = f.type === "int" ? 1 : (f.max === 1 ? 0.05 : 0.1);
        return `<input class="input narrow num" type="number" id="${id}" data-key="${f.key}" value="${esc(value)}" step="${step}"${f.min !== null ? ` min="${f.min}"` : ""}${f.max !== null ? ` max="${f.max}"` : ""}${dis}>`;
      }
      case "text":
        return `<textarea class="textarea" id="${id}" data-key="${f.key}" rows="6"${dis}>${esc(value)}</textarea>`;
      case "secret": {
        // Never pre-filled: an empty field keeps the stored key, typing replaces it
        const placeholder = isMasked(value)
          ? (locked ? `Impostata (${value.slice(SECRET.length)})` : `Impostata (${value.slice(SECRET.length)}) · scrivi per sostituirla`)
          : value ? "Nuova chiave inserita, da salvare"
          : (locked ? "Nessuna" : "Incolla la chiave");
        return `<input class="input mono" type="password" id="${id}" data-key="${f.key}" data-prev="${esc(value)}" value=""
          placeholder="${esc(placeholder)}" autocomplete="new-password" spellcheck="false"${dis}>`;
      }
      case "choice": {
        const labels = CHOICE_LABEL[f.key] || {};
        if (f.choices.length <= 3) {
          return `<div class="segmented${locked ? " locked" : ""}" role="radiogroup" aria-labelledby="${id}-l">${f.choices.map((c) =>
            `<label><input type="radio" name="${id}" data-key="${f.key}" value="${esc(c)}"${c === value ? " checked" : ""}${dis}><span>${esc(labels[c] || c)}</span></label>`).join("")}</div>`;
        }
        return `<select class="select" id="${id}" data-key="${f.key}"${dis}>${f.choices.map((c) => `<option value="${esc(c)}"${c === value ? " selected" : ""}>${esc(labels[c] || c)}</option>`).join("")}</select>`;
      }
      case "account": {
        const hasEnv = accounts.some((a) => a.id === "env");
        const opts = [`<option value="">${hasEnv ? "Sessione da .env" : "Nessuna sessione (.env vuoto)"}</option>`]
          .concat(accounts.filter((a) => a.id !== "env").map((a) => {
            const st = a.valid === false ? " (scaduta)" : "";
            return `<option value="${esc(a.id)}"${a.id === value ? " selected" : ""}>${esc(a.label)}${st}</option>`;
          }));
        return `<select class="select" id="${id}" data-key="${f.key}"${dis}>${opts.join("")}</select>`;
      }
      default:
        return `<input class="input" type="text" id="${id}" data-key="${f.key}" value="${esc(value)}"${dis} spellcheck="false">`;
    }
  }

  function row(f) {
    const own = Object.prototype.hasOwnProperty.call(ov, f.key);
    const value = own ? ov[f.key] : inherited[f.key].value;
    const labelTag = f.type === "choice" && f.choices.length <= 3
      ? `<span class="label-text" id="f-${f.key}-l">${esc(f.label)}</span>`
      : `<label for="f-${f.key}">${esc(f.label)}</label>`;
    const meta = own
      ? `<span class="src ${mode}">${ownLabel}</span><button type="button" class="link-btn" data-reset="${f.key}">${resetHint(f)}</button>`
      : `<span class="src">${SOURCE_LABEL[inherited[f.key].source]}</span><button type="button" class="link-btn" data-own="${f.key}">${mode === "job" ? "Personalizza" : "Modifica"}</button>`;
    const extra = f.key === "engine"
      ? `<button type="button" class="link-btn" data-engine-check>Verifica connessione</button><span class="check-result" data-engine-result></span>`
      : "";
    return `<div class="field-row${own ? " overridden" : ""}" data-row="${f.key}">
        <div class="field-label">${labelTag}${f.help ? `<p class="help">${esc(f.help)}</p>` : ""}</div>
        <div class="field-control">${control(f, value, !own)}<div class="field-meta">${meta}${extra}</div></div>
      </div>`;
  }

  const currentEngine = () => (Object.prototype.hasOwnProperty.call(ov, "engine") ? ov.engine : inherited.engine.value);
  // Host, model and API key are shown only for the engine in use; the others keep their values
  const visible = (f) => !f.engine || f.engine === currentEngine();

  function counts() {
    const c = {};
    for (const f of fields) {
      if (visible(f) && Object.prototype.hasOwnProperty.call(ov, f.key)) c[f.group] = (c[f.group] || 0) + 1;
    }
    return c;
  }

  function render() {
    const c = counts();
    root.innerHTML = `
      <div class="tabs" role="tablist">${groups.map((g) =>
        `<button type="button" role="tab" data-group="${g.id}" aria-selected="${g.id === activeGroup}">${esc(g.label)}${c[g.id] ? `<span class="tab-count" title="${c[g.id]} ${mode === "job" ? "personalizzate" : "impostate qui"}">${c[g.id]}</span>` : ""}</button>`).join("")}
      </div>
      <div role="tabpanel">${fields.filter((f) => f.group === activeGroup && visible(f)).map(row).join("")}</div>`;
  }

  function readValue(f, el) {
    if (f.type === "bool") return el.checked;
    if (f.type === "int") return el.value === "" ? null : parseInt(el.value, 10);
    if (f.type === "float") return el.value === "" ? null : parseFloat(el.value);
    if (f.type === "secret") return el.value === "" ? el.dataset.prev : el.value.trim();
    return el.value;
  }

  root.addEventListener("click", async (e) => {
    const tab = e.target.closest("[data-group]");
    if (tab) { activeGroup = tab.dataset.group; render(); return; }
    const own = e.target.closest("[data-own]");
    if (own) {
      const key = own.dataset.own;
      ov[key] = inherited[key].value;
      render(); onChange();
      const el = $(`[data-key="${key}"]`, root);
      if (el) el.focus();
      return;
    }
    const reset = e.target.closest("[data-reset]");
    if (reset) { delete ov[reset.dataset.reset]; render(); onChange(); return; }
    const check = e.target.closest("[data-engine-check]");
    if (check) {
      const out = $("[data-engine-result]", root);
      out.className = "check-result"; out.textContent = "Verifica in corso…";
      check.disabled = true;
      try {
        const r = await api("/engine/check", { method: "POST", body: { job_id: jobId || undefined, overrides: ov } });
        out.className = `check-result ${r.ok ? "ok" : "bad"}`;
        out.textContent = r.ok ? `Raggiungibile: ${r.engine} su ${r.host}` : `Non raggiungibile su ${r.host}`;
      } catch (err) {
        out.className = "check-result bad"; out.textContent = err.message;
      } finally { check.disabled = false; }
    }
  });

  root.addEventListener("input", (e) => {
    const key = e.target.dataset.key;
    if (!key) return;
    const f = fields.find((x) => x.key === key);
    ov[key] = readValue(f, e.target);
    if (key === "engine") {
      // Swap in the chosen engine's host, model and key, keeping focus on the engine control
      render(); onChange();
      const checked = $(`[data-key="engine"]:checked`, root);
      if (checked) checked.focus();
      return;
    }
    if (f.type === "bool") {
      const text = e.target.parentElement.querySelector(".switch-text");
      if (text) text.textContent = e.target.checked ? "Attivo" : "Disattivo";
    }
    onChange();
  });

  render();
  return { el: root, getOverrides: () => ({ ...ov }) };
}

/* ------------------------------------------------------------------ */
/* View: jobs                                                          */
/* ------------------------------------------------------------------ */

async function viewJobs() {
  setCrumbs([{ label: "Job" }]);
  const view = $("#view");
  const jobs = await api("/jobs");
  const running = jobs.find((j) => j.last_run && isActive(j.last_run.status));
  const lastStart = jobs.map((j) => j.last_run && j.last_run.created_at).filter(Boolean).sort().pop();
  const subline = running
    ? `In corso: ${esc(running.name)}`
    : jobs.length ? `${plural(jobs.length, "job", "job")}${lastStart ? ` · ultimo avvio ${fmtDate(lastStart)}` : " · nessuno avviato"}` : "";

  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>Job</h1>${subline ? `<p class="subline">${subline}</p>` : ""}</div>
      <div class="title-actions"><a class="btn btn-primary" href="#/jobs/new" data-tour="new-job">Nuovo job</a></div>
    </div>
    ${jobs.length ? `
    <div class="panel">
      <table class="table">
        <thead><tr><th>Nome</th><th>Ultima esecuzione</th><th class="num">Personalizzate</th><th class="num">Dataset</th><th></th></tr></thead>
        <tbody>${jobs.map((j) => `
          <tr class="clickable" data-href="#/jobs/${j.id}">
            <td class="primary"><a class="name" href="#/jobs/${j.id}">${esc(j.name)}</a><span class="sub">${esc(usernamesPreview(j.usernames))}</span></td>
            <td class="secondary" data-label="Ultima:">${j.last_run ? `${statusPill(j.last_run.status)} <span class="muted">${fmtDate(j.last_run.created_at)}</span>` : '<span class="dash">—</span>'}</td>
            <td class="num hide-phone">${j.override_count ? fmtInt(j.override_count) : '<span class="dash">—</span>'}</td>
            <td class="num end">${datasetCell(j.dataset)}</td>
            <td class="actions"><button class="btn" data-run="${j.id}"${j.last_run && isActive(j.last_run.status) ? " disabled" : ""}>${ICON.play}Avvia</button></td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>
    <div style="margin-top:12px">${FUNNEL_LEGEND}</div>` : `
    <div class="empty">
      <p>Un job raccoglie i profili da scaricare e le impostazioni che vuoi diverse da quelle globali. Lo rilanci quando vuoi, senza reimpostare nulla.</p>
      <a class="btn btn-primary" href="#/jobs/new">Crea il primo job</a>
    </div>`}`;

  view.addEventListener("click", async (e) => {
    const runBtn = e.target.closest("[data-run]");
    if (runBtn) {
      e.stopPropagation();
      runBtn.disabled = true;
      try {
        const run = await api(`/jobs/${runBtn.dataset.run}/run`, { method: "POST" });
        location.hash = `#/runs/${run.id}`;
      } catch (err) { toast(err.message, true); runBtn.disabled = false; }
      return;
    }
    const tr = e.target.closest("tr[data-href]");
    if (tr && !e.target.closest("a")) location.hash = tr.dataset.href;
  });
}

/* ------------------------------------------------------------------ */
/* View: job editor                                                    */
/* ------------------------------------------------------------------ */

async function viewJob(jobId) {
  const isNew = !jobId;
  const [sc, globals, accounts, job, runs, datasets] = await Promise.all([
    schema(),
    api("/settings"),
    api("/accounts"),
    isNew ? Promise.resolve({ name: "", usernames: [], notes: "", overrides: {} }) : api(`/jobs/${jobId}`),
    isNew ? Promise.resolve([]) : api(`/runs?job_id=${jobId}&limit=6`),
    isNew ? Promise.resolve([]) : api(`/jobs/${jobId}/datasets`),
  ]);
  setCrumbs([{ label: "Job", href: "#/jobs" }, { label: isNew ? "Nuovo job" : job.name }]);

  const overrideCount = Object.keys(job.overrides || {}).length;
  const last = runs[0];
  const subline = isNew
    ? "Scegli i profili; tutto il resto eredita le impostazioni globali finché non lo personalizzi."
    : [plural(job.usernames.length, "profilo", "profili"),
       overrideCount ? plural(overrideCount, "impostazione personalizzata", "impostazioni personalizzate") : "nessuna personalizzazione",
       last ? `ultima esecuzione ${fmtDate(last.created_at)}` : "mai eseguito"].join(" · ");

  const view = $("#view");
  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>${esc(isNew ? "Nuovo job" : job.name)}</h1><p class="subline">${subline}</p></div>
      <div class="title-actions">
        ${isNew ? "" : '<button class="btn" data-act="duplicate">Duplica</button>'}
        <button class="btn btn-primary" data-act="run"${last && isActive(last.status) ? " disabled" : ""}>${ICON.play}<span>${isNew ? "Salva e avvia" : "Avvia"}</span></button>
      </div>
    </div>
    <div class="split">
      <div class="stack">
        <section class="panel" aria-labelledby="p-profiles">
          <div class="panel-head"><h2 id="p-profiles">Profili</h2><div class="right" data-profile-count></div></div>
          <div class="panel-body form-grid">
            <div><label class="label" for="job-name">Nome del job</label><input class="input" id="job-name" value="${esc(job.name)}" placeholder="Es. Paesaggi alpini" autocomplete="off"></div>
            <div>
              <label class="label" for="job-users">Profili Instagram</label>
              <textarea class="textarea mono" id="job-users" rows="5" spellcheck="false" placeholder="Uno per riga: nome utente, @nome o link al profilo">${esc(job.usernames.join("\n"))}</textarea>
              <div class="profiles-meta" data-chips></div>
            </div>
            <div><label class="label" for="job-notes">Note</label><textarea class="textarea" id="job-notes" rows="2" placeholder="Per chi lo rilancia: scopo, account da usare, cosa controllare">${esc(job.notes || "")}</textarea></div>
          </div>
        </section>
        <section class="panel" aria-labelledby="p-settings">
          <div class="panel-head"><h2 id="p-settings">Impostazioni del job</h2><div class="right">Ciò che non personalizzi segue le <a href="#/settings">impostazioni globali</a></div></div>
          <div class="panel-body" data-editor></div>
        </section>
        <div class="savebar clean" data-savebar>
          <span class="note" data-save-note>${isNew ? "Job non ancora salvato" : "Tutto salvato"}</span>
          ${isNew ? "" : '<button class="btn" data-act="discard" hidden>Annulla modifiche</button>'}
          <button class="btn btn-primary" data-act="save"${isNew ? "" : " disabled"}>Salva</button>
        </div>
        ${isNew ? "" : `
        <div class="danger-zone">
          <p>Eliminare il job toglie la sua configurazione e lo storico delle esecuzioni dall'elenco. Le immagini scaricate restano su disco.</p>
          <button class="link-btn danger" data-act="delete">Elimina job</button>
        </div>`}
      </div>
      <aside class="rail">
        <section class="panel" aria-labelledby="r-runs">
          <div class="panel-head"><h2 id="r-runs">Esecuzioni recenti</h2>${runs.length ? `<div class="right"><a href="#/runs">Tutte</a></div>` : ""}</div>
          ${runs.length ? `<ul class="run-list">${runs.map((r) => {
            const res = r.result || [];
            const sum = (k) => res.reduce((a, p) => a + (p[k] || 0), 0);
            return `<li><a href="#/runs/${r.id}"><span class="when">${fmtDate(r.created_at)}</span>${statusPill(r.status)}
              <span class="what">${res.length ? `${fmtInt(sum("downloaded"))} nuove · ${fmtInt(sum("rejected") + sum("duplicates"))} scartate · ${fmtInt(sum("captioned"))} caption` : esc(r.error || (isActive(r.status) ? "In lavorazione" : "Nessun risultato"))}</span></a></li>`;
          }).join("")}</ul>` : '<div class="panel-body muted">Nessuna esecuzione. Il primo avvio scarica tutto; i successivi solo le novità.</div>'}
        </section>
        <section class="panel" aria-labelledby="r-data">
          <div class="panel-head"><h2 id="r-data">Dataset</h2></div>
          ${datasets.length ? `<ul class="profile-list">${datasets.map((d) => `
            <li><div class="top"><a href="#/datasets/${jobId}/${esc(d.username)}">@${esc(d.username)}</a><span class="num">${fmtInt(d.images)} img</span></div>
            ${(d.images + d.rejected) ? datasetFigures(d) : '<span class="muted" style="font-size:13px">Non ancora scaricato</span>'}</li>`).join("")}</ul>
            <div class="panel-body" style="border-top:1px solid var(--rule)">${FUNNEL_LEGEND}</div>`
          : '<div class="panel-body muted">Le immagini appaiono qui dopo il primo avvio.</div>'}
        </section>
      </aside>
    </div>`;

  const editor = settingsEditor({
    fields: sc.fields, groups: sc.groups, inherited: globals.effective, overrides: job.overrides || {},
    mode: "job", accounts, jobId, onChange: changed,
  });
  $("[data-editor]", view).appendChild(editor.el);

  const nameEl = $("#job-name", view), usersEl = $("#job-users", view), notesEl = $("#job-notes", view);
  const original = JSON.stringify({ n: job.name, u: job.usernames.join("\n"), no: job.notes || "", o: job.overrides || {} });

  function parseLocal(text) {
    const out = [];
    for (let item of text.split(/[\s,;]+/)) {
      const m = item.match(/instagram\.com\/([^/?#]+)/);
      if (m) item = m[1];
      item = item.replace(/^@/, "").replace(/\/$/, "");
      if (/^[A-Za-z0-9._]{1,30}$/.test(item) && !out.includes(item)) out.push(item);
    }
    return out;
  }

  function renderChips() {
    const list = parseLocal(usersEl.value);
    $("[data-chips]", view).innerHTML = list.slice(0, 24).map((u) => `<span class="chip">@${esc(u)}</span>`).join("") +
      (list.length > 24 ? `<span class="chip">+${list.length - 24}</span>` : "");
    $("[data-profile-count]", view).textContent = plural(list.length, "profilo", "profili");
  }

  function current() {
    return { name: nameEl.value, usernames: usersEl.value, notes: notesEl.value, overrides: editor.getOverrides() };
  }

  function changed() {
    const cur = current();
    const now = JSON.stringify({ n: cur.name, u: cur.usernames, no: cur.notes, o: cur.overrides });
    const dirty = isNew || now !== original;
    markDirty(isNew ? (cur.name || cur.usernames) !== "" : dirty);
    const bar = $("[data-savebar]", view);
    bar.classList.toggle("clean", !dirty);
    $("[data-save-note]", view).textContent = isNew ? "Job non ancora salvato" : dirty ? "Modifiche non salvate" : "Tutto salvato";
    $('[data-act="save"]', view).disabled = !dirty;
    const discard = $('[data-act="discard"]', view);
    if (discard) discard.hidden = !dirty;
    const runLabel = $('[data-act="run"] span', view);
    runLabel.textContent = dirty ? "Salva e avvia" : "Avvia";
  }

  async function save() {
    const body = current();
    if (!body.name.trim()) body.name = parseLocal(body.usernames)[0] ? `@${parseLocal(body.usernames)[0]}` : "Job senza nome";
    const saved = isNew ? await api("/jobs", { method: "POST", body }) : await api(`/jobs/${jobId}`, { method: "PUT", body });
    markDirty(false);
    return saved;
  }

  view.addEventListener("input", (e) => {
    if (e.target === usersEl) renderChips();
    if ([nameEl, usersEl, notesEl].includes(e.target)) changed();
  });

  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    try {
      if (act === "save") {
        btn.disabled = true;
        const saved = await save();
        toast("Job salvato");
        if (isNew) location.hash = `#/jobs/${saved.id}`; else route();
      } else if (act === "discard") {
        markDirty(false); route();
      } else if (act === "run") {
        btn.disabled = true;
        const dirtyNow = $('[data-act="run"] span', view).textContent !== "Avvia";
        const saved = dirtyNow || isNew ? await save() : job;
        const run = await api(`/jobs/${saved.id}/run`, { method: "POST" });
        location.hash = `#/runs/${run.id}`;
      } else if (act === "duplicate") {
        const copy = await api(`/jobs/${jobId}/duplicate`, { method: "POST" });
        toast("Job duplicato");
        location.hash = `#/jobs/${copy.id}`;
      } else if (act === "delete") {
        const ok = await confirmDialog({
          title: `Eliminare “${job.name}”?`,
          body: "La configurazione del job viene rimossa. Le immagini già scaricate restano nella cartella del dataset.",
          confirm: "Elimina job", danger: true,
        });
        if (!ok) return;
        await api(`/jobs/${jobId}`, { method: "DELETE" });
        markDirty(false);
        toast("Job eliminato");
        location.hash = "#/jobs";
      }
    } catch (err) {
      toast(err.message, true);
      btn.disabled = false;
    }
  });

  renderChips();
  changed();
  if (isNew) nameEl.focus();
}

/* ------------------------------------------------------------------ */
/* View: runs                                                          */
/* ------------------------------------------------------------------ */

function runTotals(run) {
  const res = run.result || [];
  const sum = (k) => res.reduce((a, p) => a + (p[k] || 0), 0);
  return { downloaded: sum("downloaded"), rejected: sum("rejected") + sum("duplicates"), kept: sum("kept"), profiles: res.length };
}

async function viewRuns() {
  setCrumbs([{ label: "Esecuzioni" }]);
  const runs = await api("/runs?limit=100");
  const view = $("#view");
  const active = runs.filter((r) => isActive(r.status));
  view.innerHTML = `
    <div class="title-row"><div class="titles"><h1>Esecuzioni</h1>
      <p class="subline">${active.length ? `${plural(active.length, "esecuzione attiva", "esecuzioni attive")} · le altre aspettano in coda, una alla volta` : runs.length ? `Ultime ${fmtInt(runs.length)}` : ""}</p></div></div>
    ${runs.length ? `<div class="panel"><table class="table">
      <thead><tr><th>Job</th><th>Stato</th><th>Avviata</th><th class="num">Durata</th><th class="num">Nuove</th><th class="num">Scartate</th><th class="num">Nel dataset</th></tr></thead>
      <tbody>${runs.map((r) => { const t = runTotals(r); return `
        <tr class="clickable" data-href="#/runs/${r.id}">
          <td class="primary"><a class="name" href="#/runs/${r.id}">${esc(r.job_name)}</a><span class="sub">${esc(usernamesPreview(r.usernames))}</span></td>
          <td class="end">${statusPill(r.status)}</td>
          <td class="secondary" data-label="Avviata:">${fmtDate(r.started_at || r.created_at)}</td>
          <td class="num hide-phone">${r.started_at ? fmtDuration(r.started_at, r.finished_at) : '<span class="dash">—</span>'}</td>
          <td class="num hide-phone">${t.profiles ? fmtInt(t.downloaded) : '<span class="dash">—</span>'}</td>
          <td class="num hide-phone">${t.profiles ? fmtInt(t.rejected) : '<span class="dash">—</span>'}</td>
          <td class="num hide-phone">${t.profiles ? fmtInt(t.kept) : '<span class="dash">—</span>'}</td>
        </tr>`; }).join("")}</tbody></table></div>` : `
    <div class="empty"><p>Nessuna esecuzione. Avvia un job e qui ne segui il log, l'avanzamento e il risultato per profilo.</p><a class="btn" href="#/jobs">Vai ai job</a></div>`}`;
  view.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-href]");
    if (tr && !e.target.closest("a")) location.hash = tr.dataset.href;
  });
}

/* ------------------------------------------------------------------ */
/* View: one run (live)                                                */
/* ------------------------------------------------------------------ */

function colorLog(text) {
  return esc(text).split("\n").map((line) => {
    if (/^(✗|⚠|Traceback|\s+File )/.test(line.trim()) || /Error:/.test(line)) return `<span class="err">${line}</span>`;
    if (/^(✓)/.test(line.trim())) return `<span class="ok">${line}</span>`;
    if (/^(━━|▶)/.test(line.trim())) return `<span class="head">${line}</span>`;
    return line;
  }).join("\n");
}

async function viewRun(runId) {
  const [sc, first] = await Promise.all([schema(), api(`/runs/${runId}`)]);
  let run = first;
  let offset = 0;
  let follow = true;
  const view = $("#view");
  setCrumbs([{ label: "Esecuzioni", href: "#/runs" }, { label: run.job_name }]);

  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>${esc(run.job_name)} <span data-status></span></h1><p class="subline" data-subline></p></div>
      <div class="title-actions" data-actions></div>
    </div>
    <div class="stack">
      <div data-progress></div>
      <div data-error></div>
      <div data-results></div>
      <section class="panel" aria-labelledby="log-h">
        <div class="panel-head"><h2 id="log-h">Log</h2><div class="right"><label class="switch"><input type="checkbox" data-follow checked><span class="track"></span><span class="switch-text">Segui</span></label></div></div>
        <pre class="log" data-log></pre>
      </section>
      <section class="panel"><details class="config" data-config><summary>Configurazione usata</summary><div data-config-body></div></details></section>
    </div>`;

  const logEl = $("[data-log]", view);
  logEl.addEventListener("scroll", () => {
    const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 24;
    if (!atBottom && follow) { follow = false; $("[data-follow]", view).checked = false; }
  });
  $("[data-follow]", view).addEventListener("change", (e) => { follow = e.target.checked; if (follow) logEl.scrollTop = logEl.scrollHeight; });

  function renderHeader() {
    $("[data-status]", view).innerHTML = statusPill(run.status);
    const when = run.started_at ? `Avviata ${fmtDate(run.started_at)} · durata ${fmtDuration(run.started_at, run.finished_at)}` : `In coda da ${fmtDate(run.created_at)}`;
    $("[data-subline]", view).textContent = `${when} · ${plural(run.usernames.length, "profilo", "profili")}`;
    $("[data-actions]", view).innerHTML = isActive(run.status)
      ? '<button class="btn" data-act="cancel">Interrompi</button>'
      : `<a class="btn" href="#/jobs/${run.job_id}">Apri job</a><button class="btn btn-primary" data-act="rerun">${ICON.play}Rilancia</button>`;
  }

  function renderProgress() {
    const box = $("[data-progress]", view);
    if (run.status !== "running") { box.innerHTML = ""; return; }
    const p = run.progress || {};
    const known = p.total > 0;
    const pct = known ? Math.min(100, (100 * (p.done || 0)) / p.total) : 0;
    const who = p.username ? `@${esc(p.username)}` : "";
    const profileOf = p.count ? ` <span class="muted">· profilo ${p.index} di ${p.count}</span>` : "";
    box.innerHTML = `<section class="panel"><div class="panel-body progress">
        <div class="line"><span class="stage">${who} ${esc(STAGE_LABEL[p.stage] || "Avvio")}</span>${profileOf}<span class="count">${known ? `${fmtInt(p.done)} di ${fmtInt(p.total)}` : ""}</span></div>
        <div class="bar${known ? "" : " indeterminate"}"><i style="width:${pct}%"></i></div>
      </div></section>`;
  }

  function renderResults() {
    $("[data-error]", view).innerHTML = run.error ? errorBox(run.error) : "";
    const res = run.result || [];
    const box = $("[data-results]", view);
    if (!res.length) { box.innerHTML = ""; return; }
    const cell = (v, ok) => `<td class="num hide-phone">${ok ? fmtInt(v) : '<span class="dash">—</span>'}</td>`;
    box.innerHTML = `<section class="panel"><div class="panel-head"><h2>Risultato per profilo</h2></div>
      <table class="table"><thead><tr><th>Profilo</th><th class="num">Trovate</th><th class="num">Nuove</th><th class="num">Già presenti</th><th class="num">Duplicati</th><th class="num">Scartate</th><th class="num">Caption</th><th class="num">Nel dataset</th></tr></thead>
      <tbody>${res.map((p) => { const ok = p.status !== "failed"; return `<tr>
        <td class="primary"><a class="name" href="#/datasets/${run.job_id}/${esc(p.username)}">@${esc(p.username)}</a>
          ${p.status !== "ok" ? `<span class="sub">${statusPill(p.status === "failed" ? "failed" : "partial")} ${esc((p.errors || []).join("; "))}</span>` : ""}</td>
        ${cell(p.found, ok)}${cell(p.downloaded, ok)}${cell(p.existing, ok)}${cell(p.duplicates, ok)}${cell(p.rejected, ok)}${cell(p.captioned, ok)}
        <td class="num end"><strong>${ok ? fmtInt(p.kept) : '<span class="dash">—</span>'}</strong></td>
        ${ok ? `<td class="secondary phone-only">${fmtInt(p.found)} trovate · ${fmtInt(p.downloaded)} nuove · ${fmtInt(p.duplicates + p.rejected)} scartate · ${fmtInt(p.captioned)} caption</td>` : ""}</tr>`; }).join("")}</tbody></table></section>`;
  }

  function renderConfig() {
    const sources = run.sources || {};
    const fields = sc.fields.filter((f) => !f.engine || f.engine === run.settings.engine);
    const shown = fields.filter((f) => sources[f.key] && sources[f.key] !== "default");
    const fmt = (f, v) => f.type === "bool" ? (v ? "sì" : "no")
      : f.type === "secret" ? esc(secretLabel(v))
      : (v === "" ? '<span class="dash">—</span>' : esc((CHOICE_LABEL[f.key] || {})[v] || v));
    $("[data-config-body]", view).innerHTML = `<table class="kv">${(shown.length ? shown : fields.slice(0, 8)).map((f) =>
      `<tr><td>${esc(f.label)}</td><td>${fmt(f, run.settings[f.key])} ${sources[f.key] ? `<span class="src ${sources[f.key]}">${SOURCE_LABEL[sources[f.key]]}</span>` : ""}</td></tr>`).join("")}
      <tr><td colspan="2" class="muted">${shown.length ? "Gli altri valori erano quelli predefiniti." : ""}</td></tr></table>`;
  }

  async function poll() {
    try {
      run = await api(`/runs/${runId}?offset=${offset}`);
    } catch (e) { return; }
    if (run.log.text) {
      logEl.insertAdjacentHTML("beforeend", colorLog(run.log.text));
      offset = run.log.offset;
      if (follow) logEl.scrollTop = logEl.scrollHeight;
    }
    renderHeader(); renderProgress(); renderResults();
  }

  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    btn.disabled = true;
    try {
      if (btn.dataset.act === "cancel") {
        await api(`/runs/${runId}/cancel`, { method: "POST" });
        toast("Interruzione richiesta: si ferma al prossimo passo");
      } else if (btn.dataset.act === "rerun") {
        const next = await api(`/jobs/${run.job_id}/run`, { method: "POST" });
        location.hash = `#/runs/${next.id}`;
      }
    } catch (err) { toast(err.message, true); btn.disabled = false; }
  });

  run.log = { text: "", offset: 0 };
  renderConfig();
  await poll();
  if (!logEl.textContent) logEl.innerHTML = '<span class="muted">Il log comparirà qui appena l\'esecuzione parte.</span>';
  let wasActive = isActive(run.status);
  const timer = setInterval(async () => {
    if (!isActive(run.status) && !wasActive) return;
    if (logEl.querySelector(".muted") && offset === 0) logEl.innerHTML = "";
    await poll();
    if (wasActive && !isActive(run.status)) { wasActive = false; refreshMeta(); }
  }, 1200);
  return () => clearInterval(timer);
}

/* ------------------------------------------------------------------ */
/* View: datasets                                                      */
/* ------------------------------------------------------------------ */

async function viewDatasets() {
  setCrumbs([{ label: "Dataset" }]);
  const jobs = await api("/jobs");
  const lists = await Promise.all(jobs.map((j) => api(`/jobs/${j.id}/datasets`).catch(() => [])));
  const total = { images: 0, captioned: 0, profiles: 0 };
  lists.flat().forEach((d) => { total.images += d.images; total.captioned += d.captioned; if (d.images) total.profiles++; });
  const view = $("#view");
  view.innerHTML = `
    <div class="title-row"><div class="titles"><h1>Dataset</h1>
      <p class="subline">${total.images ? `${fmtInt(total.images)} immagini in ${plural(total.profiles, "profilo", "profili")} · ${fmtInt(total.captioned)} con caption` : "Ancora nessuna immagine scaricata"}</p></div></div>
    ${jobs.length ? `<div class="stack">${jobs.map((j, i) => `
      <section class="panel">
        <div class="panel-head"><h2><a class="name" href="#/jobs/${j.id}" style="text-decoration:none">${esc(j.name)}</a></h2><div class="right">${plural(j.usernames.length, "profilo", "profili")}</div></div>
        ${lists[i].length ? `<table class="table"><thead><tr><th>Profilo</th><th class="num">Nel dataset</th><th class="num">Con caption</th><th class="num">Scartate</th><th>Composizione</th><th></th></tr></thead><tbody>
          ${lists[i].map((d) => `<tr class="clickable" data-href="#/datasets/${j.id}/${esc(d.username)}">
            <td class="primary"><a class="name" href="#/datasets/${j.id}/${esc(d.username)}">@${esc(d.username)}</a>${d.updated_at ? `<span class="sub">aggiornato ${fmtDate(d.updated_at)}</span>` : '<span class="sub">non ancora scaricato</span>'}</td>
            <td class="num end">${fmtInt(d.images)}</td>
            <td class="num hide-phone">${fmtInt(d.captioned)}</td>
            <td class="num hide-phone">${fmtInt(d.rejected)}</td>
            <td class="secondary" style="min-width:160px">${(d.images + d.rejected) ? datasetFigures(d) : '<span class="dash">—</span>'}</td>
            <td class="actions">${d.images ? `<a class="link-btn" href="/api/datasets/${j.id}/${esc(d.username)}/export" download>Esporta ZIP</a>` : ""}</td>
          </tr>`).join("")}</tbody></table>` : '<div class="panel-body muted">Nessun profilo in questo job.</div>'}
      </section>`).join("")}<div>${FUNNEL_LEGEND}</div></div>` : `
    <div class="empty"><p>I dataset nascono dai job: crea un job con i profili da scaricare e avvialo.</p><a class="btn btn-primary" href="#/jobs/new">Nuovo job</a></div>`}`;
  view.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-href]");
    if (tr && !e.target.closest("a")) location.hash = tr.dataset.href;
  });
}

/* ------------------------------------------------------------------ */
/* View: gallery                                                       */
/* ------------------------------------------------------------------ */

async function viewGallery(jobId, username, query) {
  const tab = query.get("view") === "rejected" ? "rejected" : "kept";
  const [job, data] = await Promise.all([api(`/jobs/${jobId}`), api(`/datasets/${jobId}/${username}?view=${tab}`)]);
  setCrumbs([{ label: "Dataset", href: "#/datasets" }, { label: job.name, href: `#/jobs/${jobId}` }, { label: "@" + username }]);
  const s = data.summary;
  const base = `/api/datasets/${jobId}/${username}`;
  const PAGE = 60;
  let limit = PAGE;
  let filter = "";
  let onlyMissing = false;
  const view = $("#view");

  const profile = s.profile || {};
  const subParts = [];
  if (profile.full_name) subParts.push(esc(profile.full_name));
  if (profile.posts_count) subParts.push(`${fmtInt(profile.posts_count)} post sul profilo`);
  subParts.push(s.feed_complete ? "feed scaricato per intero" : "feed non ancora completo");

  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>@${esc(username)}</h1><p class="subline">${subParts.join(" · ")}</p></div>
      <div class="title-actions">${s.images ? `<a class="btn" href="${base}/export" download>Esporta ZIP</a>` : ""}<a class="btn" href="#/jobs/${jobId}">Apri job</a></div>
    </div>
    <div class="stats">
      <div class="stat lead"><div class="k">Nel dataset</div><div class="v" data-kept>${fmtInt(s.images)}</div></div>
      <div class="stat"><div class="k">Con caption</div><div class="v">${fmtInt(s.captioned)}${s.images ? `<small>/ ${fmtInt(s.images)}</small>` : ""}</div></div>
      <div class="stat"><div class="k">Senza caption</div><div class="v">${fmtInt(Math.max(0, s.images - s.captioned))}</div></div>
      <div class="stat"><div class="k">Scartate</div><div class="v" data-rej>${fmtInt(s.rejected)}</div></div>
    </div>
    <div class="tabs" role="tablist" style="margin-top:24px">
      <button role="tab" data-tab="kept" aria-selected="${tab === "kept"}">Nel dataset<span class="tab-count">${fmtInt(s.images)}</span></button>
      <button role="tab" data-tab="rejected" aria-selected="${tab === "rejected"}">Scartate<span class="tab-count">${fmtInt(s.rejected)}</span></button>
    </div>
    <div class="toolbar">
      <input class="input" type="search" placeholder="Cerca nel nome o nella caption" aria-label="Cerca" data-search>
      ${tab === "kept" ? '<label class="switch"><input type="checkbox" data-missing><span class="track"></span><span class="switch-text">Solo senza caption</span></label>' : ""}
      <span class="right" data-shown></span>
    </div>
    <div class="gallery" data-gallery></div>
    <div style="margin-top:20px;text-align:center" data-more></div>
    <p class="help" style="margin-top:24px">Cartella: <span class="mono">${esc(data.path)}</span></p>`;

  const items = data.items;

  function visible() {
    const q = filter.toLowerCase();
    return items.filter((it) => (!q || it.name.toLowerCase().includes(q) || it.caption.toLowerCase().includes(q))
      && (!onlyMissing || !it.has_caption));
  }

  function tile(it) {
    const src = `${base}/file/${tab}/${encodeURIComponent(it.name)}`;
    const kind = SOURCE_KIND[it.source] || "";
    const r = it.reason;
    return `<article class="tile" data-name="${esc(it.name)}">
      <a class="img" href="${src}" target="_blank" rel="noopener"><img src="${src}" alt="${esc(it.caption ? it.caption.slice(0, 120) : "Immagine " + it.name)}" loading="lazy"></a>
      <div class="body">
        <div class="meta"><span class="mono" title="${esc(it.name)}">${esc(it.name)}</span>${kind ? `<span class="src src-label">${kind}</span>` : ""}</div>
        ${tab === "kept"
          ? `<label class="visually-hidden" for="c-${esc(it.name)}">Caption di ${esc(it.name)}</label><textarea class="textarea" id="c-${esc(it.name)}" data-caption placeholder="Nessuna caption: scrivila qui o generala con un job">${esc(it.caption)}</textarea>`
          : `<div class="reason">${esc(r ? r.reason : "Scartata")}<span class="muted">${r ? `${r.by === "filter" ? "Filtro" : r.by === "duplicate" ? "Duplicato" : "A mano"}${r.confidence ? ` · confidenza ${r.confidence.toFixed(2)}` : ""} · ${fmtDate(r.at)}` : ""}</span></div>`}
        ${it.ig_caption ? `<details><summary>Didascalia originale</summary><p>${esc(it.ig_caption)}</p></details>` : ""}
        <div class="foot">${tab === "kept"
          ? '<button class="link-btn danger" data-reject>Scarta</button><span class="stamp" data-stamp></span>'
          : '<button class="link-btn" data-restore>Rimetti nel dataset</button>'}</div>
      </div></article>`;
  }

  function render() {
    const list = visible();
    const gallery = $("[data-gallery]", view);
    if (!items.length) {
      gallery.outerHTML = `<div class="empty" data-gallery><p>${tab === "kept" ? "Nessuna immagine nel dataset. Avvia il job per scaricare il profilo." : "Nessuna immagine scartata."}</p></div>`;
      $("[data-shown]", view).textContent = "";
      return;
    }
    gallery.innerHTML = list.length ? list.slice(0, limit).map(tile).join("") : '<div class="empty" style="grid-column:1/-1"><p>Nessuna immagine corrisponde alla ricerca.</p></div>';
    $("[data-shown]", view).textContent = `${fmtInt(Math.min(limit, list.length))} di ${fmtInt(list.length)}`;
    $("[data-more]", view).innerHTML = list.length > limit ? `<button class="btn" data-more-btn>Mostra altre ${Math.min(PAGE, list.length - limit)}</button>` : "";
  }

  view.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-tab]");
    if (t) { location.hash = `#/datasets/${jobId}/${username}${t.dataset.tab === "rejected" ? "?view=rejected" : ""}`; return; }
    if (e.target.closest("[data-more-btn]")) { limit += PAGE; render(); return; }
    const card = e.target.closest("[data-name]");
    if (!card) return;
    const name = card.dataset.name;
    const action = e.target.closest("[data-reject]") ? "reject" : e.target.closest("[data-restore]") ? "restore" : null;
    if (!action) return;
    try {
      await api(`/datasets/${jobId}/${username}/${action}/${encodeURIComponent(name)}`, { method: "POST" });
      const idx = items.findIndex((i) => i.name === name);
      if (idx >= 0) items.splice(idx, 1);
      card.remove();
      toast(action === "reject" ? "Spostata tra le scartate" : "Rimessa nel dataset");
      const counter = $(action === "reject" ? "[data-kept]" : "[data-rej]", view);
      counter.textContent = fmtInt(items.length);
      $("[data-shown]", view).textContent = `${fmtInt(Math.min(limit, visible().length))} di ${fmtInt(visible().length)}`;
    } catch (err) { toast(err.message, true); }
  });

  // Captions save themselves when the field loses focus
  view.addEventListener("focusout", async (e) => {
    if (!e.target.matches("[data-caption]")) return;
    const card = e.target.closest("[data-name]");
    const it = items.find((i) => i.name === card.dataset.name);
    const value = e.target.value.trim();
    if (!it || value === it.caption) return;
    const stamp = $("[data-stamp]", card);
    stamp.textContent = "Salvataggio…";
    try {
      await api(`/datasets/${jobId}/${username}/caption/${encodeURIComponent(it.name)}`, { method: "PUT", body: { caption: value } });
      it.caption = value; it.has_caption = true;
      stamp.textContent = "Salvata";
      setTimeout(() => { if (stamp.textContent === "Salvata") stamp.textContent = ""; }, 2500);
    } catch (err) { stamp.textContent = ""; toast(err.message, true); }
  });

  $("[data-search]", view).addEventListener("input", (e) => { filter = e.target.value; limit = PAGE; render(); });
  const missing = $("[data-missing]", view);
  if (missing) missing.addEventListener("change", (e) => { onlyMissing = e.target.checked; limit = PAGE; render(); });
  render();
}

/* ------------------------------------------------------------------ */
/* View: global settings                                               */
/* ------------------------------------------------------------------ */

async function viewSettings() {
  setCrumbs([{ label: "Impostazioni globali" }]);
  const [sc, settings, accounts] = await Promise.all([schema(), api("/settings"), api("/accounts")]);
  const count = Object.keys(settings.overrides).length;
  const view = $("#view");
  view.innerHTML = `
    <div class="title-row"><div class="titles"><h1>Impostazioni globali</h1>
      <p class="subline">Valgono per ogni job che non le personalizza. Senza un valore qui si usa il file .env, poi il predefinito${count ? ` · ${plural(count, "valore impostato", "valori impostati")} qui` : ""}.</p></div></div>
    <section class="panel"><div class="panel-body" data-editor></div></section>
    <div class="savebar clean" data-savebar><span class="note" data-note>Tutto salvato</span>
      <button class="btn" data-act="discard" hidden>Annulla modifiche</button>
      <button class="btn btn-primary" data-act="save" disabled>Salva</button></div>`;

  const original = JSON.stringify(settings.overrides);
  const editor = settingsEditor({
    fields: sc.fields, groups: sc.groups, inherited: settings.base, overrides: settings.overrides,
    mode: "global", accounts, onChange: () => {
      const dirty = JSON.stringify(editor.getOverrides()) !== original;
      markDirty(dirty);
      $("[data-savebar]", view).classList.toggle("clean", !dirty);
      $("[data-note]", view).textContent = dirty ? "Modifiche non salvate" : "Tutto salvato";
      $('[data-act="save"]', view).disabled = !dirty;
      $('[data-act="discard"]', view).hidden = !dirty;
    },
  });
  $("[data-editor]", view).appendChild(editor.el);

  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    if (btn.dataset.act === "discard") { markDirty(false); route(); return; }
    btn.disabled = true;
    try {
      await api("/settings", { method: "PUT", body: { overrides: editor.getOverrides() } });
      markDirty(false);
      toast("Impostazioni salvate");
      route();
    } catch (err) { toast(err.message, true); btn.disabled = false; }
  });
}

/* ------------------------------------------------------------------ */
/* View: accounts                                                      */
/* ------------------------------------------------------------------ */

async function viewAccounts() {
  setCrumbs([{ label: "Account Instagram" }]);
  const accounts = await api("/accounts");
  const view = $("#view");
  const usedBy = (a) => {
    const parts = [];
    if (a.used_by_jobs) parts.push(plural(a.used_by_jobs, "job", "job"));
    if (a.used_globally) parts.push("predefinito globale");
    return parts.length ? parts.join(" · ") : '<span class="dash">—</span>';
  };
  const statusOf = (a) => a.valid === true ? '<span class="pill ok">Valida</span>' : a.valid === false ? '<span class="pill bad">Scaduta</span>' : '<span class="pill neutral">Non verificata</span>';

  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>Account Instagram</h1><p class="subline">Ogni job può usare un account diverso, per esempio quello che segue un profilo privato. Le sessioni restano solo su questo computer.</p></div>
      <div class="title-actions"><button class="btn btn-primary" data-act="add">Aggiungi account</button></div>
    </div>
    <section class="panel" data-add-panel hidden style="margin-bottom:24px">
      <div class="panel-head"><h2>Nuovo account</h2></div>
      <form class="panel-body form-grid" data-add-form autocomplete="off">
        <div><label class="label" for="acc-label">Nome</label><input class="input" id="acc-label" required placeholder="Es. account di lavoro" style="max-width:420px"></div>
        <div><label class="label" for="acc-session">Session ID</label><input class="input mono" id="acc-session" type="password" required spellcheck="false" style="max-width:420px">
          <p class="help">Dal browser in cui hai fatto login: Strumenti per sviluppatori → Application → Cookies → https://www.instagram.com → valore di <span class="mono">sessionid</span>.</p></div>
        <div style="display:flex;gap:8px"><button class="btn btn-primary" type="submit">Salva account</button><button class="btn" type="button" data-act="cancel-add">Annulla</button></div>
      </form>
    </section>
    ${accounts.length ? `<div class="panel"><table class="table">
      <thead><tr><th>Nome</th><th>Sessione</th><th>Stato</th><th class="num">Usato da</th><th></th></tr></thead>
      <tbody>${accounts.map((a) => `<tr data-id="${esc(a.id)}">
        <td class="primary"><span class="name">${esc(a.label)}</span>${a.user_id ? `<span class="sub">ID utente <span class="mono">${esc(a.user_id)}</span></span>` : ""}</td>
        <td class="secondary"><span class="mono">${esc(a.session)}</span></td>
        <td class="end" data-state>${statusOf(a)}${a.checked_at ? `<span class="sub">${fmtDate(a.checked_at)}</span>` : ""}</td>
        <td class="num hide-phone">${usedBy(a)}</td>
        <td class="actions"><button class="link-btn" data-act="check">Verifica</button>
          ${a.readonly ? "" : `&nbsp;&nbsp;<button class="link-btn" data-act="edit">Modifica</button>&nbsp;&nbsp;<button class="link-btn danger" data-act="delete">Elimina</button>`}</td>
      </tr>`).join("")}</tbody></table></div>` : `
    <div class="empty"><p>Nessuna sessione. Aggiungi un account oppure imposta INSTAGRAM_SESSION_ID nel file .env.</p></div>`}`;

  const panel = $("[data-add-panel]", view);
  $("[data-add-form]", view).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/accounts", { method: "POST", body: { label: $("#acc-label").value, session_id: $("#acc-session").value } });
      toast("Account aggiunto");
      route();
    } catch (err) { toast(err.message, true); }
  });

  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "add") { panel.hidden = false; $("#acc-label").focus(); return; }
    if (act === "cancel-add") { panel.hidden = true; return; }
    const tr = btn.closest("tr[data-id]");
    const acc = accounts.find((a) => a.id === tr.dataset.id);
    try {
      if (act === "check") {
        btn.disabled = true; btn.textContent = "Verifica in corso…";
        const r = await api(`/accounts/${acc.id}/check`, { method: "POST" });
        toast(r.valid ? `${acc.label}: sessione valida` : `${acc.label}: ${r.error}`, !r.valid);
        route();
      } else if (act === "edit") {
        const dlg = $("#dialog");
        dlg.innerHTML = `<form method="dialog"><div class="d-body"><h2>Modifica account</h2>
          <div><label class="label" for="ed-label">Nome</label><input class="input" id="ed-label" value="${esc(acc.label)}"></div>
          <div><label class="label" for="ed-session">Nuovo Session ID</label><input class="input mono" id="ed-session" type="password" placeholder="Lascia vuoto per tenere ${esc(acc.session)}"></div>
          </div><div class="d-foot"><button class="btn" value="cancel">Annulla</button><button class="btn btn-primary" value="ok">Salva</button></div></form>`;
        dlg.showModal();
        dlg.addEventListener("close", async () => {
          if (dlg.returnValue !== "ok") return;
          try {
            await api(`/accounts/${acc.id}`, { method: "PUT", body: { label: $("#ed-label").value, session_id: $("#ed-session").value } });
            toast("Account aggiornato"); route();
          } catch (err) { toast(err.message, true); }
        }, { once: true });
      } else if (act === "delete") {
        const ok = await confirmDialog({
          title: `Eliminare “${acc.label}”?`,
          body: (acc.used_by_jobs || acc.used_globally)
            ? `È in uso (${usedBy(acc)}): dove era scelto, i job non troveranno più l'account e l'avvio verrà rifiutato finché non ne scegli un altro.`
            : "La sessione viene rimossa da questo computer.",
          confirm: "Elimina account", danger: true,
        });
        if (!ok) return;
        await api(`/accounts/${acc.id}`, { method: "DELETE" });
        toast("Account eliminato"); route();
      }
    } catch (err) { toast(err.message, true); btn.disabled = false; }
  });
}

/* ------------------------------------------------------------------ */
/* View: home                                                          */
/* ------------------------------------------------------------------ */

const ENGINE_PREFIX = { ollama: "ollama", "llama.cpp": "llama", strata: "strata" };

async function viewHome() {
  setCrumbs([{ label: "Home" }]);
  const [accounts, jobs, runs, settings] = await Promise.all([
    api("/accounts"), api("/jobs"), api("/runs?limit=4"), api("/settings"),
  ]);
  const eff = settings.effective;
  const engine = eff.engine.value;
  const host = eff[`${ENGINE_PREFIX[engine]}_host`].value;
  const usesAI = eff.filter_enabled.value || eff.captions_enabled.value;
  const accountId = eff.account.value;
  const account = accountId ? accounts.find((a) => a.id === accountId) : accounts.find((a) => a.id === "env");

  const steps = [
    {
      id: "session", done: !!account, warn: account && account.valid === false, title: "Sessione Instagram",
      detail: account
        ? `${esc(account.label)} · ${account.valid === true ? "valida" : account.valid === false ? "scaduta: aggiornala" : "non ancora verificata"}`
        : "Aggiungi un account, oppure imposta INSTAGRAM_SESSION_ID nel file .env.",
      act: `<a class="btn" href="#/accounts">${account ? "Gestisci" : "Aggiungi account"}</a>`,
    },
    {
      id: "engine", optional: true, done: false, title: "Engine Visual AI",
      detail: `${esc(CHOICE_LABEL.engine[engine])} su <span class="mono">${esc(host)}</span> · verifica in corso…`,
      act: '<a class="btn" href="#/settings">Impostazioni</a>',
    },
    {
      id: "job", done: jobs.length > 0, title: "Primo job",
      detail: jobs.length ? `${plural(jobs.length, "job salvato", "job salvati")}` : "Un job è la lista dei profili da scaricare.",
      act: `<a class="btn" href="${jobs.length ? "#/jobs" : "#/jobs/new"}">${jobs.length ? "Apri job" : "Crea job"}</a>`,
    },
    {
      id: "run", done: runs.length > 0, title: "Prima esecuzione",
      detail: runs.length
        ? `Ultima ${fmtDate(runs[0].created_at)} · ${esc((STATUS[runs[0].status] || ["", runs[0].status])[1].toLowerCase())}`
        : "Avvia un job: la prima passata scarica tutto il profilo, le successive solo le novità.",
      act: runs.length ? `<a class="btn" href="#/runs/${runs[0].id}">Apri</a>` : "",
    },
  ];
  const required = steps.filter((s) => !s.optional);
  const done = required.filter((s) => s.done).length;
  const subline = done === required.length
    ? `Tutto pronto · ${plural(jobs.length, "job", "job")} · ultimo avvio ${fmtDate(runs[0].created_at)}`
    : `Mancano ${required.length - done} ${required.length - done === 1 ? "passo" : "passi"} per il primo dataset`;
  const exampleJob = jobs[0] ? jobs[0].name : "Paesaggi alpini";

  const view = $("#view");
  view.innerHTML = `
    <div class="title-row">
      <div class="titles"><h1>Home</h1><p class="subline">${subline}</p></div>
      <div class="title-actions"><button class="btn" data-act="tour">Rivedi il tutorial</button><a class="btn btn-primary" href="#/jobs/new">Nuovo job</a></div>
    </div>
    <div class="stack">
      <div class="split">
        <section class="panel" aria-labelledby="h-setup">
          <div class="panel-head"><h2 id="h-setup">Per iniziare</h2></div>
          <div class="setup-progress">
            <div class="line"><span>${done === required.length ? "Configurazione completa" : "Configurazione"}</span><span>${done} di ${required.length}</span></div>
            <div class="bar"><i style="width:${(100 * done) / required.length}%"></i></div>
          </div>
          <ul class="setup">${steps.map((s) => `
            <li class="${s.done ? "done" : s.warn ? "warn" : ""}" data-step="${s.id}">
              <span class="mark" aria-hidden="true"></span>
              <span class="what">${s.title}${s.optional ? ' <span class="opt">· facoltativo</span>' : ""}<span class="visually-hidden">${s.done ? " (fatto)" : " (da fare)"}</span></span>
              <span class="detail">${s.detail}</span>
              ${s.act ? `<span class="act">${s.act}</span>` : ""}
            </li>`).join("")}
          </ul>
        </section>
        <aside class="rail">
          <section class="panel" aria-labelledby="h-runs">
            <div class="panel-head"><h2 id="h-runs">Ultime esecuzioni</h2>${runs.length ? '<div class="right"><a href="#/runs">Tutte</a></div>' : ""}</div>
            ${runs.length ? `<ul class="run-list">${runs.map((r) => {
              const t = runTotals(r);
              return `<li><a href="#/runs/${r.id}"><span class="when">${esc(r.job_name)}</span>${statusPill(r.status)}
                <span class="what">${fmtDate(r.created_at)}${t.profiles ? ` · ${fmtInt(t.downloaded)} nuove · ${fmtInt(t.kept)} nel dataset` : ""}</span></a></li>`;
            }).join("")}</ul>` : '<div class="panel-body muted">Qui compaiono gli ultimi avvii, con il loro esito.</div>'}
          </section>
        </aside>
      </div>

      <section class="panel" aria-labelledby="h-flow">
        <div class="panel-head"><h2 id="h-flow">Come funziona</h2><div class="right">Ogni avvio esegue questi passi per ciascun profilo del job</div></div>
        <ol class="flow">
          <li><span class="n">01</span><span class="t">Scraping</span><span class="d">Un solo Chromium con la tua sessione legge post, caroselli e storie in evidenza, con pause tra le richieste.</span></li>
          <li><span class="n">02</span><span class="t">Download</span><span class="d">Immagini alla massima risoluzione, in parallelo. Quelle già presenti vengono saltate.</span></li>
          <li><span class="n">03</span><span class="t">Duplicati</span><span class="d">Le copie identiche vanno in <span class="mono">_rejected</span>; resta la prima.</span></li>
          <li><span class="n">04</span><span class="t">Filtro</span><span class="opt-label">facoltativo</span><span class="d">Il modello scarta ciò che non rispetta il tuo criterio e annota il motivo.</span></li>
          <li><span class="n">05</span><span class="t">Ottimizzazione</span><span class="opt-label">facoltativo</span><span class="d">Ridimensiona e ricomprime le immagini per il training.</span></li>
          <li><span class="n">06</span><span class="t">Caption</span><span class="opt-label">facoltativo</span><span class="d">Un file .txt o .json accanto a ogni immagine, con la tua trigger word.</span></li>
        </ol>
      </section>

      <section class="panel" aria-labelledby="h-chain" data-tour="chain">
        <div class="panel-head"><h2 id="h-chain">Da dove arriva ogni impostazione</h2></div>
        <div class="chain">
          <div class="node first"><span class="t">Job</span><span class="d">Solo ciò che personalizzi in quel job.</span></div>
          <div class="node"><span class="t">Impostazioni globali</span><span class="d">Valori comuni a tutti i job.</span></div>
          <div class="node"><span class="t">File .env</span><span class="d">Variabili d'ambiente del progetto.</span></div>
          <div class="node"><span class="t">Predefinito</span><span class="d">Il valore di fabbrica.</span></div>
        </div>
        <p class="chain-note">Vince il primo livello che ha un valore. Nell'editor ogni campo mostra da quale livello arriva, e "Ripristina" lo riporta a quello successivo.</p>
      </section>

      <section class="panel" aria-labelledby="h-cli">
        <div class="panel-head"><h2 id="h-cli">Da terminale</h2><div class="right">Stessa pipeline, stesse impostazioni</div></div>
<pre class="code"><span class="c"># apri questa interfaccia</span>
instagram-crawler gui
<span class="c"># un profilo, con le impostazioni globali</span>
instagram-crawler nome_utente
<span class="c"># un job salvato qui</span>
instagram-crawler --job "${esc(exampleJob)}"</pre>
      </section>
    </div>`;

  $('[data-act="tour"]', view).addEventListener("click", () => startTour());

  // The engine check can take a moment: fill it in when it answers
  const li = $('[data-step="engine"]', view);
  try {
    const r = await api("/engine/check", { method: "POST", body: {} });
    if (!li.isConnected) return;
    li.classList.toggle("done", r.ok);
    li.classList.toggle("warn", !r.ok && usesAI);
    $(".detail", li).innerHTML = `${esc(CHOICE_LABEL.engine[engine])} su <span class="mono">${esc(host)}</span> · `
      + (r.ok ? "raggiungibile" : usesAI ? "non raggiungibile: filtro e caption non partiranno" : "non raggiungibile, serve solo per filtro e caption");
  } catch (e) {
    if (li.isConnected) $(".detail", li).textContent = `Verifica non riuscita: ${e.message}`;
  }
}

/* ------------------------------------------------------------------ */
/* Tour: runs once on first start, skippable, can be replayed from Home */
/* ------------------------------------------------------------------ */

const TOUR_ART = `
  <div class="tour-art" aria-hidden="true">
    <div class="track"></div>
    <div class="node n1"><b>${ICON.account}</b>Profilo</div>
    <div class="node n2"><b>${ICON.filter}</b>Filtro</div>
    <div class="node n3"><b>${ICON.data}</b>Dataset</div>
    <i class="pic"></i><i class="pic r d2"></i><i class="pic d3"></i>
  </div>`;

const TOUR = [
  { route: "/home", art: true, title: "Benvenuto in Profile Crawler", next: "Inizia",
    text: "Trasforma profili Instagram in dataset per LoRA: scarica le immagini, toglie doppioni e scarti, scrive le caption. In sei passi ti mostro dove sta ogni cosa." },
  { target: '#nav a[href="#/accounts"]', title: "Account Instagram",
    text: "Lo scraping usa la sessione di un account con cui hai fatto login nel browser. Aggiungila qui o nel file .env; ogni job può usare un account diverso." },
  { target: '#nav a[href="#/settings"]', title: "Impostazioni globali",
    text: "I valori comuni a tutti i job: cosa scaricare, l'engine Visual AI con host, modello e API key, i prompt di filtro e caption." },
  { route: "/home", target: '[data-tour="chain"]', title: "Da dove arriva ogni valore",
    text: "Un job personalizza solo ciò che gli serve; il resto lo eredita dalle impostazioni globali, poi dal .env, poi dal predefinito." },
  { route: "/jobs", target: '[data-tour="new-job"]', title: "Job",
    text: "Una lista di profili con le sue personalizzazioni. Lo salvi una volta e lo rilanci quando vuoi: le passate successive scaricano solo le novità." },
  { target: '#nav a[href="#/runs"]', title: "Esecuzioni",
    text: "Gli avvii vanno in coda e partono uno alla volta. Segui log e avanzamento dal vivo e interrompi quando vuoi." },
  { target: '#nav a[href="#/datasets"]', title: "Dataset",
    text: "Una galleria per profilo: correggi le caption, scarta o recupera immagini, esporta lo ZIP per il training. Nulla viene cancellato." },
  { route: "/home", title: "Pronto a partire", next: "Fine", last: true,
    text: "Il tutorial resta disponibile dalla Home, con il pulsante “Rivedi il tutorial”." },
];

const tour = { i: 0, el: null, target: null };
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(selector, timeout = 3000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const el = $(selector);
    if (el) return el;
    await sleep(50);
  }
  return null;
}

function isShown(el) {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && el.offsetParent !== null;
}

function placeTour() {
  if (!tour.el) return;
  const spot = $(".tour-spot", tour.el);
  const card = $(".tour-card", tour.el);
  const cw = card.offsetWidth, ch = card.offsetHeight;
  const vw = innerWidth, vh = innerHeight, gap = 16, pad = 6;
  if (!tour.target) {
    spot.classList.add("center");
    Object.assign(spot.style, { top: `${vh / 2}px`, left: `${vw / 2}px`, width: "0px", height: "0px" });
    Object.assign(card.style, { top: `${Math.max(16, (vh - ch) / 2)}px`, left: `${Math.max(16, (vw - cw) / 2)}px` });
    return;
  }
  const r = tour.target.getBoundingClientRect();
  spot.classList.remove("center");
  Object.assign(spot.style, { top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
  let top, left;
  if (r.right + pad + gap + cw <= vw - 16) { left = r.right + pad + gap; top = r.top + r.height / 2 - ch / 2; }
  else if (r.bottom + pad + gap + ch <= vh - 16) { top = r.bottom + pad + gap; left = r.left + r.width / 2 - cw / 2; }
  else { top = r.top - pad - gap - ch; left = r.left + r.width / 2 - cw / 2; }
  Object.assign(card.style, {
    top: `${Math.min(Math.max(16, top), vh - ch - 16)}px`,
    left: `${Math.min(Math.max(16, left), vw - cw - 16)}px`,
  });
}

async function showTourStep(i) {
  const step = TOUR[i];
  tour.i = i;
  if (step.route && currentPath().path !== step.route) location.hash = `#${step.route}`;
  let target = step.target ? await waitFor(step.target) : null;
  if (!tour.el) return; // skipped while waiting
  if (target && !isShown(target)) target = null; // e.g. the sidebar is folded on a phone
  if (target) {
    target.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
    await sleep(reducedMotion() ? 0 : 280);
  }
  tour.target = target;

  const middle = TOUR.length - 2;
  const card = $(".tour-card", tour.el);
  card.classList.toggle("wide", !!step.art);
  const noJobs = step.last && !(await api("/jobs").catch(() => [1])).length;
  card.innerHTML = `
    <div class="body-anim">
      ${step.art ? TOUR_ART : ""}
      ${i > 0 && !step.last ? `<span class="step">Passo ${i} di ${middle}</span>` : ""}
      <h2 id="tour-title">${esc(step.title)}</h2>
      <p id="tour-text">${esc(step.text)}</p>
      <div class="foot">
        ${step.last ? "" : '<button class="link-btn skip" data-t="skip">Salta il tutorial</button>'}
        ${step.last ? '<span class="skip"></span>' : `<span class="tour-dots" aria-hidden="true">${TOUR.slice(1, -1).map((_, k) => `<i class="${k + 1 === i ? "on" : ""}"></i>`).join("")}</span>`}
        ${i > 0 && !step.last ? '<button class="btn" data-t="back">Indietro</button>' : ""}
        ${noJobs ? '<button class="btn" data-t="new-job">Crea il primo job</button>' : ""}
        <button class="btn btn-primary" data-t="next">${esc(step.next || "Avanti")}</button>
      </div>
    </div>`;
  placeTour();
  $('[data-t="next"]', card).focus();
}

function endTour() {
  if (!tour.el) return;
  tour.el.remove();
  tour.el = null;
  tour.target = null;
  window.removeEventListener("resize", placeTour);
  $("#sheet").removeEventListener("scroll", placeTour);
  document.removeEventListener("keydown", tourKeys, true);
  api("/ui", { method: "PUT", body: { tour_seen: true } }).catch(() => {});
}

function tourKeys(e) {
  if (!tour.el) return;
  if (e.key === "Escape") { e.preventDefault(); endTour(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); tourNext(); }
  else if (e.key === "ArrowLeft" && tour.i > 0) { e.preventDefault(); showTourStep(tour.i - 1); }
  else if (e.key === "Tab") {
    // keep the focus inside the card
    const items = $$("button", tour.el);
    if (!items.length) return;
    const idx = items.indexOf(document.activeElement);
    e.preventDefault();
    items[(idx + (e.shiftKey ? -1 : 1) + items.length) % items.length].focus();
  }
}

function tourNext() {
  if (tour.i >= TOUR.length - 1) endTour();
  else showTourStep(tour.i + 1);
}

async function startTour() {
  if (tour.el) return;
  if (state.dirty && !window.confirm("Ci sono modifiche non salvate. Avviare il tutorial e uscire da questa pagina?")) return;
  markDirty(false);
  $("#shell").classList.remove("menu-open");
  const el = document.createElement("div");
  el.className = "tour";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  el.setAttribute("aria-labelledby", "tour-title");
  el.setAttribute("aria-describedby", "tour-text");
  el.innerHTML = '<div class="tour-spot center"></div><div class="tour-card" tabindex="-1"></div>';
  document.body.appendChild(el);
  tour.el = el;
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-t]");
    if (!b) return;
    const t = b.dataset.t;
    if (t === "skip") endTour();
    else if (t === "back") showTourStep(tour.i - 1);
    else if (t === "next") tourNext();
    else if (t === "new-job") { endTour(); location.hash = "#/jobs/new"; }
  });
  window.addEventListener("resize", placeTour);
  $("#sheet").addEventListener("scroll", placeTour, { passive: true });
  document.addEventListener("keydown", tourKeys, true);
  await showTourStep(0);
}

/* ------------------------------------------------------------------ */
/* Boot                                                                */
/* ------------------------------------------------------------------ */

$("#menu-btn").addEventListener("click", () => {
  const open = $("#shell").classList.toggle("menu-open");
  $("#menu-btn").setAttribute("aria-expanded", String(open));
});
$("#nav").addEventListener("click", () => $("#shell").classList.remove("menu-open"));
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ""; } });

refreshMeta();
setInterval(refreshMeta, 3000);
route().then(async () => {
  // First start of this installation: show the tour once
  try {
    const ui = await api("/ui");
    if (!ui.tour_seen) startTour();
  } catch (_) { /* no tour if the state cannot be read */ }
});
