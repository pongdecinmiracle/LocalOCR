/* LocalOCR client. Vanilla JS single-page app. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  user: null,
  uploads: [],
  templates: [],
  editor: { docId: null, page: 0, template: { id: null, name: "", fields: [] }, selField: null },
  lastResults: null,
  allowRegistration: true,
};

/* ---------------- tabs ---------------- */
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#tab-" + t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "editor") refreshEditorDocs();
    if (t.dataset.tab === "run") refreshRunTab();
    if (t.dataset.tab === "admin") loadAdminUsers();
    setMonitorPolling(t.dataset.tab === "monitor");
  })
);

/* ---------------- status ---------------- */
async function loadStatus() {
  try {
    const s = await fetch("/api/status").then((r) => r.json());
    const el = $("#status");
    if (!s.ollama_up) {
      el.textContent = "⚠ Ollama not running";
      el.className = "status bad";
    } else if (!s.model_ready) {
      el.textContent = `⏳ model ${s.model} not ready`;
      el.className = "status";
    } else {
      el.textContent = `✓ ${s.model} ready`;
      el.className = "status ok";
    }
  } catch {
    $("#status").textContent = "⚠ backend offline";
    $("#status").className = "status bad";
  }
}

/* ---------------- upload ---------------- */
const dz = $("#dropzone");
$("#browseBtn").addEventListener("click", () => $("#fileInput").click());
$("#fileInput").addEventListener("change", (e) => uploadFiles(e.target.files));
["dragover", "dragenter"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    dz.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    dz.classList.remove("drag");
  })
);
dz.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));

async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  $("#uploadProgress").textContent = `Uploading & rendering ${files.length} file(s)…`;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd }).then((r) => {
      if (!r.ok) throw new Error("upload failed");
      return r.json();
    });
    res.uploads.forEach((u) => state.uploads.push(u));
    renderUploads();
    $("#uploadProgress").textContent = `Done. ${res.uploads.length} added.`;
  } catch (e) {
    $("#uploadProgress").textContent = "Upload error: " + e.message;
  }
}

async function loadUploads() {
  try {
    const r = await fetch("/api/uploads").then((x) => x.json());
    state.uploads = r.uploads || [];
  } catch {
    state.uploads = [];
  }
  renderUploads();
}

function renderUploads() {
  const wrap = $("#uploadsList");
  wrap.innerHTML = "";
  if (!state.uploads.length) {
    wrap.innerHTML = '<p class="muted">Nothing uploaded yet.</p>';
    return;
  }
  state.uploads.forEach((u, i) => {
    const tile = document.createElement("div");
    tile.className = "upload-tile";
    tile.innerHTML = `
      <img src="${u.pages[0].url}" loading="lazy" />
      <div class="name">${u.filename}</div>
      <div class="meta">${u.pages.length} page(s) · <span class="link rm">remove</span></div>`;
    tile.querySelector(".rm").addEventListener("click", async () => {
      await fetch("/api/uploads/" + u.upload_id, { method: "DELETE" });
      state.uploads.splice(i, 1);
      renderUploads();
    });
    wrap.appendChild(tile);
  });
}

/* ---------------- templates ---------------- */
async function loadTemplates() {
  const r = await fetch("/api/templates").then((x) => x.json());
  state.templates = r.templates;
  fillTemplatePickers();
}
function fillTemplatePickers() {
  const opts = '<option value="">— new template —</option>' +
    state.templates.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
  $("#templatePicker").innerHTML = opts;
  $("#runTemplate").innerHTML = state.templates.length
    ? state.templates.map((t) => `<option value="${t.id}">${t.name}</option>`).join("")
    : '<option value="">(no templates yet)</option>';
}

$("#newTemplateBtn").addEventListener("click", () => {
  state.editor.template = { id: null, name: "", fields: [] };
  state.editor.selField = null;
  $("#templateName").value = "";
  $("#templateEngine").value = "";
  $("#templatePicker").value = "";
  renderFields();
  renderBoxes();
});

$("#loadTemplateBtn").addEventListener("click", async () => {
  const id = $("#templatePicker").value;
  if (!id) return;
  const t = await fetch("/api/templates/" + id).then((r) => r.json());
  state.editor.template = { id: t.id, name: t.name, fields: t.fields, extract_mode: t.extract_mode };
  $("#templateName").value = t.name;
  $("#templateEngine").value = t.extract_mode || "";
  renderFields();
  renderBoxes();
});

$("#saveTemplateBtn").addEventListener("click", async () => {
  const tpl = state.editor.template;
  tpl.name = $("#templateName").value.trim();
  tpl.extract_mode = $("#templateEngine").value || undefined;
  if (!tpl.name) {
    alert("Give the template a name first.");
    return;
  }
  if (!tpl.fields.length) {
    alert("Draw at least one field box first.");
    return;
  }
  const saved = await fetch("/api/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tpl),
  }).then((r) => r.json());
  state.editor.template.id = saved.id;
  await loadTemplates();
  $("#templatePicker").value = saved.id;
  alert("Template saved.");
});

$("#deleteTemplateBtn").addEventListener("click", async () => {
  const id = state.editor.template.id || $("#templatePicker").value;
  if (!id) return;
  if (!confirm("Delete this template?")) return;
  await fetch("/api/templates/" + id, { method: "DELETE" });
  state.editor.template = { id: null, name: "", fields: [] };
  $("#templateName").value = "";
  await loadTemplates();
  renderFields();
  renderBoxes();
});

/* ---------------- editor: documents & pages ---------------- */
function refreshEditorDocs() {
  const sel = $("#editorDoc");
  const prev = state.editor.docId;
  sel.innerHTML =
    '<option value="">— pick —</option>' +
    state.uploads.map((u) => `<option value="${u.upload_id}">${u.filename}</option>`).join("");
  if (prev && state.uploads.find((u) => u.upload_id === prev)) sel.value = prev;
}
$("#editorDoc").addEventListener("change", (e) => {
  state.editor.docId = e.target.value || null;
  state.editor.page = 0;
  showPage();
});
$("#prevPage").addEventListener("click", () => {
  if (state.editor.page > 0) {
    state.editor.page--;
    showPage();
  }
});
$("#nextPage").addEventListener("click", () => {
  const doc = currentDoc();
  if (doc && state.editor.page < doc.pages.length - 1) {
    state.editor.page++;
    showPage();
  }
});
function currentDoc() {
  return state.uploads.find((u) => u.upload_id === state.editor.docId);
}
function showPage() {
  const doc = currentDoc();
  const img = $("#pageImg");
  if (!doc) {
    $("#stage").style.display = "none";
    $("#stageEmpty").style.display = "block";
    $("#pageLabel").textContent = "– / –";
    return;
  }
  $("#stage").style.display = "inline-block";
  $("#stageEmpty").style.display = "none";
  const p = doc.pages[state.editor.page];
  img.onload = renderBoxes;
  img.src = p.url;
  $("#pageLabel").textContent = `${state.editor.page + 1} / ${doc.pages.length}`;
}

/* ---------------- editor: box drawing ---------------- */
const overlay = $("#overlay");
let draw = null;

overlay.addEventListener("mousedown", (e) => {
  if (!currentDoc()) return;
  const r = overlay.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  draw = { x0: x, y0: y, el: document.createElement("div") };
  draw.el.className = "fbox";
  overlay.appendChild(draw.el);
});
overlay.addEventListener("mousemove", (e) => {
  if (!draw) return;
  const r = overlay.getBoundingClientRect();
  const x = Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1);
  const y = Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1);
  const bx = Math.min(draw.x0, x), by = Math.min(draw.y0, y);
  const bw = Math.abs(x - draw.x0), bh = Math.abs(y - draw.y0);
  Object.assign(draw.el.style, {
    left: bx * 100 + "%", top: by * 100 + "%",
    width: bw * 100 + "%", height: bh * 100 + "%",
  });
  draw.box = { x: bx, y: by, w: bw, h: bh };
});
window.addEventListener("mouseup", () => {
  if (!draw) return;
  const box = draw.box;
  draw.el.remove();
  draw = null;
  if (!box || box.w < 0.01 || box.h < 0.01) return; // ignore tiny clicks
  openFieldModal(null, box);
});

/* ---------------- field modal ---------------- */
let modalCtx = null; // { box, fieldId }

function openFieldModal(field, box) {
  modalCtx = { box: field ? field.box : box, fieldId: field ? field.id : null };
  $("#fieldModalTitle").textContent = field ? "Edit field" : "New field";
  $("#fName").value = field ? field.name : "";
  $("#fType").value = field ? field.type : "text";
  renderColumns(field && field.columns ? field.columns : []);
  toggleColumns();
  $("#fieldModal").classList.remove("hidden");
  $("#fName").focus();
}
function closeFieldModal() {
  $("#fieldModal").classList.add("hidden");
  modalCtx = null;
}
$("#fType").addEventListener("change", toggleColumns);
function toggleColumns() {
  $("#columnsEditor").classList.toggle("hidden", $("#fType").value !== "table");
}
function renderColumns(cols) {
  const wrap = $("#columnsList");
  wrap.innerHTML = "";
  cols.forEach((c) => addColumnRow(c.name, c.type));
  if (!cols.length) addColumnRow("", "text");
}
function addColumnRow(name = "", type = "text") {
  const row = document.createElement("div");
  row.className = "col-row";
  row.innerHTML = `
    <input type="text" class="cname" placeholder="column name" value="${name}" />
    <select class="ctype">
      <option value="text">text</option>
      <option value="number">number</option>
      <option value="date">date</option>
    </select>
    <span class="x">✕</span>`;
  row.querySelector(".ctype").value = type;
  row.querySelector(".x").addEventListener("click", () => row.remove());
  $("#columnsList").appendChild(row);
}
$("#addColumnBtn").addEventListener("click", () => addColumnRow());
$("#fieldCancel").addEventListener("click", closeFieldModal);
$("#fieldSave").addEventListener("click", () => {
  const name = $("#fName").value.trim();
  if (!name) {
    alert("Field name required.");
    return;
  }
  const type = $("#fType").value;
  const tpl = state.editor.template;
  let columns = [];
  if (type === "table") {
    columns = $$(".col-row")
      .map((r) => ({ name: r.querySelector(".cname").value.trim(), type: r.querySelector(".ctype").value }))
      .filter((c) => c.name);
    if (!columns.length) {
      alert("Add at least one column for a table field.");
      return;
    }
  }
  if (modalCtx.fieldId) {
    const f = tpl.fields.find((x) => x.id === modalCtx.fieldId);
    f.name = name;
    f.label = name;
    f.type = type;
    f.columns = type === "table" ? columns : undefined;
  } else {
    tpl.fields.push({
      id: "f" + Math.random().toString(36).slice(2, 8),
      name, label: name, type,
      page: state.editor.page,
      box: modalCtx.box,
      columns: type === "table" ? columns : undefined,
    });
  }
  closeFieldModal();
  renderFields();
  renderBoxes();
});

/* ---------------- render fields + boxes ---------------- */
function renderFields() {
  const tpl = state.editor.template;
  $("#fieldCount").textContent = tpl.fields.length;
  const wrap = $("#fieldsList");
  wrap.innerHTML = "";
  tpl.fields.forEach((f) => {
    const row = document.createElement("div");
    row.className = "field-row" + (state.editor.selField === f.id ? " sel" : "");
    row.innerHTML = `
      <span class="fname">${f.name}</span>
      <span class="ftype">${f.type}</span>
      <span class="fpage">p${f.page + 1}</span>
      <span class="edit link">✎</span>
      <span class="x">✕</span>`;
    row.querySelector(".fname").addEventListener("click", () => selectField(f.id));
    row.querySelector(".edit").addEventListener("click", (e) => {
      e.stopPropagation();
      openFieldModal(f);
    });
    row.querySelector(".x").addEventListener("click", (e) => {
      e.stopPropagation();
      tpl.fields = tpl.fields.filter((x) => x.id !== f.id);
      renderFields();
      renderBoxes();
    });
    wrap.appendChild(row);
  });
}
function selectField(id) {
  state.editor.selField = id;
  const f = state.editor.template.fields.find((x) => x.id === id);
  if (f && f.page !== state.editor.page) {
    state.editor.page = f.page;
    showPage();
  } else {
    renderBoxes();
  }
  renderFields();
}
function renderBoxes() {
  overlay.innerHTML = "";
  const tpl = state.editor.template;
  tpl.fields
    .filter((f) => f.page === state.editor.page)
    .forEach((f) => {
      const d = document.createElement("div");
      d.className = "fbox" + (f.type === "table" ? " table" : "") + (state.editor.selField === f.id ? " sel" : "");
      Object.assign(d.style, {
        left: f.box.x * 100 + "%", top: f.box.y * 100 + "%",
        width: f.box.w * 100 + "%", height: f.box.h * 100 + "%",
      });
      d.innerHTML = `<span class="lbl">${f.name}</span>`;
      d.addEventListener("click", (e) => {
        e.stopPropagation();
        selectField(f.id);
      });
      d.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        openFieldModal(f);
      });
      overlay.appendChild(d);
    });
}

/* ---------------- extract & export ---------------- */
function refreshRunTab() {
  fillTemplatePickers();
  const wrap = $("#runDocsList");
  if (!state.uploads.length) {
    wrap.innerHTML = '<p class="muted">No documents uploaded.</p>';
    return;
  }
  wrap.innerHTML = "";
  state.uploads.forEach((u) => {
    const row = document.createElement("label");
    row.className = "run-doc";
    row.innerHTML = `
      <input type="checkbox" value="${u.upload_id}" checked />
      <img src="${u.pages[0].url}" />
      <span>${u.filename} <span class="muted">(${u.pages.length}p)</span></span>`;
    wrap.appendChild(row);
  });
}
$("#selectAllDocs").addEventListener("click", () => {
  const boxes = $$("#runDocsList input[type=checkbox]");
  const allChecked = boxes.every((b) => b.checked);
  boxes.forEach((b) => (b.checked = !allChecked));
});

function showProc() {
  $("#procOverlay").classList.remove("hidden");
}
function hideProc() {
  $("#procOverlay").classList.add("hidden");
}
function updateProc({ done, total, file, pulse }) {
  $("#procTitle").textContent = `Extracting document ${Math.min(done + 1, total)} of ${total}`;
  $("#procFile").textContent = file ? "📄 " + file : "";
  $("#procCount").textContent = `${done} of ${total} complete`;
  const bar = $("#procBar");
  bar.style.width = Math.round((done / total) * 100) + "%";
  bar.classList.toggle("pulse", !!pulse);
}

const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

/* Extraction runs as a background job on the server; we just poll progress. */
async function pollJob(jobId) {
  let misses = 0;
  for (;;) {
    await sleep(1200);
    let job;
    try {
      const r = await fetch(`/api/extract/jobs/${jobId}`);
      if (!r.ok) throw new Error("poll failed");
      job = await r.json();
      misses = 0;
    } catch {
      // Tolerate brief network blips before giving up.
      if (++misses >= 5) throw new Error("Lost contact with the server.");
      continue;
    }
    updateProc({
      done: job.done,
      total: job.total,
      file: job.current_file,
      pulse: job.status === "running" || job.status === "queued",
    });
    if (job.status === "done" || job.status === "error") return job;
  }
}

$("#runBtn").addEventListener("click", async () => {
  const templateId = $("#runTemplate").value;
  if (!templateId) {
    alert("Pick a template.");
    return;
  }
  const ids = $$("#runDocsList input:checked").map((b) => b.value);
  if (!ids.length) {
    alert("Select at least one document.");
    return;
  }

  $("#runBtn").classList.add("busy");
  $("#runStatus").textContent = "";
  showProc();
  updateProc({ done: 0, total: ids.length, file: "", pulse: true });

  try {
    const start = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: templateId, upload_ids: ids }),
    }).then((r) => {
      if (!r.ok) return r.json().then((j) => Promise.reject(new Error(j.detail || "error")));
      return r.json();
    });

    const job = await pollJob(start.job_id);
    const results = job.results || [];
    if (results.length) {
      state.lastResults = { templateId, results };
      renderResults(templateId, results);
    }
    if (job.status === "error") {
      $("#runStatus").textContent = "Error: " + (job.error || "extraction failed");
    } else {
      $("#runStatus").textContent = `Done — ${results.length} document(s) extracted.`;
    }
  } catch (e) {
    $("#runStatus").textContent = "Error: " + e.message;
  } finally {
    hideProc();
    $("#runBtn").classList.remove("busy");
  }
});

function renderResults(templateId, results) {
  const tpl = state.templates.find((t) => t.id === templateId);
  const scalarFields = tpl.fields.filter((f) => f.type !== "table");
  const tableFields = tpl.fields.filter((f) => f.type === "table");
  const wrap = $("#resultsTableWrap");
  wrap.innerHTML = "";

  // scalar summary table
  if (scalarFields.length) {
    let html = '<table class="res"><thead><tr><th>file</th>';
    scalarFields.forEach((f) => (html += `<th>${f.name}</th>`));
    html += "</tr></thead><tbody>";
    results.forEach((r) => {
      html += `<tr><td>${r.file}</td>`;
      scalarFields.forEach((f) => (html += `<td>${fmt(r.fields[f.name])}</td>`));
      html += "</tr>";
    });
    html += "</tbody></table>";
    wrap.insertAdjacentHTML("beforeend", html);
  }

  // table fields, per document
  tableFields.forEach((tf) => {
    results.forEach((r) => {
      const rows = r.fields[tf.name] || [];
      const block = document.createElement("div");
      block.className = "doc-result";
      let h = `<h4>${tf.name} — ${r.file} (${rows.length} rows)</h4>`;
      h += '<table class="subtable"><thead><tr>';
      tf.columns.forEach((c) => (h += `<th>${c.name}</th>`));
      h += "</tr></thead><tbody>";
      rows.forEach((row) => {
        h += "<tr>";
        tf.columns.forEach((c) => (h += `<td>${fmt(row[c.name])}</td>`));
        h += "</tr>";
      });
      h += "</tbody></table>";
      block.innerHTML = h;
      wrap.appendChild(block);
    });
  });

  $("#resultsCard").style.display = "block";
  $("#exportLink").textContent = "";
}
function fmt(v) {
  if (v === null || v === undefined) return '<span class="muted">—</span>';
  return String(v);
}

$("#exportBtn").addEventListener("click", async () => {
  if (!state.lastResults) return;
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      template_id: state.lastResults.templateId,
      results: state.lastResults.results,
    }),
  }).then((r) => r.json());
  $("#exportLink").innerHTML = `✓ <a class="link" href="/api/download/${res.filename}">Download ${res.filename}</a>`;
});

/* ---------------- admin ---------------- */
function fmtDate(ts) {
  try { return new Date(ts * 1000).toLocaleDateString(); } catch { return ""; }
}

async function loadAdminUsers() {
  const wrap = $("#usersTableWrap");
  wrap.innerHTML = '<p class="muted">Loading…</p>';
  let data;
  try {
    const r = await fetch("/api/admin/users");
    if (!r.ok) throw new Error("not authorized");
    data = await r.json();
  } catch (e) {
    wrap.innerHTML = '<p class="muted">Could not load users.</p>';
    return;
  }
  $("#userCount").textContent = data.users.length;
  const meId = data.me;
  let html = '<table class="res"><thead><tr><th>Username</th><th>Role</th>' +
    '<th>Docs</th><th>Templates</th><th>Created</th><th>Actions</th></tr></thead><tbody>';
  data.users.forEach((u) => {
    const isMe = u.id === meId;
    const role = u.is_admin
      ? '<span class="role-admin">admin</span>'
      : '<span class="role-user">user</span>';
    const you = isMe ? ' <span class="you-tag">(you)</span>' : "";
    html += `<tr data-id="${u.id}" data-name="${u.username}" data-admin="${u.is_admin}">
      <td>${u.username}${you}</td>
      <td>${role}</td>
      <td>${u.counts.uploads}</td>
      <td>${u.counts.templates}</td>
      <td>${fmtDate(u.created_at)}</td>
      <td><div class="act">
        <button class="btn pw">Reset password</button>
        <button class="btn role">${u.is_admin ? "Revoke admin" : "Make admin"}</button>
        ${isMe ? "" : '<button class="btn danger del">Delete</button>'}
      </div></td></tr>`;
  });
  html += "</tbody></table>";
  wrap.innerHTML = html;

  $$("#usersTableWrap tr[data-id]").forEach((row) => {
    const id = row.dataset.id;
    const name = row.dataset.name;
    const isAdmin = row.dataset.admin === "true";
    row.querySelector(".pw").addEventListener("click", () => resetPassword(id, name));
    row.querySelector(".role").addEventListener("click", () => toggleAdmin(id, name, !isAdmin));
    const del = row.querySelector(".del");
    if (del) del.addEventListener("click", () => deleteUser(id, name));
  });
}

async function adminAction(promise, okMsg) {
  const msg = $("#adminMsg");
  try {
    const r = await promise;
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(j.detail || "error");
    }
    msg.textContent = okMsg || "Done.";
    await loadAdminUsers();
  } catch (e) {
    msg.textContent = "Error: " + e.message;
  }
}

$("#addUserBtn").addEventListener("click", () => {
  const username = $("#newUser").value.trim();
  const password = $("#newPass").value;
  const is_admin = $("#newAdmin").checked;
  if (!username || !password) {
    $("#adminMsg").textContent = "Username and password required.";
    return;
  }
  adminAction(
    fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, is_admin }),
    }),
    `Added ${username}.`
  ).then(() => {
    $("#newUser").value = "";
    $("#newPass").value = "";
    $("#newAdmin").checked = false;
  });
});

function resetPassword(id, name) {
  const pw = prompt(`New password for "${name}" (min 6 characters):`);
  if (!pw) return;
  adminAction(
    fetch(`/api/admin/users/${id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    }),
    `Password reset for ${name}.`
  );
}

function toggleAdmin(id, name, makeAdmin) {
  adminAction(
    fetch(`/api/admin/users/${id}/admin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_admin: makeAdmin }),
    }),
    `${name} is now ${makeAdmin ? "an admin" : "a regular user"}.`
  );
}

function deleteUser(id, name) {
  if (!confirm(`Delete user "${name}" and ALL their documents and templates? This cannot be undone.`)) return;
  adminAction(fetch(`/api/admin/users/${id}`, { method: "DELETE" }), `Deleted ${name}.`);
}

/* ---------------- monitor (admin) ---------------- */
let monitorTimer = null;

function setMonitorPolling(on) {
  if (on) {
    loadMonitor();
    if (!monitorTimer) monitorTimer = setInterval(loadMonitor, 4000);
  } else if (monitorTimer) {
    clearInterval(monitorTimer);
    monitorTimer = null;
  }
}

function fmtGB(mb) {
  return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb + " MB";
}

function setMeter(barId, percent) {
  const bar = $("#" + barId);
  const p = Math.max(0, Math.min(100, percent || 0));
  bar.style.width = p + "%";
  bar.classList.toggle("warn", p >= 60 && p < 85);
  bar.classList.toggle("crit", p >= 85);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function setSvc(id, label, value, ok) {
  const el = $("#" + id);
  el.textContent = `${label}: ${value}`;
  el.classList.toggle("ok", ok);
  el.classList.toggle("bad", !ok);
}

function renderMonitorErrors(e) {
  setSvc("svcFailed", "failed extractions (24 h)", e.jobs_failed_24h, e.jobs_failed_24h === 0);
  $("#monDoneTotal").textContent = e.jobs_done_total;
  $("#monFailTotal").textContent = e.jobs_failed_total;
  $("#monFailTotal").classList.toggle("bad", e.jobs_failed_total > 0);
  const wrap = $("#monErrorsWrap");
  if (!e.recent_failures.length) {
    wrap.innerHTML = '<p class="muted small">No failed extractions.</p>';
    return;
  }
  let html = '<table class="res"><thead><tr><th>Time</th><th>User</th><th>Docs</th><th>Error</th></tr></thead><tbody>';
  e.recent_failures.forEach((f) => {
    html += `<tr>
      <td>${new Date(f.time * 1000).toLocaleString()}</td>
      <td>${esc(f.username)}</td>
      <td>${f.documents}</td>
      <td>${esc(f.error)}</td></tr>`;
  });
  wrap.innerHTML = html + "</tbody></table>";
}

async function loadMonitor() {
  let m;
  try {
    const r = await fetch("/api/admin/metrics");
    if (!r.ok) throw new Error();
    m = await r.json();
  } catch {
    $("#monUpdated").textContent = "could not load metrics";
    return;
  }

  $("#monCpuVal").textContent = m.cpu.percent.toFixed(0) + "%";
  setMeter("monCpuBar", m.cpu.percent);
  $("#monCpuSub").textContent = m.cpu.cores + " cores (host-wide)";

  $("#monMemVal").textContent = m.memory.percent.toFixed(0) + "%";
  setMeter("monMemBar", m.memory.percent);
  $("#monMemSub").textContent = `${fmtGB(m.memory.used_mb)} of ${fmtGB(m.memory.total_mb)}`;

  $("#monDiskVal").textContent = m.disk.percent.toFixed(0) + "%";
  setMeter("monDiskBar", m.disk.percent);
  $("#monDiskSub").textContent = `${fmtGB(m.disk.used_mb)} of ${fmtGB(m.disk.total_mb)}`;

  const g = m.gpu;
  if (!g.ollama_up) {
    $("#monGpuVal").textContent = "engine down";
    setMeter("monGpuBar", 0);
    $("#monGpuSub").textContent = "Ollama is not reachable";
  } else if (!g.loaded_models.length) {
    $("#monGpuVal").textContent = "idle";
    setMeter("monGpuBar", 0);
    $("#monGpuSub").textContent = "no model loaded (loads on first extraction)";
  } else {
    const mod = g.loaded_models[0];
    const pct = mod.size_mb ? (mod.vram_mb / mod.size_mb) * 100 : 0;
    $("#monGpuVal").textContent = fmtGB(mod.vram_mb) + " VRAM";
    setMeter("monGpuBar", pct);
    $("#monGpuSub").textContent =
      `${mod.name} — ${pct.toFixed(0)}% of model in GPU memory (${fmtGB(mod.size_mb)} total)`;
  }

  setSvc("svcDb", "database", m.services.database, m.services.database === "ok");
  setSvc("svcOllama", "ollama", m.services.ollama, m.services.ollama === "ok");
  setSvc("svcModel", "model", m.services.model, m.services.model === "ready");
  renderMonitorErrors(m.errors);

  $("#monActive").textContent = m.activity.active_users_5m;
  $("#monTotalUsers").textContent = m.activity.total_users;
  $("#monJobsRunning").textContent = m.activity.jobs_running;
  $("#monJobsQueued").textContent = m.activity.jobs_queued;
  $("#monUpdated").textContent = "updated " + new Date().toLocaleTimeString();
}

/* ---------------- auth ---------------- */
let authMode = "login"; // or "register"
let statusTimer = null;

function setAuthMode(mode) {
  authMode = mode;
  const isLogin = mode === "login";
  $("#authSubtitle").textContent = isLogin ? "Sign in to your account" : "Create a new account";
  $("#authSubmit").textContent = isLogin ? "Sign in" : "Create account";
  $("#authSwitchText").textContent = isLogin ? "New here?" : "Already have an account?";
  $("#authToggle").textContent = isLogin ? "Create an account" : "Sign in";
  $("#authPass").setAttribute("autocomplete", isLogin ? "current-password" : "new-password");
  $("#authError").textContent = "";
}
$("#authToggle").addEventListener("click", () => setAuthMode(authMode === "login" ? "register" : "login"));

$("#authForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("#authUser").value.trim();
  const password = $("#authPass").value;
  $("#authError").textContent = "";
  $("#authSubmit").disabled = true;
  try {
    const r = await fetch("/api/" + (authMode === "login" ? "login" : "register"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(j.detail || "Something went wrong.");
    }
    const user = await r.json();
    await enterApp(user);
  } catch (err) {
    $("#authError").textContent = err.message;
  } finally {
    $("#authSubmit").disabled = false;
  }
});

$("#logoutBtn").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  if (statusTimer) clearInterval(statusTimer);
  location.reload();
});

async function enterApp(user) {
  state.user = user;
  $("#userName").textContent = user.username;
  $("#userArea").classList.remove("hidden");
  $("#adminTab").classList.toggle("hidden", !user.is_admin);
  $("#monitorTab").classList.toggle("hidden", !user.is_admin);
  $("#authGate").classList.add("hidden");
  $("#authUser").value = "";
  $("#authPass").value = "";

  await Promise.all([loadUploads(), loadTemplates()]);
  loadStatus();
  if (!statusTimer) statusTimer = setInterval(loadStatus, 8000);
}

/* ---------------- boot ---------------- */
(async function boot() {
  try {
    const r = await fetch("/api/me");
    if (r.ok) {
      await enterApp(await r.json());
      return;
    }
  } catch {}
  try {
    const cfg = await fetch("/api/auth-config").then((r) => r.json());
    state.allowRegistration = !!cfg.allow_registration;
  } catch {}
  // Invite-only deployments hide the "Create an account" switch entirely.
  $(".auth-switch").classList.toggle("hidden", !state.allowRegistration);
  setAuthMode("login");
  $("#authGate").classList.remove("hidden");
  $("#authUser").focus();
})();
