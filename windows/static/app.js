/* VibeEdit Windows MVP web UI — CapCut-style: preview top, editor
   panel, multi-track timeline strip at the bottom. Preview plays the
   latest export only (Phase 1 limit); dragging a clip saves once on
   drop, and the server rejects overlaps. */
let project = null, selectedId = null, playheadFrame = 0, pxPerSec = 60;

const $ = (id) => document.getElementById(id);
function fps() {
  const f = project.format.fps;
  return Array.isArray(f) ? f[0] / f[1] : f;
}
function setStatus(msg, isError) {
  const el = $("status");
  el.textContent = msg;
  el.style.color = isError ? "#c96f68" : "#b8b1a6";
}
async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
function findItem(id) {
  for (const t of project.tracks)
    for (const it of t.items)
      if (it.id === id) return { track: t, item: it };
  return null;
}

async function load() {
  const data = await api("/api/project");
  project = data.project;
  $("projectName").value = project.name || "";
  $("durationLabel").textContent = data.duration_seconds.toFixed(2) + "s";
  $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
  $("timelineText").textContent = data.timeline;
  $("btnUndo").disabled = !data.can_undo;
  $("btnRedo").disabled = !data.can_redo;
  if (data.last_export) {
    $("preview").src = "/api/preview?" + Date.now();
    $("previewLabel").textContent = "Preview: latest export.";
  }
  renderMedia(); renderTracks(); renderInspector();
}
function renderMedia() {
  $("mediaList").innerHTML = project.media.map((m) =>
    `<li>${m.id} — ${m.path} (${m.kind || "?"})</li>`).join("") || "<li>No media yet.</li>";
  $("addMedia").innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  $("addTrack").innerHTML = project.tracks.filter((t) => t.kind === "video").map((t) =>
    `<option value="${t.id}">${t.name} (${t.role})</option>`).join("");
  $("inspTrack").innerHTML = project.tracks.map((t) =>
    `<option value="${t.id}">${t.name} (${t.role})</option>`).join("");
}
function renderTracks() {
  const wrap = $("tracks");
  wrap.innerHTML = "";
  const totalS = Math.max(project.tracks.flatMap((t) => t.items.map((i) => (i.at + i.dur) / fps())), [1])[0] || 1;
  const widthPx = Math.max(totalS * pxPerSec, 400);
  const ruler = $("ruler");
  ruler.style.width = widthPx + "px";
  ruler.innerHTML = `<div class="playhead" style="left:${(playheadFrame / fps()) * pxPerSec}px"></div>`;
  for (const track of project.tracks) {
    const row = document.createElement("div");
    row.className = "track-row";
    row.innerHTML = `<div class="track-label">${track.name}<br><small>${track.role} · ${track.kind}</small></div>`;
    const lane = document.createElement("div");
    lane.className = "track-lane";
    lane.style.width = widthPx + "px";
    lane.dataset.track = track.id;
    lane.addEventListener("dragover", (e) => { e.preventDefault(); lane.classList.add("target"); });
    lane.addEventListener("dragleave", () => lane.classList.remove("target"));
    lane.addEventListener("drop", async (e) => {
      e.preventDefault(); lane.classList.remove("target");
      const rect = lane.getBoundingClientRect();
      const at = Math.max(0, Math.round(((e.clientX - rect.left) / pxPerSec) * fps()));
      try { await api("/api/project", { op: "move", item: selectedId, track: track.id, at }); await load(); }
      catch (err) { setStatus("Move rejected: " + err.message, true); await load(); }
    });
    for (const item of track.items) {
      const el = document.createElement("div");
      el.className = `clip ${track.kind} ${item.id === selectedId ? "selected" : ""}`;
      el.style.left = (item.at / fps()) * pxPerSec + "px";
      el.style.width = Math.max((item.dur / fps()) * pxPerSec - 2, 24) + "px";
      el.textContent = item.text || item.media || item.id;
      el.title = `${item.id} — ${item.at}..${item.at + item.dur} frames`;
      el.draggable = true;
      el.addEventListener("click", () => { selectedId = item.id; renderTracks(); renderInspector(); });
      el.addEventListener("dragstart", () => { selectedId = item.id; });
      lane.appendChild(el);
    }
    row.appendChild(lane);
    wrap.appendChild(row);
  }
}
function renderInspector() {
  const found = selectedId ? findItem(selectedId) : null;
  $("inspectorEmpty").hidden = !!found;
  $("inspectorForm").hidden = !found;
  if (!found) return;
  const { track, item } = found;
  $("inspId").value = item.id;
  $("inspTrack").value = track.id;
  $("inspAt").value = item.at;
  $("inspDur").value = item.dur;
  $("inspSpeed").value = item.speed || 1;
  $("inspFadeIn").value = item.fadeIn || 0;
  $("inspFadeOut").value = item.fadeOut || 0;
  $("inspVolume").value = item.volume || 0;
  $("inspText").value = item.text || "";
}

$("ruler").addEventListener("click", (e) => {
  const rect = $("ruler").getBoundingClientRect();
  playheadFrame = Math.max(0, Math.round(((e.clientX - rect.left) / pxPerSec) * fps()));
  $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
  const video = $("preview");
  if (video.src && !isNaN(video.duration)) video.currentTime = Math.min(playheadFrame / fps(), video.duration);
  renderTracks();
});
$("zoom").addEventListener("input", (e) => {
  pxPerSec = Number(e.target.value);
  $("zoomLabel").textContent = pxPerSec + " px/s";
  renderTracks();
});
$("projectName").addEventListener("change", async (e) => {
  try { await api("/api/project", { op: "set_project", name: e.target.value }); setStatus("Project renamed."); await load(); }
  catch (err) { setStatus(err.message, true); }
});
$("btnUndo").addEventListener("click", async () => { try { await api("/api/undo", {}); await load(); } catch (e) { setStatus(e.message, true); } });
$("btnRedo").addEventListener("click", async () => { try { await api("/api/redo", {}); await load(); } catch (e) { setStatus(e.message, true); } });
async function doExport(preset) {
  setStatus("Exporting (" + preset + ")… this can take a while.");
  try {
    const data = await api("/api/export", { preset });
    setStatus(`Export done: ${data.report.output} (${data.report.duration}s, ${data.report.width}x${data.report.height}).`);
    await load();
  } catch (err) { setStatus("Export failed: " + err.message, true); }
}
$("btnExportDraft").addEventListener("click", () => doExport("draft"));
$("btnExportFull").addEventListener("click", () => doExport("full"));
$("addClipForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "add_clip", media: $("addMedia").value, track: $("addTrack").value,
      at: Number($("addAt").value), in: Number($("addIn").value),
      dur: $("addDur").value ? Number($("addDur").value) : null, speed: Number($("addSpeed").value) });
    setStatus("Clip added."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("addTextForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "add_text", track: "t1", text: $("addText").value,
      at: Number($("addTextAt").value), dur: Number($("addTextDur").value) });
    setStatus("Text added."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("inspectorForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "move", item: $("inspId").value, track: $("inspTrack").value, at: Number($("inspAt").value) });
    if ($("inspSpeed").value) await api("/api/project", { op: "set_speed", item: $("inspId").value, speed: Number($("inspSpeed").value) });
    await api("/api/project", { op: "set_fade", item: $("inspId").value, fadeIn: Number($("inspFadeIn").value), fadeOut: Number($("inspFadeOut").value) });
    if ($("inspText").value) await api("/api/project", { op: "set_text", item: $("inspId").value, text: $("inspText").value });
    await api("/api/project", { op: "set_volume", item: $("inspId").value, volume: Number($("inspVolume").value) });
    setStatus("Clip updated."); await load();
  } catch (err) { setStatus(err.message, true); }
});
async function splitAtPlayhead() {
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Select a clip first.", true); return; }
  try {
    await api("/api/project", { op: "split", item: found.item.id, atFrame: playheadFrame });
    setStatus("Split done."); await load();
  } catch (err) { setStatus(err.message, true); }
}
$("btnSplit").addEventListener("click", splitAtPlayhead);
$("btnPlayheadSplit").addEventListener("click", splitAtPlayhead);
$("btnDelete").addEventListener("click", async () => {
  if (!selectedId) return;
  try { await api("/api/project", { op: "delete", item: selectedId }); selectedId = null; await load(); }
  catch (err) { setStatus(err.message, true); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "s" || e.key === "S") {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    splitAtPlayhead();
  }
});
$("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("uploadFile").files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/media/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) setStatus(data.error, true);
  else { setStatus("Uploaded: " + data.media.path); await load(); }
});

load().catch((err) => setStatus("Failed to load project: " + err.message, true));
