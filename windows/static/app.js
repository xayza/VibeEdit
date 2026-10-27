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
  const revEl = $("projectRev");
  if (revEl) revEl.textContent = "Edited rev " + (project.rev ?? 0);
  $("durationLabel").textContent = data.duration_seconds.toFixed(2) + "s";
  $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
  $("timelineText").textContent = data.timeline;
  $("btnUndo").disabled = !data.can_undo;
  $("btnRedo").disabled = !data.can_redo;
  if (data.last_export) {
    $("preview").src = "/api/preview?" + Date.now();
    $("previewLabel").textContent = "Preview: latest export.";
  }
  renderMedia(); renderTracks(); renderInspector(); renderTransitions(); renderVoiceover();
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
  const vm = $("voiceMedia");
  if (vm) vm.innerHTML = project.media.map((m) =>
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
  const totalSecs = Math.max(project.tracks.flatMap((t) => t.items.map((i) => (i.at + i.dur) / fps())), [1])[0] || 1;
  let rulerHtml = `<div class="playhead" style="left:${(playheadFrame / fps()) * pxPerSec}px"></div>`;
  for (let sec = 0; sec <= Math.ceil(totalSecs); sec++) {
    const mm = Math.floor(sec / 60), ss = String(sec % 60).padStart(2, "0");
    rulerHtml += `<div class="ruler-tick" style="left:${sec * pxPerSec}px">${mm}:${ss}</div>`;
  }
  ruler.innerHTML = rulerHtml +
    ((project.beatGrid && project.beatGrid.beats) || []).map((b) =>
      `<div class="beat-tick" title="beat ${b}s" style="left:${b * pxPerSec}px"></div>`).join("");
  // Original-app track order (display only — project data is unchanged):
  // Captions, Overlay, Main, Adjustment, Background, Dialogue,
  // Voiceover, Music, Sfx. Tracks the project does not have yet are
  // shown as labelled empty rows, never as fake tracks.
  const TRACK_ORDER = ["captions", "overlay", "main", "adjustment", "background", "dialogue", "voiceover", "music", "sfx"];
  const ordered = [...project.tracks].sort((a, b) => {
    const ia = TRACK_ORDER.indexOf(a.role), ib = TRACK_ORDER.indexOf(b.role);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  for (const track of ordered) {
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
      const medium = item.media ? project.media.find((m) => m.id === item.media) : null;
      const baseName = medium ? medium.path.split(/[\\/]/).pop() : "";
      if (track.kind === "text" && item.karaoke && item.karaoke.words && item.karaoke.words.length) {
        // Captions track: one chip per karaoke word (real timings).
        el.innerHTML = "";
        for (const w of item.karaoke.words) {
          const chip = document.createElement("span");
          chip.className = "word-chip";
          chip.textContent = w.text;
          chip.title = `${w.start}s–${w.end}s`;
          el.appendChild(chip);
        }
      } else if (medium) {
        el.textContent = `${baseName} · ${((item.dur / fps())).toFixed(1)}s`;
      } else {
        el.textContent = item.text || item.media || item.id;
      }
      el.title = `${item.id} — ${item.at}..${item.at + item.dur} frames` + (baseName ? ` — ${baseName}` : "");
      if (track.kind === "audio" && item.media) {
        // Real waveform strip: peaks decoded from the actual file.
        // Cached per media id; a failed fetch leaves no strip rather
        // than a fake shape.
        if (!window.__waveCache) window.__waveCache = {};
        const cacheKey = item.media;
        const drawWave = (peaks) => {
          const strip = document.createElement("div");
          strip.className = "wave-strip";
          for (const p of peaks) {
            const bar = document.createElement("span");
            bar.className = "wave-bar";
            bar.style.height = Math.max(2, Math.round(p * 100)) + "%";
            strip.appendChild(bar);
          }
          el.appendChild(strip);
        };
        if (window.__waveCache[cacheKey]) drawWave(window.__waveCache[cacheKey]);
        else fetch(`/api/waveform?media=${encodeURIComponent(item.media)}&buckets=32`)
          .then((r) => r.json()).then((d) => {
            if (d.peaks) { window.__waveCache[cacheKey] = d.peaks; drawWave(d.peaks); }
          }).catch(() => {});
      }
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
  const presentRoles = new Set(project.tracks.map((t) => t.role));
  const standard = [["captions", "Captions", "text"], ["overlay", "Overlay", "video"], ["main", "Main", "video"], ["background", "Background", "video"], ["dialogue", "Dialogue", "audio"], ["voiceover", "Voiceover", "audio"], ["music", "Music", "audio"], ["sfx", "Sfx", "audio"]];
  for (const [role, name, kind] of standard) {
    if (presentRoles.has(role)) continue;
    const row = document.createElement("div");
    row.className = "track-row track-row-empty";
    row.innerHTML = `<div class="track-label">${name}<br><small>${role} · ${kind}</small></div><div class="track-lane empty-lane" style="width:${widthPx}px">Empty — use Add Layer, then move a clip here</div>`;
    wrap.appendChild(row);
  }
}
function renderVoiceover() {
  const list = $("voiceList");
  if (!list) return;
  const takes = [];
  for (const t of project.tracks) {
    if (t.role !== "voiceover") continue;
    for (const it of t.items) takes.push(`${it.id} — ${it.media || it.text || ""} at ${(it.at / fps()).toFixed(2)}s`);
  }
  list.innerHTML = takes.length ? takes.map((x) => `<li>${x}</li>`).join("") : "<li>No voiceover takes yet.</li>";
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

/* CapCut-style shell wiring (redesign): tab switching, rail actions,
   import drop zone, timeline toolbar mirrors, Details focus.
   Fenced like the agent dock: every lookup is guarded, so a missing
   element can never break the editor above. */
(function capcutShell() {
  function activateTab(name) {
    document.querySelectorAll("[data-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll(".tool-panel").forEach((p) => {
      p.hidden = p.dataset.panel !== name;
    });
  }
  document.querySelectorAll("[data-tab]").forEach((b) => {
    b.addEventListener("click", () => activateTab(b.dataset.tab));
  });
  document.querySelectorAll('[data-action="timeline"]').forEach((b) => {
    b.addEventListener("click", () => {
      const tl = document.querySelector(".timeline-wrap");
      if (tl) tl.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.querySelectorAll('[data-action="focus-inspector"]').forEach((b) => {
    b.addEventListener("click", () => {
      const col = document.querySelector(".details-col");
      if (!col) return;
      col.scrollIntoView({ behavior: "smooth", block: "start" });
      col.classList.add("details-flash");
      setTimeout(() => col.classList.remove("details-flash"), 1600);
    });
  });
  // Timeline toolbar mirrors: new buttons click the real actions.
  const mirrors = { tlUndo: "btnUndo", tlRedo: "btnRedo",
                    tlSplit: "btnSplit", tlDelete: "btnDelete" };
  for (const [mirror, real] of Object.entries(mirrors)) {
    const m = document.getElementById(mirror);
    const r = document.getElementById(real);
    if (m && r) m.addEventListener("click", () => r.click());
  }
  const add = document.getElementById("tlAdd");
  if (add) add.addEventListener("click", () => activateTab("media"));
  // Import drop zone: dropping files fills the existing upload input
  // and submits the existing upload form (no new upload path).
  const zone = document.getElementById("importDropzone");
  const input = document.getElementById("uploadFile");
  const form = document.getElementById("uploadForm");
  if (zone && input && form) {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      if (e.dataTransfer && e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        form.requestSubmit();
      }
    });
  }
  activateTab("media");
})();

/* Original-app layout wiring: Voice panel, AGENT chat dock, player
   view controls, and the full timeline toolbar. Every handler below
   either calls a real project API or says plainly that the feature
   is not available yet — nothing here fakes an AI reply, a voice
   clone, a recording, or a waveform. Fenced: guarded lookups only. */
(function originalAppWiring() {
  function agentSay(text) {
    const chat = $("agentChat");
    if (!chat) return;
    const div = document.createElement("div");
    div.className = "msg-agent";
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }
  function agentAsk(text) {
    const chat = $("agentChat");
    if (!chat) return;
    const div = document.createElement("div");
    div.className = "msg-user";
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }
  function focusAgent(prefill) {
    const dock = $("agentDock");
    if (dock) {
      dock.scrollIntoView({ behavior: "smooth", block: "start" });
      dock.classList.add("agent-flash");
      setTimeout(() => dock.classList.remove("agent-flash"), 1600);
    }
    const input = $("agentChatInput");
    if (input) {
      if (prefill) input.value = prefill;
      input.focus();
    }
  }
  const chatForm = $("agentChatForm");
  if (chatForm) chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("agentChatInput");
    const msg = (input.value || "").trim();
    if (!msg) return;
    agentAsk(msg);
    input.value = "";
    const lower = msg.toLowerCase();
    try {
      if (lower === "help" || lower.includes("help")) {
        agentSay("Commands I can really run here: list clips, export, review, stats, undo, redo, workspace, project context. For full AI editing, connect an external agent: python windows\\vibeedit.py mcp <project-folder> (106 MCP tools). I am not a connected LLM, so I do not generate scripts or voices in this panel.");
      } else if (lower.includes("list clip")) {
        const items = [];
        for (const t of project.tracks) for (const it of t.items) items.push(`${t.name}: ${it.text || it.media || it.id} (${(it.at / fps()).toFixed(2)}s)`);
        agentSay(items.length ? `Clips (${items.length}): ${items.join(" | ")}` : "No clips on the timeline yet.");
      } else if (lower.includes("export")) {
        agentSay("Exporting a draft (real export, via the same Export draft action)…");
        doExport("draft");
      } else if (lower.includes("review")) {
        const r = $("btnReview"); if (r) r.click();
        agentSay("Review refreshed — see the Review panel in the AI tab for validation, stats and skipped items.");
      } else if (lower.includes("stats") || lower.includes("project context")) {
        const data = await api("/api/project", { op: "project_stats" });
        const st = data.result;
        agentSay(`Project context: ${st.name}, rev ${st.rev}, ${st.tracks} tracks, ${st.items} items, ${st.clips} clips, ${st.duration_seconds}s.`);
      } else if (lower.includes("workspace")) {
        agentSay(`Workspace: project "${project.name}", rev ${project.rev ?? 0}, ${project.format.width}x${project.format.height}, ${project.tracks.length} tracks. Open project folder via the server project path shown in the console.`);
      } else if (lower === "undo") {
        const b = $("btnUndo"); if (b) b.click();
        agentSay("Undo requested.");
      } else if (lower === "redo") {
        const b = $("btnRedo"); if (b) b.click();
        agentSay("Redo requested.");
      } else {
        agentSay("I cannot do that with an LLM in this app yet — no provider is connected here. Try: help, list clips, export, review, stats, undo, redo. For AI generation, connect an external agent: python windows\\vibeedit.py mcp <project-folder>.");
      }
    } catch (err) { agentSay("Command failed: " + err.message); }
  });
  const provider = $("agentProvider");
  if (provider) provider.addEventListener("change", () => {
    if (provider.value === "ollama") agentSay("Ollama is not connected in this app yet — no endpoint is configured, so I cannot generate with it. The External agent (MCP) option is the working route.");
  });
  function agentBtn(id, fn) {
    const b = $(id); if (b) b.addEventListener("click", fn);
  }
  agentBtn("btnAgentWorkspace", () => agentSay(`Workspace: project "${project.name}", rev ${project.rev ?? 0}, ${project.format.width}x${project.format.height}, ${project.tracks.length} tracks.`));
  agentBtn("btnAgentContext", async () => {
    try {
      const data = await api("/api/project", { op: "project_stats" });
      const st = data.result;
      agentSay(`Project context: ${st.name}, rev ${st.rev}, ${st.tracks} tracks, ${st.items} items, ${st.clips} clips, ${st.duration_seconds}s.`);
    } catch (err) { agentSay("Project context failed: " + err.message); }
  });
  agentBtn("btnAgentSurvey", () => { const r = $("btnReview"); if (r) r.click(); agentSay("Survey = Review refreshed — see the Review panel in the AI tab."); });
  agentBtn("btnAgentWriteVO", () => agentSay("Write VO (AI script writing) is not available in-app yet. Use the Voice panel to import voiceover audio, or an external agent via MCP to draft lines."));
  agentBtn("btnAgentReview", () => { const r = $("btnReview"); if (r) r.click(); agentSay("Review refreshed — see the Review panel in the AI tab."); });
  document.querySelectorAll('[data-action="focus-agent"]').forEach((b) => b.addEventListener("click", () => focusAgent("")));

  // Voice panel (real import + place; generation/cloning/recording honest notes)
  const vForm = $("voiceoverForm");
  if (vForm) vForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      let track = project.tracks.find((t) => t.role === "voiceover");
      if (!track) {
        const d = await api("/api/project", { op: "add_track", kind: "audio", role: "voiceover", name: "Voiceover" });
        track = d.result;
      }
      await api("/api/project", { op: "add_clip", media: $("voiceMedia").value, track: track.id, at: Number($("voiceAt").value), dur: null });
      $("voiceResult").textContent = "Voiceover take added to the Voiceover track.";
      setStatus("Voiceover take added."); await load();
    } catch (err) { $("voiceResult").textContent = "Voiceover take failed: " + err.message; setStatus(err.message, true); }
  });
  const cloneBtn = $("btnVoiceClone");
  if (cloneBtn) cloneBtn.addEventListener("click", async () => {
    const file = $("voiceRefFile") && $("voiceRefFile").files[0];
    if (!file) { $("voiceResult").textContent = "Choose a reference audio file first. Note: voice cloning is not available in this Windows port yet."; return; }
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch("/api/media/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) { $("voiceResult").textContent = "Upload failed: " + data.error; return; }
    $("voiceResult").textContent = "Reference audio imported as media (" + data.media.path + "). Voice cloning is not available yet — place it on the Voiceover track with the form below.";
    setStatus("Reference audio imported."); await load();
  });
  const genBtn = $("btnVoiceGenerate");
  if (genBtn) genBtn.addEventListener("click", () => {
    $("voiceResult").textContent = "Voice generation is not available in this Windows port yet — no voice provider is connected. Import audio and place it on the Voiceover track instead.";
  });

  // Player view controls (real display controls; Compare is honestly unavailable)
  const tabTl = $("playerTabTimeline"), tabSrc = $("playerTabSource"), note = $("playerSourceNote"), wrap = document.querySelector(".preview-wrap");
  if (tabTl) tabTl.addEventListener("click", () => {
    tabTl.classList.add("active"); if (tabSrc) tabSrc.classList.remove("active");
    if (wrap) wrap.hidden = false; if (note) note.hidden = true;
  });
  if (tabSrc) tabSrc.addEventListener("click", () => {
    tabSrc.classList.add("active"); if (tabTl) tabTl.classList.remove("active");
    if (wrap) wrap.hidden = true; if (note) note.hidden = false;
  });
  const fitBtn = $("btnPreviewFit");
  if (fitBtn && wrap) fitBtn.addEventListener("click", () => { wrap.classList.toggle("fit-contain"); setStatus(wrap.classList.contains("fit-contain") ? "Preview fit: contain." : "Preview fit: default."); });
  const safeBtn = $("btnPreviewSafe"), safe = $("safeAreaOverlay");
  if (safeBtn && safe) safeBtn.addEventListener("click", () => { safe.hidden = !safe.hidden; setStatus(safe.hidden ? "Safe-area guide hidden." : "Safe-area guide shown (display guide only, not a render setting)."); });
  const cmpBtn = $("btnPreviewCompare");
  if (cmpBtn) cmpBtn.addEventListener("click", () => setStatus("Compare view is not available yet — the preview shows the latest export only.", true));
  const playBtn = $("btnPreviewPlay"), backBtn = $("btnPreviewBack");
  if (playBtn) playBtn.addEventListener("click", () => {
    const v = $("preview"); if (!v || !v.src) { setStatus("No preview yet — export a draft first.", true); return; }
    if (v.paused) v.play(); else v.pause();
  });
  if (backBtn) backBtn.addEventListener("click", () => {
    const v = $("preview"); if (v) { v.currentTime = 0; playheadFrame = 0; renderTracks(); }
  });

  // Timeline toolbar: Add Layer, Sections, Ask agent, Export report
  const layerBtn = $("tlAddLayer");
  if (layerBtn) layerBtn.addEventListener("click", async () => {
    const n = project.tracks.filter((t) => t.kind === "video").length + 1;
    try { await api("/api/project", { op: "add_track", kind: "video", role: "overlay", name: "Layer " + n }); setStatus("Layer added."); await load(); }
    catch (err) { setStatus(err.message, true); }
  });
  const secBtn = $("tlSections");
  if (secBtn) secBtn.addEventListener("click", () => {
    const ms = project.markers || [];
    setStatus(ms.length ? "Sections (markers): " + ms.map((m) => `${(m.at / fps()).toFixed(2)}s ${m.text}`).join(" | ") : "No sections (markers) yet — markers can be added via the MCP tools (vibeedit_markers_add).");
  });
  const askBtn = $("tlAskAgent");
  if (askBtn) askBtn.addEventListener("click", () => focusAgent(selectedId ? "Help with the selected clip" : "Help with this project"));
  const reportBtn = $("btnExportReport");
  if (reportBtn) reportBtn.addEventListener("click", () => {
    const tab = document.querySelector('[data-tab="ai"]'); if (tab) tab.click();
    const r = $("btnReview"); if (r) r.click();
    setStatus("Export report refreshed (Review panel).");
  });
})();
