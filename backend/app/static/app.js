const RU = {
  on_track: "в графике", warning: "отклонение", critical: "критично", unknown: "нет данных",
  active: "идёт", past: "завершён", future: "план",
  dump_truck: "Самосвал", excavator: "Экскаватор", roller: "Каток", manipulator_crane: "Кран-манипулятор",
  concrete_mixer: "Бетоносмеситель", bulldozer: "Бульдозер", truck: "Грузовик", mobile_crane: "Автокран",
  coverage: "Покрытие", signature: "Отпечаток", role_fit: "Профиль", safety: "Safety", activity: "Активность",
};

const state = {
  cameraId: "CAM-01", snap: null, cameras: [], samples: [], schedule: [],
  dash: null, history: [], guide: null, criteria: null, busy: false,
};

const $ = (id) => document.getElementById(id);
const json = (u, opt) => fetch(u, opt).then(async (r) => {
  if (!r.ok) throw new Error(await r.text());
  return r.json();
});

document.querySelectorAll("[data-tab]").forEach((btn) => {
  btn.onclick = () => {
    const tab = btn.dataset.tab;
    const view = btn.dataset.view || "brief";
    setView(view, tab);
  };
});

document.querySelectorAll(".modes [data-view]").forEach((btn) => {
  btn.onclick = () => setView(
    btn.dataset.view,
    btn.dataset.view === "setup" ? "cameras" : btn.dataset.view === "notes" ? "notes" : "live",
  );
});

function setView(view, tab) {
  document.querySelectorAll(".rail [data-view]").forEach((b) => {
    const match = b.dataset.view === view && (!tab || !b.dataset.tab || b.dataset.tab === tab || view === "map" || view === "notes");
    b.classList.toggle("active", match);
  });
  if (view === "map") {
    document.querySelectorAll(".rail [data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === "map"));
  }
  if (view === "notes") {
    document.querySelectorAll(".rail [data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === "notes"));
  }
  document.querySelectorAll(".modes [data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("sheet")?.classList.toggle("hidden", view === "map" || view === "notes");
  $("notes-layer")?.classList.toggle("hidden", view !== "notes");
  ["live", "schedule", "cameras", "history"].forEach((id) => $(id)?.classList.toggle("hidden", id !== tab));
  $("kpis")?.classList.toggle("hidden", tab !== "live" || view === "map" || view === "notes");
  if (window.StroyTwin) window.StroyTwin.pauseTwin(view === "notes");
  if (window.StroyNotes) window.StroyNotes.pauseNotes(view !== "notes");
  if (view === "notes") {
    window.__initNotes?.();
    window.StroyNotes?.refreshNotes?.();
  }
}

function tickClock() {
  const el = $("hud-clock");
  if (!el) return;
  const d = new Date();
  el.textContent = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
tickClock();
setInterval(tickClock, 15000);

document.querySelectorAll(".tabs [data-dock]").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tabs [data-dock]").forEach((b) => b.classList.toggle("active", b === btn));
  };
});
document.querySelectorAll("#unit-strip .unit").forEach((btn) => {
  btn.onclick = () => {
    const id = btn.dataset.pick || btn.querySelector("b")?.textContent;
    if (window.StroyTwin?.selectPick) window.StroyTwin.selectPick(id);
    else if (id && $("unit-id")) $("unit-id").textContent = id;
  };
});

function badge(s) {
  return `<span class="badge ${s}">${RU[s] || s}</span>`;
}

function renderKpis() {
  const c = state.dash?.status_counts || {};
  const crit = state.snap?.criteria;
  $("kpis").innerHTML = [
    ["Индекс", crit ? `${Math.round((crit.overall || 0) * 100)}%` : "—", crit?.grade || ""],
    ["В графике", c.on_track || 0, "снимков"],
    ["Отклонения", c.warning || 0, ""],
    ["Критика", c.critical || 0, ""],
    ["Архив", state.history.length, "кадров"],
  ].map(([l, v, e]) => `<div class="metric"><span>${l}</span><b>${v} <em>${e || ""}</em></b></div>`).join("");
}

function scorecard(crit) {
  if (!crit) return `<p class="muted">Индекс появится после анализа снимка. 3D-модель эталона уже на экране.</p>`;
  const keys = ["coverage", "signature", "role_fit", "safety", "activity"];
  return keys.map((k) => {
    const v = Math.round((crit[k] || 0) * 100);
    return `<div class="score-row"><span>${RU[k] || k}</span><span>${v}%</span></div>
      <div class="bar"><i style="width:${v}%"></i></div>`;
  }).join("") + `<p class="muted" style="margin-top:10px">Итог ${Math.round((crit.overall || 0) * 100)}% · оценка ${crit.grade || "—"} · WBS ${crit.primary_wbs || "—"}</p>`;
}

function renderLive() {
  const snap = state.snap || state.dash?.recent?.[0];
  const cams = state.cameras.map((c) => `
    <button class="list-btn ${state.cameraId === c.id ? "active" : ""}" onclick="selectCam('${c.id}')">
      <b>${c.id}</b><div class="muted">${c.name} · ${c.zone}</div>
    </button>`).join("");
  const samples = state.samples.map((s) => `
    <button class="list-btn" ${state.busy ? "disabled" : ""} onclick="runSample('${s.id}')">
      <b>${s.title}</b><div class="muted">${s.camera_id} · ${s.note}</div>
    </button>`).join("");
  const img = snap?.annotated_url || snap?.original_url;
  const stages = (snap?.active_stages || []).map((s) => `
    <div class="block-row"><div class="wbs">${s.wbs}${s.leaf ? " · leaf" : ""}</div>
    <b>${s.name}</b><div class="muted">${s.start_date} — ${s.end_date} · Jaccard ${s.score}</div></div>`).join("")
    || `<p class="muted">Нет активного этапа на дату снимка.</p>`;
  const alerts = (snap?.deviations || []).map((d) => `
    <div class="alert ${d.severity}"><h4>${badge(d.severity)} ${d.title}</h4><p>${d.explanation}</p></div>`).join("");
  $("live").innerHTML = `
    <aside class="panel">
      <h2>Источники</h2>
      ${cams}
      <div class="drop">
        <div class="muted">Снимок для анализа</div>
        <input type="file" accept="image/*" onchange="upload(this.files[0])" style="margin-top:10px;color:#8b95a5" />
      </div>
      <h3>Сценарии</h3>${samples}
      <p class="err" id="err"></p>
    </aside>
    <section class="panel">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <h2>Кадр</h2>${snap ? badge(snap.site_status) : ""}
      </div>
      <div class="preview">${img ? `<img src="${img}" alt="кадр">` : `<p class="muted" style="padding:24px">Эталон 3D уже загружен сверху. Добавьте кадр — модель обновится.</p>`}</div>
      ${snap ? `<p class="muted" style="margin-top:10px">${snap.summary}</p>
        <div class="chips">${Object.entries(snap.detected_counts || {}).map(([k, n]) => `<span class="chip">${RU[k] || k}: ${n}</span>`).join("")}
        <span class="chip">${snap.detector_backend}</span></div>` : ""}
    </section>
    <aside class="panel">
      <h2>Критерии</h2>
      ${scorecard(snap?.criteria)}
      <h3 style="margin-top:16px">Связь с графиком</h3>${stages}
      <h3 style="margin-top:16px">Предупреждения</h3>${alerts || `<p class="muted">Нет предупреждений.</p>`}
    </aside>`;
}

function renderSchedule() {
  const metrics = (state.criteria?.metrics || []).map((m) => `
    <div class="block-row"><b>${m.name} · ${Math.round(m.weight * 100)}%</b><p class="muted">${m.text}</p></div>`).join("");
  $("schedule").innerHTML = `<div class="board" style="padding:0">
    <div class="panel" style="grid-column:1/-1">
      <h2>Календарный график</h2>
      <table><thead><tr><th>WBS</th><th>Этап</th><th>Зона</th><th>Сроки</th><th>Статус</th><th>Обязательно</th><th>Запрещено</th></tr></thead>
      <tbody>${state.schedule.map((s) => `<tr>
        <td class="wbs">${s.wbs}</td><td>${s.name}</td><td>${s.zone}</td>
        <td>${s.start_date} — ${s.end_date}</td><td>${badge(s.time_status)}</td>
        <td>${(s.required_equipment || []).map((c) => RU[c] || c).join(", ")}</td>
        <td>${(s.forbidden_equipment || []).map((c) => RU[c] || c).join(", ")}</td>
      </tr>`).join("")}</tbody></table>
    </div>
    <div class="panel" style="grid-column:1/-1"><h2>Как считается индекс</h2>${metrics}</div>
  </div>`;
}

function renderCameras() {
  const cams = state.cameras.map((c) => `<div class="block-row"><b>${c.id} — ${c.name}</b>
    <div class="muted">${c.view}</div>
    <div class="chips"><span class="chip">${c.zone}</span><span class="chip">${c.height_m} м / ${c.angle_deg}°</span>
    ${(c.linked_wbs || []).map((w) => `<span class="chip">${w}</span>`).join("")}</div>
    <p class="muted">${c.recommendations}</p></div>`).join("");
  const guide = (state.guide?.principles || []).map((p) => `<div class="block-row"><b>${p.title}</b><p class="muted">${p.text}</p></div>`).join("");
  $("cameras").innerHTML = `<div class="board" style="padding:0;grid-template-columns:1fr 1fr">
    <div class="panel"><h2>Камеры</h2>${cams}</div>
    <div class="panel"><h2>Установка</h2>${guide}</div></div>`;
}

function renderHistory() {
  $("history").innerHTML = `<div class="panel"><h2>История</h2>
    <table><thead><tr><th>ID</th><th>Камера</th><th>Время</th><th>Статус</th><th>Индекс</th></tr></thead>
    <tbody>${state.history.map((s) => `<tr>
      <td>${s.id}</td><td>${s.camera_id}</td><td>${(s.captured_at || "").replace("T", " ").slice(0, 19)}</td>
      <td>${badge(s.site_status)}</td><td>${Math.round((s.match_score || 0) * 100)}%</td>
    </tr>`).join("")}</tbody></table></div>`;
}

window.selectCam = (id) => { state.cameraId = id; renderLive(); };

window.runSample = async (id) => {
  state.busy = true;
  try {
    const data = await json("/api/demo/run/" + id, { method: "POST" });
    state.snap = data.snapshot;
    await rebuildTwinFromSnap(data.snapshot.id);
    await reload();
  } catch (e) {
    const el = $("err"); if (el) el.textContent = e.message;
  } finally { state.busy = false; }
};

window.upload = async (file) => {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("camera_id", state.cameraId);
  try {
    const data = await json("/api/analyze", { method: "POST", body: fd });
    state.snap = data.snapshot;
    await rebuildTwinFromSnap(data.snapshot.id);
    await reload();
  } catch (e) { const el = $("err"); if (el) el.textContent = e.message; }
};

window.rebuildFromHistory = async () => {
  setBusy(true);
  try {
    const twin = await json("/api/twin/from-history", { method: "POST" });
    window.StroyTwin?.applyScene(twin);
    $("twin-grade").textContent = state.snap?.criteria?.grade || "3D";
  } catch (e) { alert(e.message); }
  setBusy(false);
};

window.resetTwin = async () => {
  const twin = await json("/api/twin/reset", { method: "POST" });
  window.StroyTwin?.applyScene(twin);
};

window.uploadTwin = async (files) => {
  if (!files?.length) return;
  setBusy(true);
  const fd = new FormData();
  [...files].forEach((f) => fd.append("files", f));
  fd.append("camera_id", state.cameraId);
  try {
    const twin = await json("/api/twin/reconstruct", { method: "POST", body: fd });
    window.StroyTwin?.applyScene(twin);
  } catch (e) { alert(e.message); }
  setBusy(false);
};

async function rebuildTwinFromSnap(id) {
  try {
    const twin = await json("/api/twin/from-snapshot/" + id, { method: "POST" });
    window.StroyTwin?.applyScene(twin);
    if (twin.snapshot) state.snap = twin.snapshot;
  } catch { /* twin is optional relative to analysis */ }
}

function setBusy(v) {
  state.busy = v;
  document.querySelectorAll(".btn, .hud-btn").forEach((b) => { b.disabled = v; });
}

async function reload() {
  const [schedule, cameras, samples, dash, history, guide, criteria] = await Promise.all([
    json("/api/schedule"), json("/api/cameras"), json("/api/demo/samples"),
    json("/api/dashboard"), json("/api/snapshots"), json("/api/camera-guide"), json("/api/criteria"),
  ]);
  Object.assign(state, { schedule, cameras, samples, dash, history, guide, criteria });
  renderKpis(); renderLive(); renderSchedule(); renderCameras(); renderHistory();
  const g = $("twin-grade");
  if (g && state.snap?.criteria?.grade) g.textContent = state.snap.criteria.grade;
}

reload().catch((e) => { $("live").innerHTML = `<p class="err">${e.message}</p>`; });

document.querySelectorAll(".rail [data-view='notes']").forEach((btn) => {
  btn.onclick = () => setView("notes");
});

const authorEl = $("note-author");
if (authorEl) authorEl.value = localStorage.getItem("stroysync-author") || "";
$("notes-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const author = $("note-author")?.value.trim() || "crew";
  localStorage.setItem("stroysync-author", author);
  const title = $("note-name")?.value.trim();
  const body = $("note-body")?.value.trim();
  if (!title || !body) return;
  setBusy(true);
  try {
    const out = await json("/api/notes", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, body, author }),
    });
    $("note-name").value = "";
    $("note-body").value = "";
    await window.StroyNotes?.refreshNotes();
    if (out.note?.path) window.StroyNotes?.openNote(out.note.path);
  } catch (err) { alert(err.message); }
  setBusy(false);
});
$("note-ai")?.addEventListener("click", async () => {
  setBusy(true);
  try {
    const out = await json("/api/notes/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ units: ["CRN-A-MSK", "BLD-A-MSK", "BLD-C-MSK"] }),
    });
    await window.StroyNotes?.refreshNotes();
    if (out.note?.path) window.StroyNotes?.openNote(out.note.path);
  } catch (err) { alert(err.message); }
  setBusy(false);
});
