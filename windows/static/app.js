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
  renderMedia(); renderTracks(); renderInspector(); renderTransitions();
}
function renderTransitions() {
  const list = $("transitionList");
  const trans = project.transitions || [];
  list.innerHTML = trans.map((t) =>
    `<li>${t.kind} ${t.from} → ${t.to} (${t.duration} frames) <button data-tr="${t.id}" class="danger">Remove</button></li>`).join("") || "<li>No transitions yet.</li>";
  list.querySelectorAll("button[data-tr]").forEach((b) => b.addEventListener("click", async () => {
    try { await api("/api/project", { op: "remove_transition", transition: b.dataset.tr }); setStatus("Transition removed."); await load(); }
    catch (err) { setStatus(err.message, true); }
  }));
}
function renderKeyframes() {
  const box = $("keyframeBox");
  const found = selectedId ? findItem(selectedId) : null;
  box.hidden = !found;
  if (!found) return;
  const kfs = found.item.keyframes || [];
  $("keyframeList").innerHTML = kfs.map((kf, i) => {
    const entries = Object.entries(kf).filter(([k]) => k !== "at").map(([k, v]) => `${k}=${v}`).join(", ");
    return `<li>${(kf.at / fps()).toFixed(2)}s: ${entries} <button data-kf="${i}" class="danger">Delete</button></li>`;
  }).join("") || "<li>No keyframes.</li>";
  $("keyframeList").querySelectorAll("button[data-kf]").forEach((b) => b.addEventListener("click", async () => {
    const rest = kfs.filter((_, i) => String(i) !== b.dataset.kf);
    try { await api("/api/project", { op: "set_keyframes", item: found.item.id, keyframes: rest }); await load(); }
    catch (err) { setStatus(err.message, true); }
  }));
}
function renderMedia() {
  $("mediaList").innerHTML = project.media.map((m) =>
    `<li>${m.id} — ${m.path} (${m.kind || "?"})</li>`).join("") || "<li>No media yet.</li>";
  $("addMedia").innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  $("beatMedia").innerHTML = project.media.map((m) =>
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
  ruler.innerHTML = `<div class="playhead" style="left:${(playheadFrame / fps()) * pxPerSec}px"></div>` +
    ((project.beatGrid && project.beatGrid.beats) || []).map((b) =>
      `<div class="beat-tick" title="beat ${b}s" style="left:${b * pxPerSec}px"></div>`).join("");
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
      el.addEventListener("click", () => { selectedId = item.id; renderTracks(); renderInspector(); renderKeyframes(); });
      el.addEventListener("dragstart", () => { selectedId = item.id; });
      lane.appendChild(el);
    }
    if (track.role === "main") {
      for (const t of (project.transitions || [])) {
        const from = track.items.find((i) => i.id === t.from);
        if (!from) continue;
        const marker = document.createElement("div");
        marker.className = "transition-marker";
        marker.style.left = ((from.at + from.dur) / fps()) * pxPerSec + "px";
        marker.style.width = Math.max((t.duration / fps()) * pxPerSec, 12) + "px";
        marker.textContent = "⇄ " + t.kind;
        marker.title = `${t.kind} (${t.duration} frames)`;
        lane.appendChild(marker);
      }
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
  $("inspLut").value = (item.color && item.color.lut) || "";
  $("inspStrength").value = (item.color && item.color.strength !== undefined) ? item.color.strength : "";
  $("inspPreset").value = (item.color && item.color.preset) || "";
  $("inspPresetStrength").value = (item.color && item.color.preset_strength !== undefined) ? item.color.preset_strength : "";
  renderKeyframes();
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
    const data = await api("/api/export", { preset, normalize: $("exportNormalize") ? $("exportNormalize").checked : false });
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
    if ($("inspLut").value || $("inspPreset").value || $("inspStrength").value !== "" || $("inspPresetStrength").value !== "") await api("/api/project", { op: "set_color", item: $("inspId").value, lut: $("inspLut").value || null, preset: $("inspPreset").value || null, strength: $("inspStrength").value === "" ? null : Number($("inspStrength").value), preset_strength: $("inspPresetStrength").value === "" ? null : Number($("inspPresetStrength").value) });
    setStatus("Clip updated."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("transitionForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Select the clip on the left of the cut first.", true); return; }
  const main = project.tracks.find((t) => t.role === "main");
  const items = [...main.items].sort((a, b) => a.at - b.at);
  const idx = items.findIndex((i) => i.id === found.item.id);
  const next = items[idx + 1];
  if (!next || next.at !== found.item.at + found.item.dur) { setStatus("Selected clip has no directly consecutive next clip on the main track.", true); return; }
  try {
    await api("/api/project", { op: "add_transition", from: found.item.id, to: next.id, kind: $("trKind").value, duration: Number($("trDur").value) });
    setStatus("Transition added."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("keyframeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedId) return;
  try {
    await api("/api/project", { op: "add_keyframe", item: selectedId, at: Number($("kfAt").value), property: $("kfProp").value, value: Number($("kfValue").value) });
    setStatus("Keyframe added."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("srtImportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/project", { op: "srt_import", track: "t1", srt: $("srtText").value });
    setStatus(`Imported ${data.result.length} SRT cues.`); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("btnSrtExport").addEventListener("click", async () => {
  try {
    const data = await api("/api/project", { op: "srt_export", track: "t1" });
    const blob = new Blob([data.srt], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "captions.srt"; a.click();
    setStatus("SRT exported.");
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

/* Phase 5 agent dock: live MCP tool list from /api/mcp-tools. A
   failure here must never break the editor above, so it is fenced
   off from load(). */
async function loadMcpTools() {
  const list = $("mcpTools");
  if (!list) return;
  try {
    const data = await api("/api/mcp-tools");
    $("mcpToolCount").textContent = data.count;
    list.innerHTML = data.tools.map((t) =>
      `<li><code>${t.name}</code> — ${t.description}</li>`).join("");
  } catch (err) {
    $("mcpToolCount").textContent = "?";
    list.innerHTML = `<li>MCP tool list unavailable: ${err.message}</li>`;
  }
}
loadMcpTools();

$("batchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const folders = $("batchFolders").value.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  setStatus("Batch exporting… this can take a while.");
  try {
    const data = await api("/api/batch", { folders, preset: "full", normalize: $("batchNormalize").checked });
    const ok = data.results.filter((r) => r.ok).length;
    $("batchResult").textContent = `Batch done: ${ok}/${data.results.length} succeeded. ` + data.results.map((r) => `${r.project}: ${r.ok ? "OK" : "FAIL " + r.error}`).join(" | ");
    setStatus(`Batch done: ${ok}/${data.results.length} succeeded.`);
  } catch (err) { setStatus("Batch failed: " + err.message, true); }
});
$("otioImportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/otio-import", { otio: $("otioImportPath").value, dest: $("otioImportDest").value, merge: $("otioImportMerge").checked });
    $("phase4Result").textContent = `OTIO imported: ${data.report.clips} clips, ${data.report.transitions} transitions, ${data.report.markers} markers. Missing: ${data.report.missing.join(", ") || "none"}. Warnings: ${data.report.warnings.join("; ") || "none"}.`;
    setStatus("OTIO imported (into the destination folder, not the open project).");
  } catch (err) { setStatus("OTIO import failed: " + err.message, true); }
});
$("karaokeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedId) { setStatus("Select a text item first.", true); return; }
  try {
    await api("/api/project", { op: "karaoke_add", item: selectedId, words: JSON.parse($("karaokeWords").value) });
    setStatus("Karaoke timings added."); await load();
  } catch (err) { setStatus("Karaoke failed: " + err.message, true); }
});
$("btnKaraokeAss").addEventListener("click", async () => {
  try {
    const data = await api("/api/karaoke-ass", {});
    const blob = new Blob([data.ass], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "karaoke.ass"; a.click();
    setStatus(`Karaoke .ass exported: ${data.report.karaoke_items} items.`);
  } catch (err) { setStatus("Karaoke export failed: " + err.message, true); }
});
$("adjustmentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "adjustment_add", at: Number($("adjAt").value), dur: Number($("adjDur").value), preset: $("adjPreset").value || null, lut: $("adjLut").value || null });
    setStatus("Adjustment layer added."); await load();
  } catch (err) { setStatus("Adjustment failed: " + err.message, true); }
});
$("beatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("Detecting beats…");
  try {
    const data = await api("/api/project", { op: "beat_detect", media: $("beatMedia").value });
    setStatus(`Beats detected: ${data.result.beats.length} beats.`); await load();
  } catch (err) { setStatus("Beat detection failed: " + err.message, true); }
});
$("btnBeatsMarkers").addEventListener("click", async () => {
  try { await api("/api/project", { op: "beats_to_markers" }); setStatus("Beats copied to markers."); await load(); }
  catch (err) { setStatus(err.message, true); }
});
$("btnSnap").addEventListener("click", async () => {
  const beats = (project.beatGrid && project.beatGrid.beats) || [];
  if (!beats.length) { setStatus("No beat grid yet — detect beats first.", true); return; }
  const t = playheadFrame / fps();
  const nearest = beats.reduce((a, b) => Math.abs(b - t) < Math.abs(a - t) ? b : a);
  playheadFrame = Math.round(nearest * fps()); renderTracks();
  setStatus(`Playhead snapped to beat at ${nearest}s.`);
});
$("duckingForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "ducking_set", enabled: $("duckEnabled").checked, amount_db: Number($("duckAmount").value) });
    setStatus("Ducking saved."); await load();
  } catch (err) { setStatus("Ducking failed: " + err.message, true); }
});
$("btnOtio").addEventListener("click", async () => {
  try {
    const data = await api("/api/otio", {});
    const blob = new Blob([data.otio], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "timeline.otio"; a.click();
    setStatus(`OTIO exported: ${data.report.tracks} tracks, ${data.report.clips} items.`);
  } catch (err) { setStatus("OTIO failed: " + err.message, true); }
});

/* Phase 8: review panel + transition preview still. Both are fenced
   like the agent dock: a failure here never breaks the editor. */
$("btnReview").addEventListener("click", async () => {
  const box = $("reviewResult");
  try {
    const data = await api("/api/review");
    const v = data.validation;
    const lines = [];
    lines.push(`Validation: ${v.ok ? "OK" : "ISSUES — " + v.errors.join("; ")}`);
    lines.push(`Stats: ${data.stats.items} items, ${data.stats.clips} clips, ${data.stats.transitions} transitions, ${data.stats.markers} markers, ${data.stats.duration_seconds}s.`);
    lines.push(`Last export: ${data.last_export || "none"}`);
    if (data.last_export_report && data.last_export_report.duration !== undefined)
      lines.push(`Last export duration: ${data.last_export_report.duration}s, skipped: ${(data.skipped || []).join(", ") || "none"}, warnings: ${(data.warnings || []).join("; ") || "none"}.`);
    else
      lines.push("No export yet, so there are no skipped items to report.");
    box.textContent = lines.join(" ");
    setStatus("Review refreshed.");
  } catch (err) { box.textContent = "Review failed: " + err.message; setStatus(err.message, true); }
});
$("btnTransitionPreview").addEventListener("click", async () => {
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Select the clip on the left of the cut first.", true); return; }
  const main = project.tracks.find((t) => t.role === "main");
  const items = [...main.items].sort((a, b) => a.at - b.at);
  const idx = items.findIndex((i) => i.id === found.item.id);
  const next = items[idx + 1];
  const trans = (project.transitions || []).find((t) => t.from === found.item.id && next && t.to === next.id);
  if (!trans) { setStatus("No transition after the selected clip yet — add one first.", true); return; }
  setStatus("Rendering transition preview… (draft render of the cut window)");
  try {
    const data = await api("/api/transition-preview", { transition: trans.id });
    const box = $("transitionPreviewBox");
    box.hidden = false;
    $("transitionPreviewImg").src = "/api/transition-preview?transition=" + encodeURIComponent(trans.id) + "&t=" + Date.now();
    $("transitionPreviewLabel").textContent = `${data.preview.kind} at ${data.preview.midpoint_seconds}s (draft ${data.preview.width}x${data.preview.height}).`;
    setStatus("Transition preview ready.");
  } catch (err) { setStatus("Transition preview failed: " + err.message, true); }
});
