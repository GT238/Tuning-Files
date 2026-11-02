"use strict";

const state = { files: [], byPath: {}, usedBy: {}, q: "", maker: "all", type: "all", sort: "path", needsOnly: false, filesUrl: "/files/" };

const el = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function humanSize(b) {
  if (typeof b !== "number") return "—";
  if (b < 1024) return b + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1, v = b;
  do { v /= 1024; i++; } while (v >= 1024 && i < units.length - 1);
  return (v >= 100 ? Math.round(v) : v.toFixed(1)) + " " + units[i];
}

const TYPE_LABELS = { stock: "Stock", tune: "Tune", xdf: "XDF", tool: "Tool", doc: "Doc", other: "Other" };
function badge(t) {
  const label = TYPE_LABELS[t] || (t || "file");
  const cls = TYPE_LABELS[t] ? "t-" + t : "t-other";
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

function haystack(f) {
  return [f.name, f.path, f.manufacturer, f.ecu, f.module, f.os_id, f.cal_id,
          f.vehicle, f.engine, f.years, f.transmission, f.description, f.notes,
          (f.tags || []).join(" ")].join(" ").toLowerCase();
}

function filtered() {
  const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const out = state.files.filter(f => {
    if (state.maker !== "all" && f.manufacturer !== state.maker) return false;
    if (state.type !== "all" && f.type !== state.type) return false;
    if (state.needsOnly && !f.needs_metadata) return false;
    if (tokens.length && !tokens.every(t => haystack(f).includes(t))) return false;
    return true;
  });
  const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const sorts = {
    path:      (a, b) => coll.compare(a.path, b.path),
    "size-desc": (a, b) => b.size - a.size,
    "size-asc":  (a, b) => a.size - b.size,
    newest:    (a, b) => (b.modified || "").localeCompare(a.modified || ""),
  };
  return out.sort(sorts[state.sort] || sorts.path);
}

function refUrl(refPath) {
  const t = state.byPath[refPath];
  if (t) return t.download_url;
  return state.filesUrl + refPath.split("/").map(encodeURIComponent).join("/");
}

function chips(f) {
  let html = "";
  if (f.xdf) html += ` <a class="xdf-link" href="${esc(refUrl(f.xdf))}" title="Compatible XDF definition">⧉ XDF</a>`;
  for (const t of (f.tools || [])) {
    html += ` <a class="xdf-link" href="${esc(refUrl(t))}" title="Related tool: ${esc(t.split("/").pop())}">⛭ tool</a>`;
  }
  return html;
}

function idCell(f) {
  let html = `<span class="mono">${esc([f.os_id, f.cal_id].filter(Boolean).join(" / ") || "—")}</span>`;
  if (f.os_id && f.os_id_in_bin === false) {
    html += ` <span class="badge t-missing" title="OS ID from metadata not found as text inside the bin — filename may be wrong, verify before use">ID?</span>`;
  }
  return html;
}

function usedByCell(f) {
  const list = state.usedBy[f.path] || [];
  if (!list.length) return "";
  const shown = list.slice(0, 3).map(u => `<a href="${esc(u.download_url)}">${esc(u.name)}</a>`).join(", ");
  const more = list.length > 3 ? ` <span class="sub">+${list.length - 3} more</span>` : "";
  return `<div class="sub">used by: ${shown}${more}</div>`;
}

function rowHtml(f) {
  const vehicle = [f.vehicle, f.engine, f.years].filter(Boolean);
  const canon = f.duplicate_of ? state.byPath[f.duplicate_of] : null;
  const dup = f.duplicate_of
    ? `<div class="sub"><a class="dup-link" href="${esc(canon ? canon.download_url : "#")}" title="Byte-identical to this file">⧉ duplicate of ${esc(f.duplicate_of.split("/").pop())}</a></div>`
    : "";
  return `<tr>
    <td class="file">${badge(f.type)}<br>
      <a href="${esc(f.download_url)}" download title="${esc(f.path)}">${esc(f.name)}</a>
      <div class="path">${esc(f.path)}</div>
      ${f.needs_metadata ? '<span class="badge t-missing">needs info</span>' : ""}
      ${f.verified ? '<span class="badge t-stock">verified</span>' : ""}
    </td>
    <td>${esc(vehicle.join(" · ") || "—")}</td>
    <td>${esc([f.manufacturer, f.ecu, f.module].filter(Boolean).join(" / ") || "—")}</td>
    <td>${idCell(f)}</td>
    <td class="num">${humanSize(f.size)}</td>
    <td class="mono hash"><span title="${esc(f.sha256)}">${esc(f.sha256.slice(0, 12))}…</span>
      <button class="copy" data-hash="${esc(f.sha256)}" title="Copy full SHA-256">copy</button></td>
    <td class="notes">${esc(f.description || "")}
      ${chips(f)}
      ${f.source ? `<div class="sub">source: ${esc(f.source)}</div>` : ""}
      ${dup}
      ${usedByCell(f)}
      ${f.notes ? `<div class="sub">${esc(f.notes)}</div>` : ""}
    </td>
  </tr>`;
}

function render() {
  const list = filtered();
  el("count").textContent = `Showing ${list.length} of ${state.files.length} files`;
  el("rows").innerHTML = list.map(rowHtml).join("");
  const empty = el("empty");
  if (state.files.length === 0) {
    empty.hidden = false;
    empty.textContent = "The archive is empty. Drop files into files/ on the server, add metadata, and rebuild.";
  } else if (list.length === 0) {
    empty.hidden = false;
    empty.textContent = "No files match — try clearing the search or filters.";
  } else {
    empty.hidden = true;
  }
}

function populateFilters(files) {
  const makers = [...new Set(files.map(f => f.manufacturer).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
  el("f-maker").innerHTML = '<option value="all">All manufacturers</option>' +
    makers.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join("");

  const present = new Set(files.map(f => f.type).filter(Boolean));
  const known = ["stock", "tune", "xdf", "tool", "doc", "other"];
  const types = [...known.filter(t => present.has(t)),
                 ...[...present].filter(t => !known.includes(t)).sort()];
  el("f-type").innerHTML = '<option value="all">All types</option>' +
    types.map(t => `<option value="${esc(t)}">${esc(TYPE_LABELS[t] || t)}</option>`).join("");
}

function wire() {
  el("search").addEventListener("input", e => { state.q = e.target.value; render(); });
  el("f-maker").addEventListener("change", e => { state.maker = e.target.value; render(); });
  el("f-type").addEventListener("change", e => { state.type = e.target.value; render(); });
  el("sort").addEventListener("change", e => { state.sort = e.target.value; render(); });
  el("f-needs").addEventListener("change", e => { state.needsOnly = e.target.checked; render(); });
  document.addEventListener("click", e => {
    const btn = e.target.closest("button.copy");
    if (btn) {
      if (navigator.clipboard) navigator.clipboard.writeText(btn.dataset.hash);
      btn.textContent = "copied";
      setTimeout(() => (btn.textContent = "copy"), 1200);
    }
  });
}

fetch("index.json")
  .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then(data => {
    state.files = data.files || [];
    state.filesUrl = data.files_url || "/files/";
    state.byPath = Object.fromEntries(state.files.map(f => [f.path, f]));
    state.usedBy = {};
    for (const f of state.files) {
      const refs = [];
      if (f.xdf) refs.push(f.xdf);
      if (Array.isArray(f.tools)) refs.push(...f.tools);
      for (const r of refs) (state.usedBy[r] = state.usedBy[r] || []).push(f);
    }
    el("generated").textContent = "Catalog generated " + (data.generated || "");
    populateFilters(state.files);
    wire();
    render();
  })
  .catch(err => {
    el("empty").hidden = false;
    el("empty").textContent = "Could not load catalog/index.json — serve this page over HTTP " +
      "(e.g. python -m http.server), not file://. (" + err + ")";
  });
