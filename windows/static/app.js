/* VibeEdit Windows MVP web UI — CapCut-style: preview top, editor
   panel, multi-track timeline strip at the bottom. Preview plays the
   latest export only (Phase 1 limit); dragging a clip saves once on
   drop, and the server rejects overlaps. */
let project = null, selectedId = null, playheadFrame = 0, pxPerSec = 60;
let previewMode = "export", previewMediaId = null, previewItemId = null, lastExportPath = null;

const $ = (id) => document.getElementById(id);
function fps() {
  const f = project.format.fps;
  return Array.isArray(f) ? f[0] / f[1] : f;
}
let statusTimer = 0;
function setStatus(msg, isError) {
  const el = $("status");
  if (!el) return;
  el.textContent = msg;
  el.style.color = isError ? "#c96f68" : "#b8b1a6";
  // Round 18 step 2: the toast shows while .show is set and hides
  // itself after 4s; the text and error colours are unchanged.
  el.classList.add("show");
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => el.classList.remove("show"), 4000);
}
function setSaveState(state) {
  // Round 19: the persistent save indicator next to Edited rev.
  // "saving" blinks "Đang lưu…"; "saved" shows a green dot +
  // "Đã lưu" ONLY after a real successful /api/save response;
  // "error" clears it (the error status carries the message).
  // Never shows "Đã lưu" without a success response.
  const dot = $("saveDot"), label = $("saveLabel");
  if (!dot || !label) return;
  if (state === "saving") { dot.className = "save-dot saving"; label.textContent = "Đang lưu…"; }
  else if (state === "saved") { dot.className = "save-dot saved"; label.textContent = "Đã lưu"; }
  else { dot.className = "save-dot"; label.textContent = ""; }
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
// Round 19: THE project-op helper, top-level. Previously it lived
// only inside the gapBatch2Wiring IIFE, so every Knowledge/Vision/
// Plugin handler in round3Wiring threw "post is not defined" before
// doing anything (14 dead buttons). One helper, one convention:
// POST /api/project, then reload the project view.
async function post(body) {
  const d = await api("/api/project", body);
  await load();
  return d;
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
  // Round 18 step 3: the preview canvas follows the project format.
  if (project.format) document.documentElement.style.setProperty("--project-aspect", project.format.width + "/" + project.format.height);
  $("projectName").value = project.name || "";
  const revEl = $("projectRev");
  if (revEl) revEl.textContent = "Edited rev " + (project.rev ?? 0);
  $("durationLabel").textContent = data.duration_seconds.toFixed(2) + "s";
  $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
  // Round 18: the status bar under the tracks shows ONE line only
  // (project line + track/clip counts). The full multi-line readout
  // still exists server-side for the MCP timeline_sheet tool and the
  // Inspector; only this display is condensed, nothing is deleted.
  const statusClips = project.tracks.reduce((n, t) => n + t.items.length, 0);
  $("timelineText").textContent =
    data.timeline.split("\n")[0] + ` · ${project.tracks.length} track · ${statusClips} clip`;
  // Round 19: the footer hint is ellipsized (nowrap is test-locked),
  // so the full text lives in the title tooltip.
  $("timelineText").title = $("timelineText").textContent;
  $("btnUndo").disabled = !data.can_undo;
  $("btnRedo").disabled = !data.can_redo;
  syncFormatUI();
  // Round 22: single source of truth for Magnetic — the project
  // view's server-computed "magnetic" field. (The old code fetched
  // magnetic_get here via renderMedia and misread the shape, so
  // the toggle always reset to false; the fetch also planted a
  // junk undo snapshot on every load, breaking undo-after-delete.)
  const mgBtn = $("tlMagnetic");
  if (mgBtn && data.magnetic !== undefined) { mgBtn.setAttribute("aria-pressed", data.magnetic ? "true" : "false"); mgBtn.classList.toggle("active", !!data.magnetic); }
  const expBtn = $("btnPreviewExport");
  if (expBtn) expBtn.disabled = !data.last_export;
  lastExportPath = data.last_export || null;
  if (previewMode !== "source" && data.last_export) {
    $("preview").src = "/api/preview?" + Date.now();
    $("previewImage").hidden = true;
    $("preview").hidden = false;
    $("previewLabel").textContent = "Đang xem: bản xuất gần nhất.";
    $("previewLabel").hidden = false;
  } else if (previewMode !== "source") {
    // Round 19: no export yet — show the first main clip's first
    // frame as a poster via the existing /api/media serving
    // (preload="metadata" shows frame 0), instead of a black box.
    // No new endpoint: /api/media/<id> already serves the file.
    const mainTrack = project.tracks.find((t) => t.role === "main");
    const firstClip = mainTrack && mainTrack.items.length ? mainTrack.items.slice().sort((a, b) => a.at - b.at)[0] : null;
    const medium = firstClip ? project.media.find((m) => m.id === firstClip.media) : null;
    if (medium) {
      $("previewLabel").textContent = `Chưa có bản xuất — đang xem frame đầu của clip đầu tiên (${mediaBaseName(medium)}).`;
      $("previewLabel").hidden = false;
      if (medium.kind === "image" || /\.(png|jpe?g|gif|webp|bmp)$/i.test(medium.path)) {
        $("previewImage").src = "/api/media/" + encodeURIComponent(medium.id);
        $("previewImage").hidden = false; $("preview").hidden = true; $("preview").removeAttribute("src"); $("preview").load();
      } else {
        $("preview").src = "/api/media/" + encodeURIComponent(medium.id);
        $("preview").hidden = false; $("previewImage").hidden = true;
      }
    } else {
      // Round 19: nothing to show — keep only the one empty-state
      // notice (previewEmpty) and hide the second label.
      $("previewLabel").hidden = true;
    }
  }
  updatePreviewEmpty();
  fillSettingsInfo();
  renderMedia(); renderTracks(); renderInspector(); renderTransitions(); renderVoiceover();
  seekPreviewToPlayhead();
}
function renderTransitions() {
  const list = $("transitionList");
  const trans = project.transitions || [];
  list.innerHTML = trans.map((t) =>
    `<li>${t.kind} ${t.from} → ${t.to} (${t.duration} frames) <button data-tr="${t.id}" class="danger">Remove</button></li>`).join("") || "<li>No transitions yet.</li>";
  list.querySelectorAll("button[data-tr]").forEach((b) => b.addEventListener("click", async () => {
    try { await api("/api/project", { op: "remove_transition", transition: b.dataset.tr }); setStatus("Đã xóa transition."); await load(); }
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
function mediaBaseName(m) { return (m.path || "").split(/[\\/]/).pop() || m.id; }
function mediaFps(m) {
  // Round 19: a media record's OWN frame rate, or null when unknown
  // (audio has none). Never defaults to the project fps here: that
  // default is what made source frames read as project frames.
  if (!m || !m.fps) return null;
  if (Array.isArray(m.fps)) return m.fps[1] ? m.fps[0] / m.fps[1] : null;
  const v = Number(m.fps);
  return v > 0 ? v : null;
}
function mediaDurationS(m) {
  if (m.duration) return Number(m.duration);
  // Round 19: source frames divided by SOURCE fps, not project fps.
  if (m.frames) {
    const mf = mediaFps(m);
    return mf ? Number(m.frames) / mf : Number(m.frames) / fps();
  }
  return null;
}
function mediaDurationLabel(m) {
  const s = mediaDurationS(m);
  if (s === null || isNaN(s)) return "—";
  const mm = Math.floor(s / 60), ss = Math.round(s % 60);
  return `${mm}:${String(ss).padStart(2, "0")}`;
}
function mediaDurFrames(m) {
  // Round 19: dur is PROJECT frames everywhere downstream, so a
  // source-frame count must be converted (seconds-first). The old
  // code returned source frames directly, doubling durations
  // whenever media fps != project fps (6797 frames of 59.94fps
  // footage in a 29.97fps project showed as 226.79s).
  if (m.duration) return Math.max(1, Math.round(Number(m.duration) * fps()));
  if (m.frames) {
    const mf = mediaFps(m);
    if (mf) return Math.max(1, Math.round(Number(m.frames) / mf * fps()));
    return Math.max(1, Math.round(Number(m.frames)));
  }
  return null;
}
function mediaIsUsed(m) {
  return project.tracks.some((t) => t.items.some((it) => it.media === m.id));
}
function setMediaStatus(msg, isError) {
  const el = $("mediaAddStatus");
  if (el) { el.textContent = msg; el.style.color = isError ? "#c96f68" : "#b8b1a6"; }
  setStatus(msg, isError);
}
function freePosition(track, durFrames) {
  const items = [...track.items].sort((a, b) => a.at - b.at);
  if (!items.length) return 0;
  const fits = (at) => !items.some((it) => at < it.at + it.dur && at + durFrames > it.at);
  if (fits(playheadFrame)) return playheadFrame;
  return Math.max(...items.map((it) => it.at + it.dur));
}
async function addMediaToTimeline(mediaId) {
  const m = project.media.find((x) => x.id === mediaId);
  if (!m) { setMediaStatus("Không tìm thấy file media này.", true); return; }
  const isAudio = m.kind === "audio";
  const track = isAudio
    ? (project.tracks.find((t) => t.kind === "audio") || null)
    : (project.tracks.find((t) => t.role === "main") || project.tracks.find((t) => t.kind === "video") || null);
  if (!track) { setMediaStatus("Không có track phù hợp cho file này.", true); return; }
  const dur = mediaDurFrames(m);
  if (!dur) { setMediaStatus(`Không thêm được ${mediaBaseName(m)}: file này không có thời lượng ghi nhận, hãy dùng form Thêm clip và nhập Thời lượng thủ công.`, true); return; }
  const at = freePosition(track, dur);
  try {
    const data = await api("/api/project", { op: "add_clip", media: m.id, track: track.id, at, in: 0, dur, speed: 1 });
    await load();
    const newId = data.result && data.result.id;
    if (newId) {
      selectClipAndPreview(newId);
      const tl = document.querySelector(".timeline-wrap");
      const el = document.querySelector(`#tracks .clip.selected`);
      if (tl && el) tl.scrollLeft = Math.max(0, el.offsetLeft - 100);
      setMediaStatus(`Đã thêm ${mediaBaseName(m)} vào timeline (${track.name}) lúc ${(at / fps()).toFixed(2)}s — bấm ▶ để phát.`);
    } else setMediaStatus(`Đã thêm ${mediaBaseName(m)} vào timeline.`);
  } catch (err) { setMediaStatus(`Không thêm được ${mediaBaseName(m)}: ${err.message}`, true); }
}
async function renderMedia() {
  const used = new Set();
  for (const t of project.tracks) for (const it of t.items) if (it.media) used.add(it.media);
  $("mediaList").innerHTML = project.media.map((m) => {
    const name = mediaBaseName(m);
    const dims = (m.width && m.height) ? `${m.width}×${m.height}` : "";
    const durLabel = mediaDurationLabel(m);
    const icon = m.kind === "audio" ? "♪" : (m.kind === "image" ? "🖼" : "🎬");
    const thumb = m.kind === "audio"
      ? `<div class="media-thumb media-thumb-audio" title="Audio — không có thumbnail">♪</div>`
      : `<img class="media-thumb" src="/api/thumbnail/${encodeURIComponent(m.id)}" alt="" loading="lazy" onerror="this.style.display='none'">`;
    return `<li class="media-card" data-media="${m.id}" title="Bấm để xem file này, bấm đúp để thêm vào timeline">${thumb}${durLabel === "—" ? "" : `<span class="media-duration-badge">${durLabel}</span>`}<div class="media-card-body"><div class="media-card-name">${icon} ${name}</div><div class="media-card-meta">${m.kind || "?"} · ${durLabel}${dims ? " · " + dims : ""}</div></div>${used.has(m.id) ? '<span class="media-added-badge">Đã thêm</span>' : ""}<button type="button" class="media-add-btn primary" data-add-media="${m.id}" title="Thêm vào timeline" aria-label="Thêm vào timeline">+</button></li>`;
  }).join("") || "<li>Chưa có media.</li>";
  const mc = $("mediaCount");
  if (mc) mc.textContent = project.media.length ? project.media.length + " file" : "";
  const ct = document.querySelector(".create-tools");
  if (ct) ct.hidden = project.media.length > 0;
  $("mediaList").querySelectorAll(".media-card").forEach((li) => {
    li.addEventListener("click", (e) => { if (!e.target.closest("[data-add-media]")) loadMediaPreview(li.dataset.media); });
    li.addEventListener("dblclick", () => addMediaToTimeline(li.dataset.media));
  });
  $("mediaList").querySelectorAll("[data-add-media]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); addMediaToTimeline(b.dataset.addMedia); }));
  const srcSel = $("sourceMedia");
  if (srcSel) srcSel.innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${mediaBaseName(m)}</option>`).join("");
  if (srcSel && previewMediaId) srcSel.value = previewMediaId;
  $("addMedia").innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  $("beatMedia").innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  const tm = $("transcribeMedia");
  if (tm) tm.innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  const vm = $("voiceMedia");
  if (vm) vm.innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  const vms = $("visionMedia");
  if (vms) vms.innerHTML = project.media.map((m) =>
    `<option value="${m.id}">${m.id} — ${m.path}</option>`).join("");
  // Round 22: no magnetic_get fetch here anymore — load() syncs
  // the toggle from the project view's "magnetic" field (see
  // above). The old fetch misread the response shape (the value
  // lives in result.magnetic, not top-level) AND pushed a junk undo
  // snapshot on every load, which made undo-after-delete need two
  // presses.
  $("addTrack").innerHTML = project.tracks.filter((t) => t.kind === "video").map((t) =>
    `<option value="${t.id}">${t.name} (${t.role})</option>`).join("");
  $("inspTrack").innerHTML = project.tracks.map((t) =>
    `<option value="${t.id}">${t.name} (${t.role})</option>`).join("");
}
// Round 18 timeline restyle: pure helpers, tested in test_round18.py
// via node extraction (no DOM needed).
const TRACK_CODES = { captions: "CC", overlay: "V2", main: "V1", background: "V3", dialogue: "A1", voiceover: "A2", music: "A3", sfx: "A4", adjustment: "FX" };
// Sample-style header: icon row (code + static eye/speaker) above the
// name. The indicators are STATIC spans, never buttons: hide/mute/
// lock do not exist in this port, so nothing here pretends to toggle.
function trackHeaderHtml(role, name, kind) {
  const code = TRACK_CODES[role] || "?";
  const speaker = kind === "audio" ? `<span class="track-ico" title="Track âm thanh">🔊</span>` : "";
  return `<div class="track-label" title="${role} · ${kind}"><span class="track-head-row"><span class="track-code code-${kind}">${code}</span><span class="track-ico" title="Đang hiển thị">👁</span>${speaker}</span><span class="track-name">${name}</span></div>`;
}
// Effect chip label from the clip's OWN stored colour data only:
// preset name, else "LUT" when a LUT file is set, else no chip.
// Sample-photo effect names must never appear here — they are not
// this project's data, so they are deliberately not named.
function effectChipNameForClip(item) {
  const col = (item && item.color) || {};
  if (col.preset && col.preset !== "none") return col.preset;
  if (col.lut) return "LUT";
  return null;
}
// Ruler labels stay readable at any zoom: the smallest step whose
// labels sit at least 64px apart. Positions stay exact multiples of
// the step — the step only thins labels, never moves them.
function rulerLabelStep(pxPerSec) {
  for (const s of [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]) {
    if (s * pxPerSec >= 64) return s;
  }
  return 600;
}
function visibleTickRange(scrollLeft, clientWidth, pxPerSec, totalSecs) {
  // Round 19: pure helper (Node-testable) for ruler virtualization.
  // Returns the second range whose ticks get DOM nodes, plus the
  // minor-tick step: 500ms when ticks are >= 10px apart, else 1s.
  const firstSec = Math.max(0, Math.floor(scrollLeft / pxPerSec));
  const lastSec = Math.min(Math.ceil(totalSecs), Math.ceil((scrollLeft + clientWidth) / pxPerSec) + 1);
  return { firstSec, lastSec, minorStep: pxPerSec >= 20 ? 0.5 : 1 };
}
function renderRuler() {
  // Round 19: virtualized ruler — only ticks in the visible range
  // get DOM nodes. The old loop created one node per second even
  // when labels were sparse, so a 3600s project built ~3601 tick
  // nodes (plus one beat node per beat). Scrolling re-renders only
  // the ruler (rAF-throttled), never the whole track list.
  const ruler = $("ruler");
  if (!ruler) return;
  const totalS = Math.max(1, ...project.tracks.flatMap((t) => t.items.map((i) => (i.at + i.dur) / fps())));
  const widthPx = Math.max(totalS * pxPerSec, 400);
  ruler.style.width = widthPx + "px";
  const labelStep = rulerLabelStep(pxPerSec);
  const stepPx = Math.max(1, labelStep * pxPerSec);
  // Grid lines follow the label step, so the background never
  // disagrees with the seconds at a zoom other than 60 px/s.
  ruler.style.backgroundImage = `repeating-linear-gradient(90deg, transparent 0, transparent ${stepPx - 1}px, rgba(255, 255, 255, 0.06) ${stepPx - 1}px, rgba(255, 255, 255, 0.06) ${stepPx}px)`;
  const scroller = ruler.parentElement;
  const viewLeft = scroller ? scroller.scrollLeft : 0;
  const viewW = scroller ? scroller.clientWidth : widthPx;
  const viewStartS = viewLeft / pxPerSec, viewEndS = (viewLeft + viewW) / pxPerSec;
  const { firstSec, lastSec, minorStep } = visibleTickRange(viewLeft, viewW, pxPerSec, totalS);
  let html = `<div class="playhead" style="left:${(playheadFrame / fps()) * pxPerSec}px"></div>`;
  for (let sec = firstSec; sec <= lastSec; sec++) {
    if (sec % labelStep === 0) {
      const mm = Math.floor(sec / 60), ss = String(sec % 60).padStart(2, "0");
      html += `<div class="ruler-tick" style="left:${sec * pxPerSec}px">${mm}:${ss}</div>`;
    } else {
      html += `<div class="ruler-tick-minor" style="left:${sec * pxPerSec}px"></div>`;
    }
  }
  if (minorStep === 0.5) {
    for (let t = Math.ceil(viewStartS * 2) / 2; t <= Math.min(totalS, viewEndS); t += 0.5) {
      if (Number.isInteger(t)) continue; // whole seconds already have a tick
      html += `<div class="ruler-tick-minor" style="left:${t * pxPerSec}px"></div>`;
    }
  }
  html += ((project.beatGrid && project.beatGrid.beats) || []).filter((b) => b >= viewStartS && b <= viewEndS).map((b) =>
    `<div class="beat-tick" title="beat ${b}s" style="left:${b * pxPerSec}px"></div>`).join("");
  if (window.__showSections) {
    html += (project.markers || []).filter((m) => { const s = m.at / fps(); return s >= viewStartS && s <= viewEndS; }).map((m) =>
      `<div class="section-tick" title="${(m.text || "").replace(/"/g, "&quot;")}" style="left:${(m.at / fps()) * pxPerSec}px"></div>`).join("");
  }
  ruler.innerHTML = html;
  if (scroller && !scroller.dataset.rulerScroll) {
    scroller.dataset.rulerScroll = "1";
    let queued = false;
    scroller.addEventListener("scroll", () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; renderRuler(); });
    }, { passive: true });
  }
}
function renderTracks() {
  const wrap = $("tracks");
  wrap.innerHTML = "";
  const totalS = Math.max(1, ...project.tracks.flatMap((t) => t.items.map((i) => (i.at + i.dur) / fps())));
  const widthPx = Math.max(totalS * pxPerSec, 400);
  const tc = $("tlTimecode");
  const fmtTc = (t) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${(t % 60).toFixed(2).padStart(5, "0")}`;
  if (tc) tc.textContent = `${fmtTc(playheadFrame / fps())} / ${fmtTc(totalS)}`;
  // Round 18 continued: the empty-timeline hint shows only when no
  // track has a clip; it never covers real clips (pointer-events
  // none in CSS, and hidden here as soon as any clip exists).
  const hint = $("timelineEmptyHint");
  if (hint) hint.hidden = project.tracks.some((t) => t.items.length > 0);
  renderRuler();
  // Original-app track order (display only — project data is unchanged):
  // Captions, Overlay, Main, Adjustment, Background, Dialogue,
  // Voiceover, Music, Sfx. Tracks the project does not have yet are
  // shown as labelled empty rows, never as fake tracks.
  const TRACK_ORDER = ["captions", "overlay", "main", "adjustment", "background", "dialogue", "voiceover", "music", "sfx"];
  const ordered = [...project.tracks].sort((a, b) => {
    const ia = TRACK_ORDER.indexOf(a.role), ib = TRACK_ORDER.indexOf(b.role);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  // Beauty-photo headers: short code + name + indicators (no fake
  // toggles: hide/mute/lock do not exist in this port, so the eye
  // only states the track is visible and the speaker marks audio).
  for (const track of ordered) {
    const row = document.createElement("div");
    // Main lane is taller in the original (TimelineLayout.mainRowHeight
    // 46pt vs 29pt for other rows); the class carries that, ids unchanged.
    row.className = "track-row" + (track.role === "main" ? " track-row-main" : "");
    row.innerHTML = trackHeaderHtml(track.role, track.name, track.kind);
    const lane = document.createElement("div");
    // Round 19: empty lanes get their own class (28px via CSS) so
    // the locked .track-lane rule is never edited.
    lane.className = "track-lane" + (track.items.length === 0 ? " is-empty" : "");
    lane.style.width = widthPx + "px";
    lane.dataset.track = track.id;
    lane.addEventListener("dragover", (e) => { e.preventDefault(); lane.classList.add("target"); });
    lane.addEventListener("dragleave", () => lane.classList.remove("target"));
    lane.addEventListener("drop", async (e) => {
      e.preventDefault(); lane.classList.remove("target");
      const rect = lane.getBoundingClientRect();
      const at = Math.max(0, Math.round(((e.clientX - rect.left) / pxPerSec) * fps()));
      try { await api("/api/project", { op: "move", item: selectedId, track: track.id, at }); await load(); }
      catch (err) { setStatus("Di chuyển bị từ chối: " + err.message, true); await load(); }
    });
    for (const item of track.items) {
      const el = document.createElement("div");
      el.className = `clip ${track.kind} role-${track.role} ${item.id === selectedId ? "selected" : ""}`;
      // Round 22: id lookup for the overlap flash (add_text refusal
      // names the conflicting clip; see the addTextForm handler).
      el.dataset.item = item.id;
      el.style.left = (item.at / fps()) * pxPerSec + "px";
      el.style.width = Math.max((item.dur / fps()) * pxPerSec - 2, 24) + "px";
      if ((item.dur / fps()) * pxPerSec < 90) el.classList.add("clip-narrow");
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
      } else if (medium && track.kind !== "audio") {
        const img = document.createElement("img");
        img.className = "clip-thumb";
        img.src = `/api/thumbnail/${encodeURIComponent(item.media)}`;
        img.alt = "";
        img.loading = "lazy";
        img.onerror = () => { img.style.display = "none"; };
        const nm = document.createElement("span"); nm.className = "clip-name"; nm.textContent = baseName;
        const du = document.createElement("span"); du.className = "clip-dur"; du.textContent = `${((item.dur / fps())).toFixed(1)}s`;
        el.append(img, nm, du);
        // Real effect chip only: the clip's own stored colour data
        // (preset name, or LUT when no preset). Nothing is invented.
        const fxName = effectChipNameForClip(item);
        if (fxName) { const fx = document.createElement("span"); fx.className = "clip-fx"; fx.textContent = fxName; el.appendChild(fx); }
      } else if (medium) {
        const nm = document.createElement("span"); nm.className = "clip-name"; nm.textContent = baseName;
        el.appendChild(nm);
      } else {
        el.textContent = item.text || item.media || item.id;
        if (track.kind === "text") el.classList.add("clip-title");
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
      el.addEventListener("click", () => selectClipAndPreview(item.id));
      el.addEventListener("dragstart", () => { selectedId = item.id; });
      lane.appendChild(el);
    }
    if (track.role === "main") {
      for (const t of (project.transitions || [])) {
        const from = track.items.find((i) => i.id === t.from);
        if (!from) continue;
        const marker = document.createElement("div");
        marker.className = "transition-marker";
        marker.style.left = ((from.at + from.dur) / fps()) * pxPerSec - 9 + "px";
        marker.textContent = "⇄";
        marker.title = `${t.kind} (${t.duration} frames)`;
        lane.appendChild(marker);
      }
    }
    const ph = document.createElement("div");
    ph.className = "tl-playhead";
    ph.style.left = (playheadFrame / fps()) * pxPerSec + "px";
    lane.appendChild(ph);
    row.appendChild(lane);
    wrap.appendChild(row);
  }
  const presentRoles = new Set(project.tracks.map((t) => t.role));
  const standard = [["captions", "Captions", "text"], ["overlay", "Overlay", "video"], ["main", "Main", "video"], ["background", "Background", "video"], ["dialogue", "Dialogue", "audio"], ["voiceover", "Voiceover", "audio"], ["music", "Music", "audio"], ["sfx", "Sfx", "audio"]];
  const emptyRoles = standard.filter(([role]) => !presentRoles.has(role));
  if (emptyRoles.length && !window.__showEmptyTracks) {
    const row = document.createElement("div");
    row.className = "track-row track-row-fold";
    row.innerHTML = `<div class="track-label">Tracks</div><div class="track-lane empty-lane" style="width:${widthPx}px">${emptyRoles.length} track trống — bấm để hiện</div>`;
    row.addEventListener("click", () => { window.__showEmptyTracks = true; renderTracks(); });
    wrap.appendChild(row);
  } else {
    for (const [role, name, kind] of emptyRoles) {
      const row = document.createElement("div");
      row.className = "track-row track-row-empty";
      row.innerHTML = trackHeaderHtml(role, name, kind) + `<div class="track-lane empty-lane" style="width:${widthPx}px">Trống — dùng Add Layer rồi kéo clip vào đây</div>`;
      wrap.appendChild(row);
    }
    if (emptyRoles.length) {
      const row = document.createElement("div");
      row.className = "track-row track-row-fold";
      row.innerHTML = `<div class="track-label">Tracks</div><div class="track-lane empty-lane" style="width:${widthPx}px">Ẩn track trống — bấm để gập</div>`;
      row.addEventListener("click", () => { window.__showEmptyTracks = false; renderTracks(); });
      wrap.appendChild(row);
    }
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
  list.innerHTML = takes.length ? takes.map((x) => `<li>${x}</li>`).join("") : "<li>Chưa có take voiceover nào.</li>";
}
function fillDetailsProject() {
  if (!project) return;
  if (project.format) document.documentElement.style.setProperty("--project-aspect", project.format.width + "/" + project.format.height);
  const set = (id, v) => { const el = $(id); if (el) el.textContent = v; };
  set("detailsName", project.name || "—");
  const nm = $("detailsName");
  if (nm) nm.title = project.name || "";
  set("detailsFormat", `${project.format.width}×${project.format.height}`);
  set("detailsFps", `${fps().toFixed(2)} fps`);
  let totalS = 0;
  for (const t of project.tracks) for (const it of t.items) totalS = Math.max(totalS, (it.at + it.dur) / fps());
  set("detailsLength", `${totalS.toFixed(2)}s`);
  set("detailsClips", String(project.tracks.reduce((n, t) => n + t.items.length, 0)));
  const setPathTitle = () => { const p = $("detailsPath"); if (p) p.title = p.textContent || ""; };
  if (window.__projectDir) { set("detailsPath", window.__projectDir); setPathTitle(); }
  else api("/api/info").then((d) => { window.__projectDir = d.project_dir || ""; set("detailsPath", window.__projectDir || "—"); setPathTitle(); }).catch(() => {});
}
function renderInspector() {
  const found = selectedId ? findItem(selectedId) : null;
  $("inspectorEmpty").hidden = true; // empty state is now the project Details view
  $("inspectorForm").hidden = !found;
  const dp = $("detailsProject");
  if (dp) { dp.hidden = !!found; if (!found) fillDetailsProject(); }
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
  const eq = (item.color && item.color.eq) || {};
  $("inspEqBrightness").value = eq.brightness !== undefined ? eq.brightness : "";
  $("inspEqContrast").value = eq.contrast !== undefined ? eq.contrast : "";
  $("inspEqSaturation").value = eq.saturation !== undefined ? eq.saturation : "";
  $("inspEqGamma").value = eq.gamma !== undefined ? eq.gamma : "";
  renderKeyframes();
}


/* Finishing batch: aspect ratio, source preview, settings.
   Every control here calls a real API or says plainly what is
   not available — nothing fakes a preview, a format, or a tool. */
const FORMAT_PRESETS = {"16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080],
  "4:5": [1080, 1350], "3:4": [1080, 1440], "4:3": [1440, 1080], "21:9": [1920, 810]};
function presetKeyFor(w, h) {
  for (const [k, v] of Object.entries(FORMAT_PRESETS)) if (v[0] === w && v[1] === h) return `${w}x${h}`;
  return "custom";
}
function applyPreviewAspect() {
  if (!project) return;
  const ratio = `${project.format.width} / ${project.format.height}`;
  $("preview").style.aspectRatio = ratio;
  $("previewImage").style.aspectRatio = ratio;
}
function syncFormatUI() {
  if (!project) return;
  const w = project.format.width, h = project.format.height;
  const label = $("formatLabel");
  if (label) label.textContent = `${w}×${h} (${presetKeyFor(w, h) === "custom" ? "Tùy chỉnh" : Object.keys(FORMAT_PRESETS).find((k) => FORMAT_PRESETS[k][0] === w && FORMAT_PRESETS[k][1] === h)})`;
  const key = presetKeyFor(w, h);
  for (const id of ["formatPreset", "settingsFormatPreset"]) {
    const sel = $(id); if (sel) sel.value = key;
  }
  const cw = $("settingsFormatWidth"), ch = $("settingsFormatHeight");
  if (cw) cw.value = w; if (ch) ch.value = h;
  applyPreviewAspect();
}
async function applyFormat(w, h) {
  try {
    await api("/api/project", { op: "set_format", width: Number(w), height: Number(h) });
    setStatus(`Đã đổi tỉ lệ thành ${w}×${h}. Các clip hiện có không bị co giãn — tỉ lệ mới áp dụng cho lần xuất tiếp theo.`);
    await load();
  } catch (err) { setStatus("Đổi tỉ lệ thất bại: " + err.message, true); }
}
function applyPresetValue(value) {
  if (value === "custom") { setStatus("Chọn kích thước tùy chỉnh trong panel Cài đặt (nút ⚙)."); return; }
  const [w, h] = value.split("x").map(Number);
  applyFormat(w, h);
}
function baseNameOf(medium) { return medium ? medium.path.split(/[\\/]/).pop() : ""; }
function showSourcePreview(medium) {
  previewMode = "source"; previewMediaId = medium.id;
  const video = $("preview"), img = $("previewImage");
  $("previewLabel").textContent = `Đang xem: ${baseNameOf(medium)} — bấm ▶ để phát.`;
  $("previewLabel").hidden = false;
  if (medium.kind === "image" || /\.(png|jpe?g|gif|webp|bmp)$/i.test(medium.path)) {
    img.src = "/api/media/" + encodeURIComponent(medium.id);
    img.hidden = false; video.hidden = true; video.removeAttribute("src"); video.load();
  } else {
    video.src = "/api/media/" + encodeURIComponent(medium.id);
    video.hidden = false; img.hidden = true;
  }
  applyPreviewAspect();
  seekPreviewToPlayhead();
}
function loadMediaPreview(mediaId) {
  const medium = project.media.find((m) => m.id === mediaId);
  if (!medium) { setStatus("Không tìm thấy media: " + mediaId, true); return; }
  previewItemId = null;
  showSourcePreview(medium);
  const srcSel = $("sourceMedia"); if (srcSel) srcSel.value = mediaId;
  setStatus(`Đang xem file gốc: ${baseNameOf(medium)}. Bấm ▶ để phát, hoặc thêm clip vào timeline để dựng.`);
}
function loadSourcePreviewForItem(item) {
  const medium = item.media ? project.media.find((m) => m.id === item.media) : null;
  if (!medium) return;
  previewItemId = item.id;
  showSourcePreview(medium);
}
function selectClipAndPreview(itemId) {
  const found = findItem(itemId);
  if (!found) return;
  selectedId = itemId; renderTracks(); renderInspector(); renderKeyframes();
  loadSourcePreviewForItem(found.item);
  const tl = document.querySelector(".timeline-wrap");
  if (tl) tl.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
// __PREVIEW_SYNC_MAP_START__
// Pure timeline <-> source mapping in seconds. Extracted verbatim by
// tests/test_round14.py and run under Node: both directions must agree
// within one frame (the user's <1-frame sync requirement).
function timelineToSourceSeconds(timelineSec, atSec, inSec, speed, mediaDuration) {
  const clipSec = Math.max(0, timelineSec - atSec);
  const src = inSec + clipSec * (speed || 1);
  const dur = (mediaDuration === null || mediaDuration === undefined) ? Infinity : mediaDuration;
  return Math.max(0, Math.min(src, dur));
}
function sourceToTimelineSeconds(sourceSec, atSec, inSec, speed, clipDurSec) {
  const t = atSec + (sourceSec - inSec) / (speed || 1);
  return Math.max(atSec, Math.min(t, atSec + clipDurSec));
}
// __PREVIEW_SYNC_MAP_END__
function sourceTimeForPlayhead() {
  // Timeline seconds -> source seconds for the selected clip, or
  // plain timeline seconds when only a file (no clip) is previewed.
  const t = playheadFrame / fps();
  if (previewItemId) {
    const found = findItem(previewItemId);
    if (found) {
      const medium = project.media.find((m) => m.id === found.item.media);
      const mediaFps = medium && Array.isArray(medium.fps) ? medium.fps[0] / medium.fps[1] : (medium && medium.fps ? medium.fps : fps());
      const inSec = (found.item.in || 0) / mediaFps;
      const dur = medium && medium.duration ? medium.duration : null;
      return timelineToSourceSeconds(t, found.item.at / fps(), inSec, found.item.speed || 1, dur);
    }
  }
  return t;
}
function seekPreviewToPlayhead() {
  // Timeline -> preview (one direction of the two-way sync). The old
  // code silently dropped the seek when metadata was not loaded yet;
  // now it waits for loadedmetadata instead of losing the seek.
  $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
  renderPreviewCaption();
  updatePreviewEmpty();
  const video = $("preview");
  if (!video || video.hidden || !video.src) return;
  const target = previewMode === "source" ? sourceTimeForPlayhead() : playheadFrame / fps();
  if (!isNaN(video.duration)) video.currentTime = Math.min(target, video.duration);
  else video.addEventListener("loadedmetadata", () => { video.currentTime = Math.min(target, video.duration); }, { once: true });
}
function renderPreviewCaption() {
  // Real timeline text at the playhead: the active text item's own
  // text (or the active karaoke word) at its stored position. Source
  // mode only — the export already carries burned-in subtitles.
  const box = $("previewCaption");
  if (!box || !project) return;
  box.innerHTML = "";
  const video = $("preview");
  if (previewMode !== "source" || !video || video.hidden) { box.hidden = true; return; }
  const stage = document.querySelector(".preview-stage");
  const refH = stage && stage.clientHeight ? stage.clientHeight : 360;
  const tSec = playheadFrame / fps();
  let shown = 0;
  for (const tr of project.tracks) {
    if (tr.kind !== "text") continue;
    for (const item of tr.items) {
      const atSec = item.at / fps(), endSec = (item.at + item.dur) / fps();
      if (tSec < atSec || tSec >= endSec) continue;
      let text = item.text || "";
      if (item.karaoke && item.karaoke.words) {
        const rel = tSec - atSec;
        const w = item.karaoke.words.find((x) => rel >= x.start && rel < x.end);
        if (w) text = w.text;
      }
      if (!text) continue;
      const st = item.textStyle || {};
      const d = document.createElement("div");
      d.className = "preview-caption-line";
      d.textContent = text;
      d.style.left = ((st.positionX ?? 0.5) * 100) + "%";
      d.style.top = ((st.positionY ?? 0.85) * 100) + "%";
      d.style.fontSize = Math.max(14, Math.round((st.size || 0.055) * refH)) + "px";
      box.appendChild(d);
      shown++;
    }
  }
  box.hidden = shown === 0;
}
function updatePreviewEmpty() {
  // Honest empty state: shown only when no preview source is loaded,
  // instead of a black video box pretending to be a preview.
  const box = $("previewEmpty");
  if (!box) return;
  const video = $("preview"), img = $("previewImage");
  const hasSource = (video && !video.hidden && !!video.src) || (img && !img.hidden && !!img.src);
  box.hidden = hasSource;
}
async function fillSettingsInfo() {
  const pi = $("settingsProjectInfo");
  if (pi && project) {
    const clips = project.tracks.reduce((n, t) => n + t.items.length, 0);
    pi.textContent = `Tên: ${project.name} · Rev: ${project.rev ?? 0} · Khung hình: ${project.format.width}×${project.format.height} · FPS: ${fps().toFixed(2)} · ${project.tracks.length} track · ${clips} clip · ${project.media.length} file media`;
  }
  const ei = $("settingsEnvInfo");
  if (ei && !ei.dataset.loaded) {
    try {
      const info = await api("/api/info");
      ei.textContent = `Python ${info.python} · FFmpeg: ${info.ffmpeg} · FFprobe: ${info.ffprobe} · Thư mục project: ${info.project_dir}`;
      ei.dataset.loaded = "1";
    } catch (err) { ei.textContent = "Không lấy được thông tin môi trường: " + err.message; }
  }
}
function applyAgentCollapsePref() {
  const col = $("agentCol"), box = $("settingsAgentCollapsed");
  if (!col) return;
  // Round 18 step 3: the agent column is a fixed right drawer. A
  // stored pref wins; with no pref the drawer follows the
  // original-app rule — open on wide windows (>=1600px), closed
  // below it — so it never eats grid space when closed.
  const stored = localStorage.getItem("vibeedit_agent_collapsed");
  const wide = (typeof window !== "undefined" && typeof window.innerWidth === "number") ? window.innerWidth >= 1600 : true;
  const collapsed = stored === "1" ? true : (stored === "0" ? false : !wide);
  col.classList.toggle("open", !collapsed);
  const backdrop = $("agentBackdrop");
  if (backdrop) backdrop.classList.toggle("show", !collapsed);
  if (box) box.checked = collapsed;
  // The rail "AI Agent" toggle and the header toggle mirror the same
  // state — active + aria-expanded while the drawer is open.
  const toggle = $("btnAgentToggle");
  if (toggle) { toggle.classList.toggle("active", !collapsed); toggle.setAttribute("aria-expanded", String(!collapsed)); toggle.setAttribute("aria-pressed", String(!collapsed)); }
  const top = $("btnAgentToggleTop");
  if (top) { top.classList.toggle("active", !collapsed); top.setAttribute("aria-expanded", String(!collapsed)); top.setAttribute("aria-pressed", String(!collapsed)); }
}
function syncInspectorDrawer() {
  // Round 19: at narrow widths the Details column is a slide-from-
  // right drawer (.open), not a grid column. Keep .open in sync
  // with the hidden state so the drawer never disagrees with the
  // toggle button.
  const wb = document.querySelector(".workbench");
  const col = document.querySelector(".details-col");
  if (!wb || !col) return;
  const hidden = wb.classList.contains("details-hidden");
  col.classList.toggle("open", !hidden);
  const btn = $("btnInspectorToggle");
  if (btn) btn.setAttribute("aria-pressed", String(!hidden));
}
function toggleInspectorColumn() {
  const wb = document.querySelector(".workbench");
  if (!wb) return;
  const hidden = wb.classList.toggle("details-hidden");
  const btn = $("btnInspectorToggle");
  if (btn) btn.setAttribute("aria-expanded", String(!hidden));
  syncInspectorDrawer();
}

$("ruler").addEventListener("click", (e) => {
  const rect = $("ruler").getBoundingClientRect();
  playheadFrame = Math.max(0, Math.round(((e.clientX - rect.left) / pxPerSec) * fps()));
  seekPreviewToPlayhead();
  renderTracks();
});
$("zoom").addEventListener("input", (e) => {
  pxPerSec = Number(e.target.value);
  $("zoomLabel").textContent = pxPerSec + " px/s";
  renderTracks();
});
function setZoom(v) {
  // Round 19: the −/+ buttons step through the SAME zoom mechanism
  // as the slider (pxPerSec, clamped to the slider range 10–200).
  pxPerSec = Math.max(10, Math.min(200, Math.round(v)));
  const z = $("zoom"); if (z) z.value = pxPerSec;
  $("zoomLabel").textContent = pxPerSec + " px/s";
  renderTracks();
}
const zOut = $("zoomOut"), zIn = $("zoomIn");
if (zOut) zOut.addEventListener("click", () => setZoom(pxPerSec - 10));
if (zIn) zIn.addEventListener("click", () => setZoom(pxPerSec + 10));
$("projectName").addEventListener("change", async (e) => {
  try { await api("/api/project", { op: "set_project", name: e.target.value }); setStatus(`Đã đổi tên project thành “${e.target.value}”.`); await load(); }
  catch (err) { setStatus(err.message, true); }
});
// Round 19: Enter in the name field commits (blur fires change).
// Without this, a user who types a name and hits Enter never fires
// change, and the rename silently never happens.
$("projectName").addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.blur(); });
$("btnUndo").addEventListener("click", async () => { try { await api("/api/undo", {}); await load(); setStatus(`Đã hoàn tác. (Edited rev ${project.rev})`); } catch (e) { setStatus(e.message, true); } });
$("btnRedo").addEventListener("click", async () => { try { await api("/api/redo", {}); await load(); setStatus(`Đã làm lại. (Edited rev ${project.rev})`); } catch (e) { setStatus(e.message, true); } });
/* Phase 2 Windows shortcuts: Ctrl (not Command) for a Windows
   browser app. Ctrl+Z undo, Ctrl+Shift+Z / Ctrl+Y redo, Ctrl+S
   explicit save. preventDefault only where the browser would
   otherwise hijack the shortcut (Ctrl+S opens the browser save
   dialog; Ctrl+Z/Y are also claimed by editable fields, which is
   why inputs are skipped below). Round 18 batch 2 reassigned the
   single-letter S key: S is now the magnetic (auto-snap) toggle
   and split moved to Ctrl+K; I/O/E/Q source shortcuts keep
   working unchanged. */
document.addEventListener("keydown", async (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  const key = (e.key || "").toLowerCase();
  try {
    if (key === "s") {
      e.preventDefault();
      setSaveState("saving");
      try { await api("/api/save", {}); setSaveState("saved"); setStatus("Đã lưu project."); }
      catch (err) { setSaveState("error"); setStatus(err.message, true); }
      await load();
    } else if (key === "z" && !e.shiftKey) {
      e.preventDefault();
      await api("/api/undo", {});
      await load();
    } else if ((key === "z" && e.shiftKey) || key === "y") {
      e.preventDefault();
      await api("/api/redo", {});
      await load();
    }
  } catch (err) { setStatus(err.message, true); }
});
// Round 22: background export. POST /api/export returns a job
// immediately; this polls /api/export/status (lock-free server
// side) and shows an indeterminate progress bar with a Cancel
// button, so the editor stays usable during a long render. The
// bar is indeterminate on purpose: the renderer reports no
// percentage, and inventing one would be fake progress.
let exportPollTimer = null, exportJobId = null, exportStartedAt = 0;
function showExportBar(show) {
  const bar = $("exportJobBar"); if (bar) bar.hidden = !show;
}
async function runExportJob(body, label) {
  showExportBar(true);
  const txt = $("exportProgressText");
  try {
    const started = await api("/api/export", body);
    exportJobId = started.job ? started.job.id : null;
    exportStartedAt = Date.now();
    if (txt) txt.textContent = `Đang xuất ${label}…`;
    await new Promise((resolve, reject) => {
      clearInterval(exportPollTimer);
      exportPollTimer = setInterval(async () => {
        try {
          const res = await fetch("/api/export/status" + (exportJobId ? "?job=" + encodeURIComponent(exportJobId) : ""));
          const d = await res.json();
          const job = d.job;
          if (!job) { clearInterval(exportPollTimer); resolve(null); return; }
          const secs = Math.floor((Date.now() - exportStartedAt) / 1000);
          if (txt) txt.textContent = `Đang xuất ${label}… ${secs}s`;
          if (job.status === "done") { clearInterval(exportPollTimer); resolve(job); }
          else if (job.status === "error") { clearInterval(exportPollTimer); reject(new Error(job.error || "Xuất thất bại")); }
          else if (job.status === "cancelled") { clearInterval(exportPollTimer); resolve(null); }
        } catch (err) { clearInterval(exportPollTimer); reject(err); }
      }, 1000);
    }).then(async (job) => {
      showExportBar(false); exportJobId = null;
      if (!job) { setStatus("Đã huỷ xuất."); return; }
      setStatus(`Xuất xong: ${job.report.output} (${job.report.duration} giây, ${job.report.width}x${job.report.height}).`);
      await load();
    });
  } catch (err) { showExportBar(false); exportJobId = null; setStatus("Xuất thất bại: " + err.message, true); }
}
async function doExport(preset) {
  await runExportJob({ preset, normalize: $("exportNormalize") ? $("exportNormalize").checked : false }, preset);
}
// Round 22: cancel a running background export. The server marks the
// job cancelled (its output is never published); the poller in
// runExportJob then resolves to "Đã huỷ xuất." A second click is
// safe: cancel_export_job returns the already-cancelled job.
// Guarded: the bar markup sits after the script tag, so the button
// does not exist yet at parse time.
const cancelBtn = $("btnExportCancel");
if (cancelBtn) cancelBtn.addEventListener("click", async () => {
  if (!exportJobId) return;
  try { await api("/api/export/cancel", { job: exportJobId }); }
  catch (err) { /* poller reports the terminal state either way */ }
});
$("btnExportDraft").addEventListener("click", () => doExport("draft"));
$("btnExportFull").addEventListener("click", () => doExport("full"));
$("addClipForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/project", { op: "add_clip", media: $("addMedia").value, track: $("addTrack").value,
      at: Number($("addAt").value), in: Number($("addIn").value),
      dur: $("addDur").value ? Number($("addDur").value) : null, speed: Number($("addSpeed").value) });
    await load();
    const newId = data.result && data.result.id;
    if (newId) { selectClipAndPreview(newId); setStatus("Clip đã thêm — đang xem file gốc của clip, bấm ▶ để phát."); }
    else setStatus("Đã thêm clip.");
  } catch (err) { setStatus(err.message, true); }
});
const btnQuick = $("btnAddClipQuick");
if (btnQuick) btnQuick.addEventListener("click", () => {
  const sel = $("addMedia");
  if (sel && sel.value) addMediaToTimeline(sel.value);
  else setMediaStatus("Chưa chọn file media nào để thêm.", true);
});
const btnPlugins = $("btnPlugins");
if (btnPlugins) btnPlugins.addEventListener("click", () => {
  // Round 5: this used to be a status-only message claiming there was
  // no plugin panel. There IS one: the Plugins panel in the Details
  // column (apply a sample plugin to the selected clip, enable/disable
  // installed plugins) and plugin install/download in the More tab.
  // So the top-bar button now scrolls to the real Details panel.
  const col = document.querySelector(".details-col");
  if (col) {
    col.scrollIntoView({ behavior: "smooth", block: "start" });
    col.classList.add("details-flash");
    setTimeout(() => col.classList.remove("details-flash"), 1600);
  }
  setStatus("Plugins: xem panel Plugins ở cột Details bên phải (áp dụng plugin mẫu cho clip đang chọn, bật/tắt plugin đã cài); cài plugin mới ở tab More.");
});
const btnReviewTop = $("btnReviewTop");
if (btnReviewTop) btnReviewTop.addEventListener("click", () => {
  const tab = document.querySelector('[data-tab="ai"]'); if (tab) tab.click();
  const r = $("btnReview"); if (r) r.click();
});
const transcribeForm = $("transcribeForm");
if (transcribeForm) transcribeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    setStatus("Đang phiên âm (faster-whisper)…");
    const data = await api("/api/project", { op: "transcribe", media: $("transcribeMedia").value, track: "t1", model: $("transcribeModel").value });
    setStatus(`Đã phiên âm: ${data.result.added.length} đoạn phụ đề đã thêm vào track Captions.`);
    await load();
  } catch (err) { setStatus(`Phiên âm thất bại: ${err.message}`, true); }
});
const pluginForm = $("pluginForm");
if (pluginForm) pluginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedId) { const r = $("pluginResult"); if (r) r.textContent = "Hãy chọn một clip trên timeline trước."; return; }
  try {
    const data = await api("/api/plugin", { plugin: $("pluginSelect").value, item: selectedId });
    const r = $("pluginResult"); if (r) r.textContent = `Đã áp dụng ${$("pluginSelect").value} cho clip ${data.item.id}.`;
    await load();
  } catch (err) { const r = $("pluginResult"); if (r) r.textContent = `Plugin thất bại: ${err.message}`; }
});
$("addTextForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "add_text", track: "t1", text: $("addText").value,
      at: Number($("addTextAt").value), dur: Number($("addTextDur").value) });
    setStatus("Đã thêm chữ."); await load();
  } catch (err) {
    // Round 22: overlap refusal names the conflicting clip
    // ("Item overlaps <id> on track ...") — flash exactly that clip
    // instead of leaving the user to guess which caption collides.
    setStatus(err.message, true);
    const m = /overlaps (\S+) on track/.exec(err.message || "");
    if (m) {
      const clash = document.querySelector(`.clip[data-item="${m[1]}"]`);
      if (clash) { clash.classList.add("clip-flash"); setTimeout(() => clash.classList.remove("clip-flash"), 3400); }
    }
  }
});
$("inspectorForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "move", item: $("inspId").value, track: $("inspTrack").value, at: Number($("inspAt").value) });
    if ($("inspSpeed").value) await api("/api/project", { op: "set_speed", item: $("inspId").value, speed: Number($("inspSpeed").value) });
    await api("/api/project", { op: "set_fade", item: $("inspId").value, fadeIn: Number($("inspFadeIn").value), fadeOut: Number($("inspFadeOut").value) });
    if ($("inspText").value) await api("/api/project", { op: "set_text", item: $("inspId").value, text: $("inspText").value });
    await api("/api/project", { op: "set_volume", item: $("inspId").value, volume: Number($("inspVolume").value) });
    const eqVals = {};
    if ($("inspEqBrightness").value !== "") eqVals.brightness = Number($("inspEqBrightness").value);
    if ($("inspEqContrast").value !== "") eqVals.contrast = Number($("inspEqContrast").value);
    if ($("inspEqSaturation").value !== "") eqVals.saturation = Number($("inspEqSaturation").value);
    if ($("inspEqGamma").value !== "") eqVals.gamma = Number($("inspEqGamma").value);
    if ($("inspLut").value || $("inspPreset").value || $("inspStrength").value !== "" || $("inspPresetStrength").value !== "" || Object.keys(eqVals).length) await api("/api/project", { op: "set_color", item: $("inspId").value, lut: $("inspLut").value || null, preset: $("inspPreset").value || null, strength: $("inspStrength").value === "" ? null : Number($("inspStrength").value), preset_strength: $("inspPresetStrength").value === "" ? null : Number($("inspPresetStrength").value), eq: Object.keys(eqVals).length ? eqVals : null });
    setStatus("Đã cập nhật clip."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("transitionForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Chọn clip ở bên trái điểm cắt trước.", true); return; }
  const main = project.tracks.find((t) => t.role === "main");
  const items = [...main.items].sort((a, b) => a.at - b.at);
  const idx = items.findIndex((i) => i.id === found.item.id);
  const next = items[idx + 1];
  if (!next || next.at !== found.item.at + found.item.dur) { setStatus("Clip đang chọn không có clip kế tiếp liền kề trên track chính.", true); return; }
  try {
    await api("/api/project", { op: "add_transition", from: found.item.id, to: next.id, kind: $("trKind").value, duration: Number($("trDur").value) });
    setStatus("Đã thêm transition."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("keyframeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedId) { setStatus("Chọn một clip trước.", true); return; }
  try {
    await api("/api/project", { op: "add_keyframe", item: selectedId, at: Number($("kfAt").value), property: $("kfProp").value, value: Number($("kfValue").value) });
    setStatus("Đã thêm keyframe."); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("srtImportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/project", { op: "srt_import", track: "t1", srt: $("srtText").value });
    setStatus(`Đã import ${data.result.length} cue SRT.`); await load();
  } catch (err) { setStatus(err.message, true); }
});
$("btnSrtExport").addEventListener("click", async () => {
  try {
    const data = await api("/api/project", { op: "srt_export", track: "t1" });
    const blob = new Blob([data.srt], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "captions.srt"; a.click();
    setStatus("Đã xuất SRT.");
  } catch (err) { setStatus(err.message, true); }
});
async function splitAtPlayhead() {
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Chọn một clip trước.", true); return false; }
  try {
    await api("/api/project", { op: "split", item: found.item.id, atFrame: playheadFrame });
    setStatus("Đã tách clip."); await load(); return true;
  } catch (err) { setStatus(err.message, true); return false; }
}
/* Round 18 batch 2: split ALL clips intersecting the playhead.
   Composed only from the existing "split" op: the intersecting
   list is snapshotted first (splitting never changes the other
   items' ranges), then each item is split in turn and the original
   selection is restored. No new op. */
async function splitAllAtPlayhead() {
  if (!project) return;
  const targets = [];
  for (const t of project.tracks) for (const it of t.items)
    if (playheadFrame >= it.at && playheadFrame < it.at + it.dur) targets.push(it.id);
  if (!targets.length) { setStatus("Không có clip nào tại playhead để tách.", true); return; }
  const before = selectedId;
  let done = 0;
  for (const id of targets) { selectedId = id; if (await splitAtPlayhead()) done++; }
  selectedId = before;
  await load();
  setStatus(`Đã tách tất cả: ${done}/${targets.length} clip tại playhead.`);
}
$("btnSplit").addEventListener("click", splitAtPlayhead);
$("btnPlayheadSplit").addEventListener("click", splitAtPlayhead);
$("btnDelete").addEventListener("click", async () => {
  if (!selectedId) { setStatus("Chọn một clip trước.", true); return; }
  // Round 22: clear the selection BEFORE awaiting, so a fast
  // double-click cannot fire a second delete for the same clip.
  const doomed = selectedId; selectedId = null;
  try { await api("/api/project", { op: "delete", item: doomed }); await load(); setStatus("Đã xoá clip — bấm Ctrl+Z để hoàn tác."); }
  catch (err) { setStatus(err.message, true); }
});
document.addEventListener("keydown", (e) => {
  // Phase 2: Ctrl+S must reach the save handler above, not split.
  if (e.ctrlKey || e.metaKey) return;
  if (e.key === "s" || e.key === "S") {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    // Round 18 batch 2: S is now the auto-snap toggle. The app has
    // no persistent drag-snap switch; the magnetic Main toggle is
    // the only persistent auto-attach switch, so S clicks it.
    // Split moved to Ctrl+K (see the round 18 shortcut block).
    const mg = $("tlMagnetic"); if (mg) mg.click();
  }
});
$("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("uploadFile").files[0];
  if (!file) { setStatus("Chọn một file trước.", true); return; }
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/media/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) setStatus(data.error, true);
  else { await load(); loadMediaPreview(data.media.id); setStatus(data.reused ? `File này đã có, dùng lại media ${data.media.id}.` : "Đã tải lên: " + data.media.path + " — đang xem file gốc, bấm ▶ để phát."); }
});

load().catch((err) => setStatus("Tải project thất bại: " + err.message, true));

/* Phase 5 agent dock: live MCP tool list from /api/mcp-tools. A
   failure here must never break the editor above, so it is fenced
   off from load(). */
async function loadMcpTools() {
  const list = $("mcpTools");
  if (!list) return;
  try {
    const data = await api("/api/mcp-tools");
    $("mcpToolCount").textContent = data.count;
    // Phase 0: the provider option shows the LIVE registry count,
    // never a hardcoded number (a stale number here is how an old
    // count survived several batches). On failure the
    // option keeps its number-free label from index.html.
    const provider = $("agentProvider");
    if (provider) {
      const opt = provider.querySelector('option[value="mcp"]');
      if (opt) opt.textContent = `External agent (MCP) — ${data.count} tools`;
    }
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
  // Round 22: an empty folder list still exports the current project
  // (server behaviour) — say so up front instead of letting the
  // "1/1 success" report surprise the user.
  setStatus(folders.length === 0 ? "Chưa nhập thư mục phụ — sẽ chỉ xuất project hiện tại." : "Đang xuất batch… có thể mất một lúc.");
  try {
    const data = await api("/api/batch", { folders, preset: "full", normalize: $("batchNormalize").checked });
    const ok = data.results.filter((r) => r.ok).length;
    $("batchResult").textContent = `Xuất batch xong: ${ok}/${data.results.length} thành công. ` + data.results.map((r) => `${r.project}: ${r.ok ? "OK" : "FAIL " + r.error}`).join(" | ");
    setStatus(`Xuất batch xong: ${ok}/${data.results.length} thành công.`);
  } catch (err) { setStatus("Xuất batch thất bại: " + err.message, true); }
});
$("otioImportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/api/otio-import", { otio: $("otioImportPath").value, dest: $("otioImportDest").value, merge: $("otioImportMerge").checked });
    $("phase4Result").textContent = `OTIO imported: ${data.report.clips} clips, ${data.report.transitions} transitions, ${data.report.markers} markers. Missing: ${data.report.missing.join(", ") || "none"}. Warnings: ${data.report.warnings.join("; ") || "none"}.`;
    setStatus("Đã import OTIO (vào thư mục đích, không phải project đang mở).");
  } catch (err) { setStatus("Import OTIO thất bại: " + err.message, true); }
});
$("karaokeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedId) { setStatus("Chọn một text item trước.", true); return; }
  try {
    await api("/api/project", { op: "karaoke_add", item: selectedId, words: JSON.parse($("karaokeWords").value) });
    setStatus("Đã thêm thời gian karaoke."); await load();
  } catch (err) { setStatus("Karaoke thất bại: " + err.message, true); }
});
$("btnKaraokeAss").addEventListener("click", async () => {
  try {
    const data = await api("/api/karaoke-ass", {});
    const blob = new Blob([data.ass], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "karaoke.ass"; a.click();
    setStatus(`Đã xuất karaoke .ass: ${data.report.karaoke_items} mục.`);
  } catch (err) { setStatus("Xuất karaoke thất bại: " + err.message, true); }
});
$("adjustmentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "adjustment_add", at: Number($("adjAt").value), dur: Number($("adjDur").value), preset: $("adjPreset").value || null, lut: $("adjLut").value || null });
    setStatus("Đã thêm lớp hiệu chỉnh."); await load();
  } catch (err) { setStatus("Hiệu chỉnh thất bại: " + err.message, true); }
});
$("beatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  setStatus("Đang phát hiện nhịp…");
  try {
    const data = await api("/api/project", { op: "beat_detect", media: $("beatMedia").value });
    const n = (data.result.beats || []).length;
    setStatus(n ? `Đã phát hiện nhịp: ${n} nhịp.` : "Đã chạy phân tích nhịp nhưng không tìm thấy nhịp nào trong file này (0 nhịp) — thử file nhạc có nhịp rõ hơn."); await load();
  } catch (err) { setStatus("Phát hiện nhịp thất bại: " + err.message, true); }
});
$("btnBeatsMarkers").addEventListener("click", async () => {
  try { await api("/api/project", { op: "beats_to_markers" }); setStatus("Đã chép nhịp thành marker."); await load(); }
  catch (err) { setStatus(err.message === "No beat grid detected yet" ? "Chưa có lưới nhịp — phát hiện nhịp trước (nếu đã chạy mà vẫn trống, file này không có nhịp rõ)." : err.message, true); }
});
$("btnSnap").addEventListener("click", async () => {
  const beats = (project.beatGrid && project.beatGrid.beats) || [];
  if (!beats.length) { setStatus("Chưa có lưới nhịp — phát hiện nhịp trước.", true); return; }
  const t = playheadFrame / fps();
  const nearest = beats.reduce((a, b) => Math.abs(b - t) < Math.abs(a - t) ? b : a);
  playheadFrame = Math.round(nearest * fps()); renderTracks();
  setStatus(`Playhead đã nhảy tới nhịp tại ${nearest} giây.`);
});
$("duckingForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/project", { op: "ducking_set", enabled: $("duckEnabled").checked, amount_db: Number($("duckAmount").value) });
    setStatus("Đã lưu ducking."); await load();
  } catch (err) { setStatus("Lưu ducking thất bại: " + err.message, true); }
});
$("btnOtio").addEventListener("click", async () => {
  try {
    const data = await api("/api/otio", {});
    const blob = new Blob([data.otio], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "timeline.otio"; a.click();
    setStatus(`Đã xuất OTIO: ${data.report.tracks} track, ${data.report.clips} mục.`);
  } catch (err) { setStatus("Xuất OTIO thất bại: " + err.message, true); }
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
      lines.push("Chưa có bản xuất nên không có mục nào bị bỏ qua để báo cáo.");
    box.textContent = lines.join(" ");
    setStatus("Đã làm mới review.");
  } catch (err) { box.textContent = "Review failed: " + err.message; setStatus(err.message, true); }
});
$("btnTransitionPreview").addEventListener("click", async () => {
  const found = selectedId ? findItem(selectedId) : null;
  if (!found) { setStatus("Chọn clip ở bên trái điểm cắt trước.", true); return; }
  const main = project.tracks.find((t) => t.role === "main");
  const items = [...main.items].sort((a, b) => a.at - b.at);
  const idx = items.findIndex((i) => i.id === found.item.id);
  const next = items[idx + 1];
  const trans = (project.transitions || []).find((t) => t.from === found.item.id && next && t.to === next.id);
  if (!trans) { setStatus("Chưa có transition sau clip đang chọn — thêm một cái trước.", true); return; }
  setStatus("Đang render xem trước transition… (bản nháp của đoạn cắt)");
  try {
    const data = await api("/api/transition-preview", { transition: trans.id });
    const box = $("transitionPreviewBox");
    box.hidden = false;
    $("transitionPreviewImg").src = "/api/transition-preview?transition=" + encodeURIComponent(trans.id) + "&t=" + Date.now();
    $("transitionPreviewLabel").textContent = `${data.preview.kind} at ${data.preview.midpoint_seconds}s (draft ${data.preview.width}x${data.preview.height}).`;
    setStatus("Xem trước transition đã sẵn sàng.");
  } catch (err) { setStatus("Xem trước transition thất bại: " + err.message, true); }
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
    b.addEventListener("click", () => {
      const col = document.querySelector(".tool-col");
      if (b.closest(".tool-rail") && b.classList.contains("active")) {
        if (col) col.classList.add("tool-col-collapsed");
        activateTab("__none__");
        return;
      }
      if (col) col.classList.remove("tool-col-collapsed");
      activateTab(b.dataset.tab);
      // Round 22: switching panels overwrites the status toast,
      // so it never keeps a stale message from an earlier panel.
      const tabLabels = { media: "Media", audio: "Audio", text: "Text",
        stickers: "Stickers — chưa có sticker, dùng text overlay thay thế",
        effects: "Effects", transitions: "Transitions", filters: "Filters",
        voice: "Voice", knowledge: "Knowledge", vision: "Vision",
        templates: "More", captions: "Captions", ai: "AI" };
      setStatus("Panel: " + (tabLabels[b.dataset.tab] || b.dataset.tab) + ".");
    });
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
  $("tlSnap").addEventListener("click", () => { const b = $("btnSnap"); if (b) b.click(); });
  $("tlFit").addEventListener("click", () => {
    const lane = document.querySelector(".track-lane");
    const w = lane ? lane.clientWidth : 800;
    let totalS = 1;
    if (project) for (const t of project.tracks) for (const it of t.items) totalS = Math.max(totalS, (it.at + it.dur) / fps());
    pxPerSec = Math.max(10, Math.min(200, Math.floor((w - 40) / totalS)));
    const z = document.getElementById("zoom"); if (z) z.value = pxPerSec;
    const zl = document.getElementById("zoomLabel"); if (zl) zl.textContent = pxPerSec + " px/s";
    renderTracks();
  });
  $("tlWaveforms").addEventListener("click", () => { window.__waveCache = {}; renderTracks(); setStatus("Đã tải lại sóng âm."); });
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
  function agentLogRow(text, fromUser) {
    const chat = $("agentChat");
    if (!chat) return;
    const row = document.createElement("div");
    row.className = "agent-log-row" + (fromUser ? " from-user" : "");
    const tm = document.createElement("span");
    tm.className = "agent-log-time";
    tm.textContent = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    const tx = document.createElement("span");
    tx.className = "agent-log-text";
    tx.textContent = text;
    row.append(tm, tx);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
  }
  function agentSay(text) { agentLogRow(text, false); }
  function agentAsk(text) { agentLogRow(text, true); }
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
  document.querySelectorAll("[data-agent-chip]").forEach((b) => b.addEventListener("click", () => {
    const input = $("agentChatInput"); const form = $("agentChatForm");
    if (input) input.value = b.dataset.agentChip;
    if (form) form.requestSubmit();
  }));
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
        agentSay("Các lệnh tôi thực sự chạy được ở đây: list clips, export, review, stats, undo, redo, workspace, project context. Để AI sửa thật, kết nối một agent ngoài: python windows\\vibeedit.py mcp <project-folder> (số công cụ trực tiếp hiển thị trong danh sách bên dưới). Tôi không phải LLM đã kết nối nên không viết kịch bản hay tạo giọng trong panel này.");
      } else if (lower.includes("list clip")) {
        const items = [];
        for (const t of project.tracks) for (const it of t.items) items.push(`${t.name}: ${it.text || it.media || it.id} (${(it.at / fps()).toFixed(2)}s)`);
        agentSay(items.length ? `Clips (${items.length}): ${items.join(" | ")}` : "No clips on the timeline yet.");
      } else if (lower.includes("export")) {
        agentSay("Đang xuất bản nháp (xuất thật, qua cùng nút Export draft)…");
        doExport("draft");
      } else if (lower.includes("review")) {
        const r = $("btnReview"); if (r) r.click();
        agentSay("Review đã làm mới — xem panel Review trong tab AI để thấy kiểm chứng, thống kê và mục đã bỏ qua.");
      } else if (lower.includes("stats") || lower.includes("project context")) {
        const data = await api("/api/project", { op: "project_stats" });
        const st = data.result;
        agentSay(`Bối cảnh project: ${st.name}, rev ${st.rev}, ${st.tracks} tracks, ${st.items} items, ${st.clips} clips, ${st.duration_seconds}s.`);
      } else if (lower.includes("workspace")) {
        agentSay(`Workspace: project "${project.name}", rev ${project.rev ?? 0}, ${project.format.width}x${project.format.height}, ${project.tracks.length} tracks. Open project folder via the server project path shown in the console.`);
      } else if (lower === "undo") {
        const b = $("btnUndo"); if (b) b.click();
        agentSay("Đã yêu cầu hoàn tác.");
      } else if (lower === "redo") {
        const b = $("btnRedo"); if (b) b.click();
        agentSay("Đã yêu cầu làm lại.");
      } else {
        agentSay("Tôi chưa thể làm việc đó bằng LLM trong app này — chưa có provider nào được kết nối ở đây. Thử: help, list clips, export, review, stats, undo, redo. Để AI tạo nội dung, kết nối một agent ngoài: python windows\\vibeedit.py mcp <project-folder>.");
      }
    } catch (err) { agentSay("Lệnh thất bại: " + err.message); }
  });
  const provider = $("agentProvider");
  if (provider) provider.addEventListener("change", () => {
    if (provider.value === "ollama") agentSay("Ollama chưa được kết nối trong app này — chưa cấu hình endpoint nên tôi không thể tạo nội dung bằng nó. Lựa chọn External agent (MCP) mới là đường đang hoạt động.");
  });
  function agentBtn(id, fn) {
    const b = $(id); if (b) b.addEventListener("click", fn);
  }
  agentBtn("btnAgentWorkspace", () => agentSay(`Workspace: project "${project.name}", rev ${project.rev ?? 0}, ${project.format.width}x${project.format.height}, ${project.tracks.length} tracks.`));
  agentBtn("btnAgentContext", async () => {
    try {
      const data = await api("/api/project", { op: "project_stats" });
      const st = data.result;
      agentSay(`Bối cảnh project: ${st.name}, rev ${st.rev}, ${st.tracks} tracks, ${st.items} items, ${st.clips} clips, ${st.duration_seconds}s.`);
    } catch (err) { agentSay("Lấy bối cảnh project thất bại: " + err.message); }
  });
  agentBtn("btnAgentSurvey", () => { const r = $("btnReview"); if (r) r.click(); agentSay("Survey: Review đã làm mới — xem panel Review trong tab AI."); });
  agentBtn("btnAgentWriteVO", () => agentSay("Write VO (viết kịch bản bằng AI) chưa có trong app. Dùng panel Voice để import audio voiceover, hoặc một agent ngoài qua MCP để soạn lời."));
  agentBtn("btnAgentReview", () => { const r = $("btnReview"); if (r) r.click(); agentSay("Review đã làm mới — xem panel Review trong tab AI."); });
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
      setStatus("Đã thêm take voiceover."); await load();
    } catch (err) { $("voiceResult").textContent = "Voiceover take failed: " + err.message; setStatus(err.message, true); }
  });
  const cloneBtn = $("btnVoiceClone");
  if (cloneBtn) cloneBtn.addEventListener("click", async () => {
    const file = $("voiceRefFile") && $("voiceRefFile").files[0];
    if (!file) { const msg = "Choose a reference audio file first. Note: voice cloning is not available in this Windows port yet."; $("voiceResult").textContent = msg; setStatus(msg, true); return; }
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch("/api/media/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) { $("voiceResult").textContent = "Upload failed: " + data.error; setStatus("Upload thất bại: " + data.error, true); return; }
    $("voiceResult").textContent = "Reference audio imported as media (" + data.media.path + "). Voice cloning is not available yet — place it on the Voiceover track with the form below.";
    setStatus("Đã import audio mẫu."); await load();
  });
  const genBtn = $("btnVoiceGenerate");
  if (genBtn) genBtn.addEventListener("click", async () => {
    const text = ($("voiceGenText") ? $("voiceGenText").value : "").trim();
    if (!text) { $("voiceResult").textContent = "Nhập câu thoại cần tạo giọng trước."; return; }
    $("voiceResult").textContent = "Đang tạo giọng…";
    try {
      const provider = $("voiceProvider") ? $("voiceProvider").value : "auto";
      const voice = $("voiceVoice") ? $("voiceVoice").value : "";
      const model = $("voiceGenModel") ? $("voiceGenModel").value : "";
      // Round 19: never stay silent when no backend exists — check
      // the real backends first and say so clearly.
      const check = await api("/api/project", { op: "voice_check" });
      const backs = check.backends || {};
      if (!backs.piper && !backs.edge_tts) {
        const msg = "Chưa có backend giọng nói: cài Piper (binary + model .onnx) hoặc edge-tts để tạo giọng.";
        $("voiceResult").textContent = msg; setStatus(msg, true); return;
      }
      const data = await api("/api/project", { op: "voice_generate", text, provider, voice: voice || undefined, model: model || undefined });
      $("voiceResult").textContent = `Đã tạo giọng bằng ${data.backend}: ${data.path} (media ${data.media}). Dùng form “Import a voiceover take…” bên dưới để đặt lên track Voiceover, hoặc đặt ngay bằng voice_place qua MCP.`;
      setStatus("Đã tạo giọng — xem chi tiết trong panel Voice.");
      await load();
    } catch (err) { $("voiceResult").textContent = "Tạo giọng thất bại: " + err.message; setStatus(err.message, true); }
  });

  // Player view controls (real display controls; Compare is a masked
  // wipe with time-sync, not a sample-accurate frame lock — see below)
  const tabTl = $("playerTabTimeline"), tabSrc = $("playerTabSource"), note = $("playerSourceNote"), wrap = document.querySelector(".preview-wrap");
  if (tabTl) tabTl.addEventListener("click", () => {
    tabTl.classList.add("active"); if (tabSrc) tabSrc.classList.remove("active");
    if (wrap) wrap.hidden = false; if (note) note.hidden = true;
  });
  if (tabSrc) tabSrc.addEventListener("click", () => {
    // Round 5: the old handler hid .preview-wrap, which CONTAINS
    // playerSourceNote, so the note never showed and the whole preview
    // (including the Source In/Out controls) vanished — a dead tab.
    // Source preview really exists (showSourcePreview, GET
    // /api/media/<id>), so Source now shows the selected source file,
    // and only asks the user to pick one when none is selected.
    tabSrc.classList.add("active"); if (tabTl) tabTl.classList.remove("active");
    if (wrap) wrap.hidden = false; if (note) note.hidden = true;
    const sel = $("sourceMedia");
    const mediaId = (sel && sel.value) || previewMediaId;
    const medium = mediaId ? project.media.find((m) => m.id === mediaId) : null;
    if (medium) {
      showSourcePreview(medium);
      setStatus("Đang xem file nguồn: " + baseNameOf(medium) + " — bấm ▶ để phát.");
    } else {
      setStatus("Chọn một file nguồn ở ô Nguồn bên dưới rồi bấm Source để xem file gốc.", true);
    }
  });
  const fitBtn = $("btnPreviewFit");
  if (fitBtn && wrap) fitBtn.addEventListener("click", () => { wrap.classList.toggle("fit-contain"); setStatus(wrap.classList.contains("fit-contain") ? "Preview fit: contain." : "Preview fit: default."); });
  const safeBtn = $("btnPreviewSafe"), safe = $("safeAreaOverlay");
  if (safeBtn && safe) safeBtn.addEventListener("click", () => { safe.hidden = !safe.hidden; setStatus(safe.hidden ? "Safe-area guide hidden." : "Safe-area guide shown (display guide only, not a render setting)."); });
  const cmpBtn = $("btnPreviewCompare");
  // Round 4: REAL Compare masked wipe, following the original
  // (EditorView+Viewer: a second player masked to one half +
  // Before/After labels). Before (source) is the base layer; After
  // (latest export) sits on top, clipped to the right of a draggable
  // divider. Sync: the two <video> elements are NOT sample-accurate
  // frame-locked — the browser cannot lock two decoders that way —
  // so play/pause/seek/timeupdate events keep their times aligned
  // (re-sync when they drift past 0.3s). That residual drift is
  // stated honestly in the sync note, never claimed away.
  let lastSourceMediaId = null, compareOn = false, compareSynced = false;
  function compareWipeAt(pct) {
    const after = document.querySelector("#compareWipe .compare-after");
    const div = $("compareDivider");
    const p = Math.max(0, Math.min(100, pct));
    if (after) after.style.clipPath = `inset(0 0 0 ${p}%)`;
    if (div) div.style.left = p + "%";
    const range = $("compareRange"); if (range) range.value = String(p);
  }
  function compareWireSync() {
    if (compareSynced) return; compareSynced = true;
    const src = $("previewCompareSource"), exp = $("previewCompareExport");
    if (!src || !exp) return;
    let syncing = false, lastSync = 0;
    exp.addEventListener("play", () => { src.play().catch(() => {}); });
    exp.addEventListener("pause", () => { src.pause(); });
    exp.addEventListener("seeked", () => {
      if (Math.abs(src.currentTime - exp.currentTime) > 0.15) {
        syncing = true; src.currentTime = exp.currentTime; syncing = false;
      }
    });
    exp.addEventListener("timeupdate", () => {
      if (syncing) return;
      const now = Date.now();
      if (now - lastSync < 250) return;
      if (Math.abs(src.currentTime - exp.currentTime) > 0.3) {
        lastSync = now; syncing = true;
        src.currentTime = exp.currentTime; syncing = false;
      }
    });
    const note = $("compareSyncNote");
    const report = () => {
      if (!note) return;
      if (src.duration && exp.duration && Math.abs(src.duration - exp.duration) > 0.5) {
        note.textContent = `Nguồn ${src.duration.toFixed(1)}s, bản xuất ${exp.duration.toFixed(1)}s — đồng bộ theo thời gian; hai video không khóa khung hình tuyệt đối, có thể lệch nhỏ khi tua.`;
      } else {
        note.textContent = "Đồng bộ theo thời gian (play/pause/seek); hai video không khóa khung hình tuyệt đối.";
      }
    };
    src.addEventListener("loadedmetadata", report);
    exp.addEventListener("loadedmetadata", report);
    const range = $("compareRange");
    if (range) range.addEventListener("input", () => compareWipeAt(Number(range.value)));
    const divider = $("compareDivider");
    const wipe = $("compareWipe");
    if (divider && wipe) {
      divider.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        const move = (ev) => {
          const r = wipe.getBoundingClientRect();
          compareWipeAt(((ev.clientX - r.left) / r.width) * 100);
        };
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      });
    }
  }
  const _showSource = showSourcePreview;
  showSourcePreview = function (medium) { lastSourceMediaId = medium.id; return _showSource(medium); };
  function setCompare(on) {
    compareOn = on;
    const wrap = $("compareWrap"), video = $("preview"), img = $("previewImage");
    if (!wrap) return;
    if (!on) { wrap.hidden = true; video.hidden = false; return; }
    const srcId = lastSourceMediaId || previewMediaId ||
      (selectedId && findItem(selectedId) ? findItem(selectedId).item.media : null);
    const src = srcId ? project.media.find((m) => m.id === srcId) : null;
    if (!src) { compareOn = false; setStatus("Chưa có file nguồn nào để so sánh — bấm vào một clip hoặc file media trước.", true); return; }
    if (!lastExportPath) { compareOn = false; setStatus("Chưa có bản xuất nào để so sánh — xuất bản nháp trước.", true); return; }
    video.hidden = true; img.hidden = true;
    $("previewCompareSource").src = "/api/media/" + encodeURIComponent(src.id);
    $("previewCompareExport").src = "/api/preview?" + Date.now();
    wrap.hidden = false;
    compareWireSync(); compareWipeAt(50);
    setStatus("So sánh wipe: trái vạch chia = file nguồn (Before), phải vạch chia = bản xuất gần nhất (After). Kéo vạch chia hoặc thanh trượt để so sánh; hai video đồng bộ theo thời gian, không khóa khung hình tuyệt đối.");
  }
  const cmpModeBtn = $("btnPreviewCompareMode");
  if (cmpModeBtn) cmpModeBtn.addEventListener("click", () => setCompare(!compareOn));
  if (cmpBtn) cmpBtn.addEventListener("click", () => setCompare(!compareOn));
  // Source viewer In/Out + Insert at playhead (original E/Q workflow).
  function sourceMediaFps() {
    const medium = project.media.find((m) => m.id === $("sourceMedia").value);
    if (!medium) return fps();
    if (Array.isArray(medium.fps)) return medium.fps[0] / medium.fps[1];
    return medium.fps || fps();
  }
  function markSource(which) {
    const video = $("preview");
    if (!video || video.hidden || isNaN(video.duration)) { setStatus("Chưa có video nguồn đang phát để đánh dấu.", true); return; }
    const frame = Math.round(video.currentTime * sourceMediaFps());
    if (which === "in") $("sourceIn").value = frame; else $("sourceOut").value = frame;
    $("sourceRangeStatus").textContent = `Đã đánh dấu ${which === "in" ? "In" : "Out"} = ${frame} frames.`;
  }
  const markInBtn = $("btnSourceMarkIn"), markOutBtn = $("btnSourceMarkOut");
  if (markInBtn) markInBtn.addEventListener("click", () => markSource("in"));
  if (markOutBtn) markOutBtn.addEventListener("click", () => markSource("out"));
  async function placeSource(overwrite) {
    const media = $("sourceMedia").value;
    const inF = Number($("sourceIn").value), outF = Number($("sourceOut").value);
    if (!media) { setStatus("Chọn một file nguồn trước.", true); return; }
    if (!(outF > inF)) { setStatus("Out phải lớn hơn In.", true); return; }
    try {
      const data = await api("/api/project", { op: overwrite ? "source_overwrite" : "source_insert", media, in: inF, out: outF, at: playheadFrame });
      await load();
      if (data.result && data.result.id) selectClipAndPreview(data.result.id);
      setStatus(overwrite ? `Đã ghi đè đoạn ${inF}–${outF} frames vào playhead.` : `Đã chèn đoạn ${inF}–${outF} frames vào playhead.`);
    } catch (err) { setStatus(err.message, true); }
  }
  const srcInsertBtn = $("btnSourceInsert");
  if (srcInsertBtn) srcInsertBtn.addEventListener("click", () => placeSource(false));
  const srcOverwriteBtn = $("btnSourceOverwrite");
  if (srcOverwriteBtn) srcOverwriteBtn.addEventListener("click", () => placeSource(true));
  document.addEventListener("keydown", (e) => {
    // Phase 2: Ctrl+letter must reach the Ctrl-shortcut handler,
    // not the single-letter source shortcuts.
    if (e.ctrlKey || e.metaKey) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    // Original shortcuts, from UIAction.swift: I = Mark In, O = Mark Out,
    // E = Insert source range at playhead, Q = Overwrite at playhead.
    if (e.key === "i" || e.key === "I") markSource("in");
    if (e.key === "o" || e.key === "O") markSource("out");
    if (e.key === "e" || e.key === "E") placeSource(false);
    if (e.key === "q" || e.key === "Q") placeSource(true);
  });
  // Khít khoảng trống trên track Main.
  const closeGapsBtn = $("tlCloseGaps");
  if (closeGapsBtn) closeGapsBtn.addEventListener("click", async () => {
    try {
      const data = await api("/api/project", { op: "close_gaps" });
      setStatus(`Đã khít khoảng trống: ${data.result.moved.length} clip đã dịch chuyển.`);
      await load();
    } catch (err) { setStatus(err.message, true); }
  });
  // Colour reset (sliders + LUT).
  const colorResetBtn = $("btnColorReset");
  if (colorResetBtn) colorResetBtn.addEventListener("click", async () => {
    if (!selectedId) { setStatus("Chọn một clip trước.", true); return; }
    try {
      await api("/api/project", { op: "set_color", item: selectedId, clear_eq: true, clear_lut: true });
      setStatus("Đã đặt lại màu của clip (xóa eq + LUT).");
      await load(); renderInspector();
    } catch (err) { setStatus(err.message, true); }
  });
  // Project switcher (welcome/recent-projects equivalent): list, open, create.
  async function refreshProjectList() {
    try {
      const res = await fetch("/api/projects"); const data = await res.json();
      const sel = $("projectSelect"); if (!sel) return;
      sel.innerHTML = (data.projects || []).map((p) => `<option value="${p.folder}" ${p.current ? "selected" : ""}>${p.name} (${p.folder})</option>`).join("");
    } catch (err) { /* list failure never breaks the editor */ }
  }
  const openProjBtn = $("btnProjectOpen");
  if (openProjBtn) openProjBtn.addEventListener("click", async () => {
    const folder = $("projectSelect").value;
    if (!folder) { setStatus("Chọn một project trong danh sách trước.", true); return; }
    try { await api("/api/project/open", { folder }); await load(); await refreshProjectList(); setStatus("Đã mở project: " + folder); }
    catch (err) { setStatus(err.message, true); }
  });
  const createProjBtn = $("btnProjectCreate");
  if (createProjBtn) createProjBtn.addEventListener("click", async () => {
    const name = $("projectNewName").value.trim();
    if (!name) { setStatus("Nhập tên project mới trước.", true); return; }
    try { await api("/api/project/create", { name }); await load(); await refreshProjectList(); setStatus("Đã tạo và mở project: " + name); }
    catch (err) { setStatus(err.message, true); }
  });
  refreshProjectList();
  const playBtn = $("btnPreviewPlay"), backBtn = $("btnPreviewBack");
  if (playBtn) playBtn.addEventListener("click", () => {
    const img = $("previewImage");
    if (img && !img.hidden) { setStatus("Đây là ảnh tĩnh — chỉ xem, không phát được.", true); return; }
    const v = $("preview"); if (!v || !v.src) { setStatus("Chưa có gì để phát — bấm vào một clip/media, hoặc xuất bản nháp trước.", true); return; }
    if (v.paused) v.play(); else v.pause();
  });
  if (backBtn) backBtn.addEventListener("click", () => {
    // Round 19: "Về đầu" always means timeline frame 0. The old
    // code jumped to the selected source item's start in source
    // mode, which read as "goes to 226.79s instead of 0" when the
    // selected clip was the second one.
    playheadFrame = 0;
    seekPreviewToPlayhead(); renderTracks();
  });

  // Timeline toolbar: Add Layer, Sections, Ask agent, Export report
  const layerBtn = $("tlAddLayer");
  if (layerBtn) layerBtn.addEventListener("click", async () => {
    const n = project.tracks.filter((t) => t.kind === "video").length + 1;
    try { await api("/api/project", { op: "add_track", kind: "video", role: "overlay", name: "Layer " + n }); setStatus("Đã thêm layer."); await load(); }
    catch (err) { setStatus(err.message, true); }
  });
  const secBtn = $("tlSections");
  if (secBtn) secBtn.addEventListener("click", () => {
    // Round 19: Sections is now a real toggle (was status-only):
    // it shows/hides the section markers on the ruler, flips
    // aria-pressed + the active style, and always reports its state.
    const on = secBtn.getAttribute("aria-pressed") !== "true";
    secBtn.setAttribute("aria-pressed", on ? "true" : "false");
    secBtn.classList.toggle("active", on);
    window.__showSections = on;
    renderTracks();
    const ms = project.markers || [];
    setStatus(on
      ? (ms.length ? "Đã bật Sections (marker): " + ms.map((m) => `${(m.at / fps()).toFixed(2)}s ${m.text}`).join(" | ") : "Đã bật Sections — chưa có marker nào.")
      : "Đã tắt Sections.");
  });
  const askBtn = $("tlAskAgent");
  if (askBtn) askBtn.addEventListener("click", () => focusAgent(selectedId ? "Help with the selected clip" : "Help with this project"));
  const reportBtn = $("btnExportReport");
  if (reportBtn) reportBtn.addEventListener("click", () => {
    const tab = document.querySelector('[data-tab="ai"]'); if (tab) tab.click();
    const r = $("btnReview"); if (r) r.click();
    setStatus("Đã làm mới Export report (panel Review).");
  });
})();

/* Finishing batch wiring: ratio pickers, Settings gear, source
   playback controls. Guarded lookups only — a missing element
   never breaks the editor above. */
(function finishBatchWiring() {
  const preset = $("formatPreset");
  if (preset) preset.addEventListener("change", () => applyPresetValue(preset.value));
  const sPreset = $("settingsFormatPreset");
  if (sPreset) sPreset.addEventListener("change", () => applyPresetValue(sPreset.value));
  const customBtn = $("btnFormatCustom");
  if (customBtn) customBtn.addEventListener("click", () => applyFormat($("settingsFormatWidth").value, $("settingsFormatHeight").value));
  const panel = $("settingsPanel");
  const gear = $("btnSettings"), close = $("btnSettingsClose");
  if (gear && panel) gear.addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) fillSettingsInfo(); });
  if (close && panel) close.addEventListener("click", () => { panel.hidden = true; });
  const fitBtn = $("btnSettingsFit"), realFit = $("btnPreviewFit");
  if (fitBtn && realFit) fitBtn.addEventListener("click", () => realFit.click());
  const safeBtn = $("btnSettingsSafe"), realSafe = $("btnPreviewSafe");
  if (safeBtn && realSafe) safeBtn.addEventListener("click", () => realSafe.click());
  const collapseBox = $("settingsAgentCollapsed");
  if (collapseBox) collapseBox.addEventListener("change", () => {
    localStorage.setItem("vibeedit_agent_collapsed", collapseBox.checked ? "1" : "0");
    applyAgentCollapsePref();
  });
  // Round 18: rail "AI Agent" button toggles the same collapse state
  // the Settings checkbox owns, so the two controls can never drift
  // apart. Default (no stored pref) is shown, so the first press
  // hides the dock and the next press shows it again.
  const agentToggle = $("btnAgentToggle");
  if (agentToggle) agentToggle.addEventListener("click", () => {
    const collapsed = localStorage.getItem("vibeedit_agent_collapsed") === "1";
    localStorage.setItem("vibeedit_agent_collapsed", collapsed ? "0" : "1");
    applyAgentCollapsePref();
  });
  // Round 18 step 3: the header toggle drives the same drawer state,
  // the backdrop and Esc close it, the inspector toggle hides the
  // Details column (workbench drops to two tracks).
  const agentToggleTop = $("btnAgentToggleTop");
  if (agentToggleTop) agentToggleTop.addEventListener("click", () => {
    const collapsed = localStorage.getItem("vibeedit_agent_collapsed") === "1";
    localStorage.setItem("vibeedit_agent_collapsed", collapsed ? "0" : "1");
    applyAgentCollapsePref();
  });
  const agentBackdrop = $("agentBackdrop");
  if (agentBackdrop) agentBackdrop.addEventListener("click", () => {
    localStorage.setItem("vibeedit_agent_collapsed", "1");
    applyAgentCollapsePref();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const col = $("agentCol");
    if (col && col.classList.contains("open")) {
      localStorage.setItem("vibeedit_agent_collapsed", "1");
      applyAgentCollapsePref();
    }
  });
  const inspToggle = $("btnInspectorToggle");
  if (inspToggle) inspToggle.addEventListener("click", toggleInspectorColumn);
  const detailsClose = $("btnDetailsClose");
  if (detailsClose) detailsClose.addEventListener("click", toggleInspectorColumn);
  const agentClose = $("btnAgentClose");
  if (agentClose) agentClose.addEventListener("click", () => {
    localStorage.setItem("vibeedit_agent_collapsed", "1");
    applyAgentCollapsePref();
  });
  applyAgentCollapsePref();
  syncInspectorDrawer();
  const expBtn = $("btnPreviewExport");
  if (expBtn) expBtn.addEventListener("click", async () => {
    previewMode = "export"; previewMediaId = null; previewItemId = null;
    await load();
    setStatus("Đang xem: bản xuất gần nhất. Muốn xem file gốc thì bấm vào clip hoặc file media.");
  });
})();

/* Code-gap batch 2 wiring (guarded lookups only): export presets,
   review workflow, speed curve / reverse / freeze, library, brand,
   plugin list/enable/disable, welcome panel. */
(function gapBatch2Wiring() {
  const needClip = () => { if (!selectedId) { setStatus("Hãy chọn một clip trên timeline trước.", true); return false; } return true; };
  const sc = $("speedCurveForm");
  if (sc) sc.addEventListener("submit", async (e) => {
    e.preventDefault(); if (!needClip()) return;
    try { const d = await post({ op: "speed_curve", item: selectedId, preset: $("speedCurvePreset").value });
      $("speedCurveResult").textContent = `Đã áp dụng ${d.result.preset} thành ${d.result.segments.length} đoạn, tốc độ: ${d.result.speeds.join(", ")}.`; }
    catch (err) { $("speedCurveResult").textContent = `Áp dụng đường cong thất bại: ${err.message}`; }
  });
  const rev = $("btnClipReverse");
  if (rev) rev.addEventListener("click", async () => {
    if (!needClip()) return;
    try { await post({ op: "clip_reverse", item: selectedId, reverse: true }); setStatus("Clip sẽ phát ngược khi xuất (cờ reverse đã lưu)."); }
    catch (err) { setStatus(err.message, true); }
  });
  const frz = $("btnClipFreeze");
  if (frz) frz.addEventListener("click", async () => {
    if (!needClip()) return;
    try { const d = await post({ op: "freeze_clip", item: selectedId, frames: 30 });
      setStatus(`Đã thêm đoạn đóng băng ${d.result.dur} khung hình sau clip đang chọn.`); }
    catch (err) { setStatus(err.message, true); }
  });
  const expP = $("btnExportPreset");
  if (expP) expP.addEventListener("click", async () => {
    const preset = $("exportPresetSelect").value; if (!preset) { setStatus("Hãy chọn một preset xuất trước.", true); return; }
    // Round 22: same background job flow as doExport.
    await runExportJob({ preset: "full", export_preset: preset }, "preset " + preset);
  });
  const rr = $("btnReviewRun"), ra = $("btnReviewAccept"), rv = $("btnReviewVerify");
  const showReview = (d) => { $("reviewWorkflowResult").textContent = `Review: trạng thái ${d.result.status}, số vấn đề ${d.result.issue_count}${d.result.previous_issue_count !== undefined ? ` (lần trước ${d.result.previous_issue_count}, thay đổi: ${d.result.issue_count_changed ? "có" : "không"})` : ""}${d.result.accepted_rev !== undefined ? `, đã chấp nhận ở rev ${d.result.accepted_rev}` : ""}.`; };
  if (rr) rr.addEventListener("click", async () => { try { showReview(await post({ op: "review_run" })); } catch (err) { $("reviewWorkflowResult").textContent = err.message; } });
  if (ra) ra.addEventListener("click", async () => { try { showReview(await post({ op: "review_accept" })); } catch (err) { $("reviewWorkflowResult").textContent = err.message; } });
  if (rv) rv.addEventListener("click", async () => { try { showReview(await post({ op: "review_verify" })); } catch (err) { $("reviewWorkflowResult").textContent = err.message; } });
  const renderLibrary = async () => {
    const box = $("libraryList"); if (!box) return;
    try { const d = await post({ op: "library_list" });
      box.innerHTML = (d.result.items || []).map((e) => `<div class="library-item">${e.name} <button type="button" class="secondary" data-library-place="${e.id}">Đặt lên timeline</button> <button type="button" class="secondary" data-library-remove="${e.id}">Xóa</button></div>`).join("") || "Thư viện trống.";
      box.querySelectorAll("[data-library-place]").forEach((b) => b.addEventListener("click", async () => { try { await post({ op: "library_place", entry: b.dataset.libraryPlace }); setStatus("Đã đặt mục thư viện lên timeline."); await renderLibrary(); } catch (err) { setStatus(err.message, true); } }));
      box.querySelectorAll("[data-library-remove]").forEach((b) => b.addEventListener("click", async () => { try { await post({ op: "library_remove", entry: b.dataset.libraryRemove }); await renderLibrary(); } catch (err) { setStatus(err.message, true); } }));
    } catch (err) { box.textContent = err.message; }
  };
  const la = $("btnLibraryAdd");
  if (la) la.addEventListener("click", async () => {
    if (!needClip()) return;
    try { await post({ op: "library_add", item: selectedId }); await renderLibrary(); setStatus("Đã lưu clip đang chọn vào thư viện."); }
    catch (err) { setStatus(err.message, true); }
  });
  const bf = $("brandForm");
  if (bf) bf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const colours = $("brandColours").value.split(",").map((c) => c.trim()).filter(Boolean);
    try { const d = await post({ op: "brand_set", colours, logo_media: $("brandLogoMedia").value.trim() || null });
      $("brandResult").textContent = `Đã lưu thương hiệu: màu ${JSON.stringify(d.result.colours || [])}, logo ${d.result.logo_media || "(không có)"}.`; }
    catch (err) { $("brandResult").textContent = `Lưu thương hiệu thất bại: ${err.message}`; }
  });
  const renderPlugins = async () => {
    const box = $("pluginList"); if (!box) return;
    try { const res = await fetch("/api/plugins"); const d = await res.json();
      box.innerHTML = (d.plugins || []).filter((p) => p.name !== "_errors").map((p) => `<div class="plugin-item">${p.name} — ${p.description} (${p.enabled ? "đang bật" : "đang tắt"}) <button type="button" class="secondary" data-plugin-toggle="${p.name}" data-plugin-enable="${p.enabled ? "0" : "1"}">${p.enabled ? "Tắt" : "Bật"}</button></div>`).join("") || "Không có plugin nào.";
      box.querySelectorAll("[data-plugin-toggle]").forEach((b) => b.addEventListener("click", async () => { try { await post({ op: b.dataset.pluginEnable === "1" ? "plugin_enable" : "plugin_disable", plugin: b.dataset.pluginToggle }); await renderPlugins(); } catch (err) { setStatus(err.message, true); } }));
    } catch (err) { box.textContent = err.message; }
  };
  const pr = $("btnPluginReload");
  if (pr) pr.addEventListener("click", renderPlugins);
  renderLibrary(); renderPlugins();
  // Welcome panel
  const wp = $("welcomePanel");
  const loadWelcome = async () => {
    const box = $("welcomeRecent"); if (!box) return;
    try { const res = await fetch("/api/projects"); const d = await res.json();
      const rec = d.recent || [];
      box.innerHTML = rec.length ? rec.map((r) => `<div class="welcome-item">${r.folder} <button type="button" class="secondary" data-welcome-open="${r.folder}">Mở</button> <button type="button" class="secondary" data-welcome-remove="${r.folder}">Xóa khỏi gần đây</button></div>`).join("") : "Chưa có project gần đây nào — hãy tạo project mới.";
      box.querySelectorAll("[data-welcome-open]").forEach((b) => b.addEventListener("click", async () => { try { await api("/api/project/open", { folder: b.dataset.welcomeOpen }); await load(); wp.hidden = true; } catch (err) { $("welcomeStatus").textContent = err.message; } }));
      box.querySelectorAll("[data-welcome-remove]").forEach((b) => b.addEventListener("click", async () => { try { await api("/api/recent/remove", { folder: b.dataset.welcomeRemove }); await loadWelcome(); } catch (err) { $("welcomeStatus").textContent = err.message; } }));
    } catch (err) { box.textContent = err.message; }
  };
  const wb = $("btnWelcome");
  if (wb && wp) wb.addEventListener("click", async () => { wp.hidden = !wp.hidden; if (!wp.hidden) await loadWelcome(); });
  const wc = $("btnWelcomeClose");
  if (wc && wp) wc.addEventListener("click", () => { wp.hidden = true; });
  const wo = $("btnWelcomeOpen");
  if (wo) wo.addEventListener("click", async () => { const sel = $("projectSelect"); if (!sel || !sel.value) { $("welcomeStatus").textContent = "Hãy chọn một project trước."; return; } try { await api("/api/project/open", { folder: sel.value }); await load(); wp.hidden = true; } catch (err) { $("welcomeStatus").textContent = err.message; } });
  // Round 22: open a project by absolute path (e.g. a second project
  // stored outside projects/). The picker only lists projects_root,
  // so without this there was no UI path to such a project at all;
  // the server side already accepts absolute paths (round 22).
  const wop = $("btnWelcomeOpenPath");
  if (wop) wop.addEventListener("click", async () => { const p = $("welcomePath"); if (!p || !p.value.trim()) { $("welcomeStatus").textContent = "Nhập đường dẫn thư mục project trước."; return; } try { await api("/api/project/open", { folder: p.value.trim() }); await load(); await refreshProjectList(); wp.hidden = true; } catch (err) { $("welcomeStatus").textContent = err.message; } });
  const wcr = $("btnWelcomeCreate");
  if (wcr) wcr.addEventListener("click", () => { const btn = $("btnProjectCreate"); if (btn) btn.click(); });
  const wr = $("btnWelcomeReveal");
  if (wr) wr.addEventListener("click", async () => { try { const d = await api("/api/reveal", { folder: $("projectSelect") ? $("projectSelect").value : "" }); $("welcomeStatus").textContent = `Đã mở thư mục: ${d.path}`; } catch (err) { $("welcomeStatus").textContent = `Reveal thất bại: ${err.message}`; } });
  const wcp = $("btnWelcomeCopyPath");
  if (wcp) wcp.addEventListener("click", async () => { try { const res = await fetch("/api/projects"); const d = await res.json(); await navigator.clipboard.writeText(d.current || ""); $("welcomeStatus").textContent = "Đã sao chép đường dẫn project hiện tại."; } catch (err) { $("welcomeStatus").textContent = `Copy thất bại: ${err.message}`; } });
})();

/* Round 3 wiring: knowledge/skills, vision, plugin install/download and
   the magnetic toggle. Every control is guarded (the panel may be hidden)
   and every handler calls a real server op — no dead buttons. Follows the
   gapBatch2Wiring pattern above. */
(function round3Wiring() {
  const out = (id, text) => { const el = $(id); if (el) el.textContent = text; };
  // Round 22: panel actions also overwrite the status toast.
  const show = async (fn) => { try { await fn(); setStatus("Xong — kết quả ở panel Knowledge."); } catch (err) { out("knowledgeResult", err.message); setStatus(err.message, true); } };
  const ks = $("btnKnowledgeSkills");
  if (ks) ks.addEventListener("click", () => show(async () => {
    const d = await post({ op: "skills_list" });
    const list = $("knowledgeList");
    const skills = d.result.skills || d.skills || [];
    if (list) list.innerHTML = skills.map((s) => `<li>${s.id || s.name || JSON.stringify(s)}${s.title ? " — " + s.title : ""}${s.enabled === false ? " (disabled)" : ""}</li>`).join("") || "<li>No skills found.</li>";
    out("knowledgeResult", `Skills: ${skills.length}.`);
  }));
  const kl = $("btnKnowledgeLessons");
  if (kl) kl.addEventListener("click", () => show(async () => {
    const d = await post({ op: "knowledge", action: "lessons" });
    const list = $("knowledgeList");
    const lessons = d.result.lessons || [];
    if (list) list.innerHTML = lessons.map((l) => `<li>${l.title || l.id || ""} — ${(l.text || "").slice(0, 120)}</li>`).join("") || "<li>No lessons yet.</li>";
    out("knowledgeResult", `Lessons: ${lessons.length}.`);
  }));
  const kg = $("btnKnowledgeGet");
  if (kg) kg.addEventListener("click", () => show(async () => {
    const id = $("knowledgeId").value.trim(); if (!id) { out("knowledgeResult", "Enter a skill / lesson id first."); return; }
    try {
      const d = await post({ op: "skills_get", skill: id });
      out("knowledgeResult", `Skill ${id}: ${JSON.stringify(d.result.skill || d.result)}`);
    } catch (err) {
      const d = await post({ op: "knowledge", action: "get", lesson: id });
      out("knowledgeResult", `Lesson ${id}: ${JSON.stringify(d.result)}`);
    }
  }));
  const kd = $("btnKnowledgeSkillDisable");
  if (kd) kd.addEventListener("click", () => show(async () => {
    const id = $("knowledgeId").value.trim(); if (!id) { out("knowledgeResult", "Enter a skill id first."); return; }
    await post({ op: "skills_disable", skill: id }); out("knowledgeResult", `Skill ${id} disabled.`);
  }));
  const ke = $("btnKnowledgeSkillEnable");
  if (ke) ke.addEventListener("click", () => show(async () => {
    const id = $("knowledgeId").value.trim(); if (!id) { out("knowledgeResult", "Enter a skill id first."); return; }
    await post({ op: "skills_enable", skill: id }); out("knowledgeResult", `Skill ${id} enabled.`);
  }));
  const kr = $("btnKnowledgeSkillRemove");
  if (kr) kr.addEventListener("click", () => show(async () => {
    const id = $("knowledgeId").value.trim(); if (!id) { out("knowledgeResult", "Enter a skill id first."); return; }
    const confirmBox = $("knowledgeRemoveConfirm");
    if (!confirmBox || !confirmBox.checked) { out("knowledgeResult", "Tick the confirm checkbox first — skill remove is irreversible except via git."); return; }
    await post({ op: "skills_remove", skill: id, confirm: true }); out("knowledgeResult", `Skill ${id} removed.`);
  }));
  const ksf = $("knowledgeSaveForm");
  if (ksf) ksf.addEventListener("submit", (e) => { e.preventDefault(); show(async () => {
    const d = await post({ op: "skills_save", skill: $("knowledgeSaveId").value.trim(), title: $("knowledgeSaveTitle").value, body: $("knowledgeSaveBody").value, overwrite: !!$("knowledgeSaveOverwrite").checked });
    out("knowledgeResult", `Skill saved: ${JSON.stringify(d.result)}`);
  }); });
  const kp = $("btnKnowledgePropose");
  if (kp) kp.addEventListener("click", () => show(async () => {
    const d = await post({ op: "skills_propose", skill: $("knowledgeSaveId").value.trim(), title: $("knowledgeSaveTitle").value, body: $("knowledgeSaveBody").value });
    out("knowledgeResult", `Proposal draft saved (not an active skill): ${JSON.stringify(d.result)}`);
  }));
  const klf = $("knowledgeLessonForm");
  if (klf) klf.addEventListener("submit", (e) => { e.preventDefault(); show(async () => {
    const d = await post({ op: "knowledge", action: "add_lesson", text: $("knowledgeLessonText").value, title: $("knowledgeLessonTitle").value || null });
    out("knowledgeResult", `Lesson added: ${JSON.stringify(d.result)}`);
  }); });
  const vision = async (op, extra) => {
    const media = $("visionMedia") ? $("visionMedia").value : "";
    // Round 22: every panel action also overwrites the status
    // toast, so it never keeps a stale message from an earlier
    // panel (the toast itself still auto-hides after 4s).
    if (!media) { out("visionResult", "Choose a media item first."); setStatus("Chọn một media trước.", true); return; }
    try { const d = await post(Object.assign({ op, media }, extra || {})); out("visionResult", JSON.stringify(d.result, null, 2)); setStatus(`Vision xong (${op}) — kết quả ở panel Vision.`); }
    catch (err) { out("visionResult", err.message); setStatus(err.message, true); }
  };
  const vo = $("btnVisionOcr"); if (vo) vo.addEventListener("click", () => vision("vision_ocr"));
  const vf = $("btnVisionFaces"); if (vf) vf.addEventListener("click", () => vision("vision_faces"));
  const vc = $("btnVisionCutout"); if (vc) vc.addEventListener("click", () => vision("vision_cutout"));
  const vm = $("btnVisionCutoutModel"); if (vm) vm.addEventListener("click", () => {
    const model = $("visionModelPath") ? $("visionModelPath").value.trim() : "";
    if (!model) { out("visionResult", "Enter a user-supplied ONNX model path first — no model is bundled."); return; }
    vision("vision_cutout_model", { model });
  });
  const pif = $("pluginInstallForm");
  if (pif) pif.addEventListener("submit", (e) => { e.preventDefault(); (async () => {
    try { const d = await post({ op: "plugin_install", source: $("pluginInstallSource").value.trim(), source_label: $("pluginInstallLabel").value.trim() || null });
      out("pluginInstallResult", `Installed (disabled by default): ${JSON.stringify(d.result)}`); }
    catch (err) { out("pluginInstallResult", err.message); }
  })(); });
  const pdf = $("pluginDownloadForm");
  if (pdf) pdf.addEventListener("submit", (e) => { e.preventDefault(); (async () => {
    try {
      if (!$("pluginDownloadConfirm").checked) { out("pluginInstallResult", "Tick the confirm checkbox first — download only, never installs."); return; }
      const d = await post({ op: "plugin_download", url: $("pluginDownloadUrl").value.trim(), confirm: true });
      out("pluginInstallResult", `Downloaded only (not installed): ${JSON.stringify(d.result)}`);
    } catch (err) { out("pluginInstallResult", err.message); }
  })(); });
  const mg = $("tlMagnetic");
  // Round 18: icon toggle button — the pressed state flips only
  // after the server confirms, so the UI can never disagree with
  // the project about whether magnetic is on.
  if (mg) mg.addEventListener("click", async () => {
    const on = mg.getAttribute("aria-pressed") !== "true";
    try { await post({ op: "magnetic_set", enabled: on }); mg.setAttribute("aria-pressed", on ? "true" : "false"); mg.classList.toggle("active", on); setStatus(on ? "Đã bật Magnetic Main." : "Đã tắt Magnetic Main."); }
    catch (err) { setStatus(err.message, true); }
  });
})();

/* Round 4: in-app voiceover recording (browser MediaRecorder).
   The browser owns microphone permission: getUserMedia prompts the
   user, and a denial (or an insecure context, or no microphone)
   surfaces as a clear status message — nothing is recorded or
   faked. A finished take is uploaded to /api/voiceover/record,
   stored as real project media, and selected in the voiceover form
   so the existing form places it on the Voiceover track. No real
   microphone exists on a headless VM, so mic recording itself can
   only be verified in a real browser on Windows. */
(function round4Recording() {
  const recBtn = $("btnVoiceRecord"), stopBtn = $("btnVoiceRecordStop"),
    status = $("voiceRecordStatus"), preview = $("voiceRecordPreview");
  if (!recBtn) return;
  const say = (text, isErr) => {
    if (status) status.textContent = text;
    if (isErr) setStatus(text, true); else setStatus(text);
  };
  let recorder = null, chunks = [], stream = null, mimeType = "";
  recBtn.addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say("Trình duyệt này không hỗ trợ ghi âm (cần getUserMedia, thường là Chrome/Edge qua localhost hoặc HTTPS).", true); return;
    }
    if (typeof MediaRecorder === "undefined") {
      say("Trình duyệt này không hỗ trợ MediaRecorder.", true); return;
    }
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", ""];
    mimeType = candidates.find((m) => !m || (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m))) || "";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      say("Không ghi được: trình duyệt đã từ chối quyền micro hoặc không tìm thấy micro (" + (err && err.name ? err.name : err) + "). Hãy cho phép quyền micro rồi bấm ghi lại.", true); return;
    }
    chunks = [];
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch (err) {
      say("Không khởi động được MediaRecorder: " + err.message, true); return;
    }
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = async () => {
      if (stream) stream.getTracks().forEach((t) => t.stop());
      stream = null;
      if (!chunks.length) { say("Bản ghi trống — hãy giữ nút ghi, nói, rồi bấm dừng.", true); return; }
      const ext = mimeType.includes("mp4") ? "mp4" : mimeType.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      const fd = new FormData();
      fd.append("file", blob, "voiceover-recording." + ext);
      say("Đang tải bản ghi lên project…");
      try {
        const res = await fetch("/api/voiceover/record", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
        say(`Đã lưu bản ghi: ${data.media.path} (media ${data.media.id}). Chọn form bên dưới để đặt lên track Voiceover.`);
        if (preview) { preview.src = "/api/media/" + encodeURIComponent(data.media.id); preview.hidden = false; }
        await load();
        const vm = $("voiceMedia"); if (vm) vm.value = data.media.id;
      } catch (err) { say("Tải bản ghi thất bại: " + err.message, true); }
    };
    recorder.start();
    recBtn.hidden = true; if (stopBtn) stopBtn.hidden = false;
    say("Đang ghi… bấm ■ Dừng thu để dừng.");
  });
  if (stopBtn) stopBtn.addEventListener("click", () => {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recBtn.hidden = false; stopBtn.hidden = true;
  });
})();

/* Round 14: inspector tabs, agent provider tabs + one-line MCP status, copyable MCP command. */
(function round14Shell() {
  function activateInsp(tab) {
    document.querySelectorAll("[data-insp-tab]").forEach((b) => b.classList.toggle("active", b.dataset.inspTab === tab));
    document.querySelectorAll("[data-insp-pane]").forEach((p) => { p.hidden = p.dataset.inspPane !== tab; });
  }
  $("inspTabVideo").addEventListener("click", () => activateInsp("video"));
  $("inspTabAudio").addEventListener("click", () => activateInsp("audio"));
  $("inspTabText").addEventListener("click", () => activateInsp("text"));
  $("inspTabColor").addEventListener("click", () => activateInsp("color"));
  $("inspTabSpeed").addEventListener("click", () => activateInsp("speed"));
  $("btnDetailsModify").addEventListener("click", () => { const s = $("btnSettings"); if (s) s.click(); });
  function syncAgentTabs(value) {
    document.querySelectorAll("[data-agent-tab]").forEach((b) => b.classList.toggle("active", b.dataset.agentTab === value));
    const sel = document.getElementById("agentProvider");
    if (sel) sel.value = value;
  }
  async function refreshAgentStatus() {
    const line = document.getElementById("agentStatusLine");
    if (!line) return;
    const sel = document.getElementById("agentProvider");
    if (sel && sel.value === "ollama") {
      line.textContent = "Ollama chưa kết nối trong app — dùng agent ngoài qua MCP.";
      return;
    }
    try {
      const d = await api("/api/agent-status");
      // Round 22: fill both command displays with the server's real
      // MCP command (absolute paths + .venv python); the copy button
      // copies #agentMcpCommand, so it now copies the real command.
      if (d && d.mcp_command) {
        const code = document.getElementById("agentMcpCommand");
        if (code) code.textContent = d.mcp_command;
        const dock = document.getElementById("agentDockCommand");
        if (dock) dock.textContent = d.mcp_command;
      }
      if (d && d.connected && d.last_seen) {
        const when = new Date(d.last_seen * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
        line.textContent = `Đã kết nối agent ngoài qua MCP (hoạt động gần nhất ${when}).`;
      } else {
        line.textContent = "Chưa kết nối agent ngoài — chạy lệnh MCP để kết nối.";
      }
    } catch (err) {
      line.textContent = "Chưa kết nối agent ngoài — chạy lệnh MCP để kết nối.";
    }
  }
  $("agentTabMcp").addEventListener("click", () => { syncAgentTabs("mcp"); refreshAgentStatus(); });
  $("agentTabOllama").addEventListener("click", () => { syncAgentTabs("ollama"); refreshAgentStatus(); });
  const sel = document.getElementById("agentProvider");
  if (sel) sel.addEventListener("change", () => { syncAgentTabs(sel.value); refreshAgentStatus(); });
  $("btnAgentCopyMcp").addEventListener("click", async () => {
    const code = document.getElementById("agentMcpCommand");
    const text = code ? code.textContent : "python windows\\vibeedit.py mcp <project-folder>";
    try { await navigator.clipboard.writeText(text); setStatus("Đã sao chép lệnh MCP."); }
    catch (err) { setStatus("Không sao chép được tự động — hãy bôi đen lệnh MCP rồi Ctrl+C.", true); }
  });
  refreshAgentStatus();
  setInterval(refreshAgentStatus, 60000);
})();

(function previewSync() {
  // Preview -> timeline (the other direction of the two-way sync).
  // timeupdate fires while playing; seeked fires on native-control
  // seeks. A <=1-frame difference is treated as echo from our own
  // seek (rounding) and only refreshes the caption, never re-renders.
  const video = $("preview");
  if (!video) return;
  function syncPlayheadFromPreview() {
    if (!project || video.hidden || !video.src) return;
    let t;
    if (previewMode === "source" && previewItemId) {
      const found = findItem(previewItemId);
      if (!found) return;
      const medium = project.media.find((m) => m.id === found.item.media);
      const mediaFps = medium && Array.isArray(medium.fps) ? medium.fps[0] / medium.fps[1] : (medium && medium.fps ? medium.fps : fps());
      t = sourceToTimelineSeconds(video.currentTime, found.item.at / fps(), (found.item.in || 0) / mediaFps, found.item.speed || 1, found.item.dur / fps());
    } else {
      t = video.currentTime;
    }
    const newFrame = Math.round(t * fps());
    if (Math.abs(newFrame - playheadFrame) <= 1) { renderPreviewCaption(); return; }
    playheadFrame = newFrame;
    $("playheadLabel").textContent = (playheadFrame / fps()).toFixed(2) + "s";
    renderTracks();
    renderPreviewCaption();
  }
  video.addEventListener("timeupdate", syncPlayheadFromPreview);
  video.addEventListener("seeked", syncPlayheadFromPreview);
})();

/* Round 18 shortcuts (batches 1 + 2). One document keydown
   listener for shortcuts that did NOT already exist. Deliberately
   NOT re-bound here (their existing handlers own them): Ctrl+S
   save, Ctrl+Z undo, Ctrl+Shift+Z / Ctrl+Y redo, plain S magnetic
   toggle, plain I/O/E/Q source marks. Deliberately NOT bound at
   all (no matching feature exists in this web build — never
   faked): Ctrl+C/V/X copy/paste/cut (no web-UI flow, no
   /api/project op; MCP-only), Ctrl+A select-all (single-selection
   model), Ctrl+Shift+S share (no share feature), Ctrl+Shift+F
   audio split/detach (no such feature), V/C tool modes (no
   tool-mode concept), Ctrl+L linked toggle (link_audio op exists
   but no UI toggle deciding which audio to link), Shift+P
   preview-axis toggle (no such toggle), Shift+X/Alt+X region
   select (no region concept), Ctrl+G/Ctrl+Shift+G group (no
   grouping), Alt+G/Alt+Shift+G compound clip (no compound clips).
   Typing guard: when focus is in an input/textarea/select or a
   contenteditable element, every shortcut below is skipped so
   native typing, copy/paste/cut and select-all keep working.
   J is a 1-second seek back, NOT reverse playback: a <video>
   element cannot play in reverse. Ctrl+N/Ctrl+T are registered
   with preventDefault, but desktop Chrome/Edge may swallow them
   before the page sees them (the pywebview shell receives them). */
function shortcutIsTypingTarget(e) {
  const tag = (e.target.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || !!e.target.isContentEditable;
}
function stepPlayhead(frames) {
  if (!project) return;
  playheadFrame = Math.max(0, playheadFrame + frames);
  seekPreviewToPlayhead();
  renderTracks();
}
let __prevZoomPx = null;
function toggleTimelineZoom() {
  if (__prevZoomPx === null) {
    __prevZoomPx = pxPerSec;
    const fit = $("tlFit"); if (fit) fit.click();
  } else {
    pxPerSec = __prevZoomPx; __prevZoomPx = null;
    const z = $("zoom"); if (z) z.value = pxPerSec;
    const zl = $("zoomLabel"); if (zl) zl.textContent = pxPerSec + " px/s";
    renderTracks();
  }
}
function openCreateProject() {
  const wp = $("welcomePanel");
  if (wp && wp.hidden) { const wb = $("btnWelcome"); if (wb) wb.click(); }
  const name = $("projectNewName"); if (name) name.focus();
}
function openSavedProject() {
  const sel = $("projectSelect");
  if (sel && sel.value) { const b = $("btnProjectOpen"); if (b) b.click(); return; }
  const wp = $("welcomePanel");
  if (wp && wp.hidden) { const wb = $("btnWelcome"); if (wb) wb.click(); }
  if (sel) sel.focus();
}
function playPreviewFromKey() {
  const img = $("previewImage");
  if (img && !img.hidden) { setStatus("Đây là ảnh tĩnh — chỉ xem, không phát được.", true); return; }
  const v = $("preview");
  if (!v || !v.src) { setStatus("Chưa có gì để phát — bấm vào một clip/media, hoặc xuất bản nháp trước.", true); return; }
  if (v.paused) v.play();
}
function openSpeedCurve() {
  const tab = $("inspTabSpeed"); if (tab) tab.click();
  const form = $("speedCurveForm");
  if (form) {
    const d = form.closest("details"); if (d) d.open = true;
    const sel = $("speedCurvePreset"); if (sel) sel.focus();
  }
}
document.addEventListener("keydown", (e) => {
  if (shortcutIsTypingTarget(e)) return;
  const key = (e.key || "").toLowerCase();
  const ctrl = e.ctrlKey || e.metaKey, shift = e.shiftKey, alt = e.altKey;
  const click = (id) => { const el = $(id); if (el) el.click(); };
  const railClick = (tab) => { const el = document.querySelector(`.tool-rail [data-tab="${tab}"]`); if (el) el.click(); };
  if (ctrl && !alt) {
    if (key === "n" && !shift) { e.preventDefault(); openCreateProject(); }
    else if (key === "o" && !shift) { e.preventDefault(); openSavedProject(); }
    else if (key === "e" && !shift) { e.preventDefault(); railClick("effects"); }
    else if (key === "t" && !shift) { e.preventDefault(); railClick("text"); }
    else if (key === "r" && !shift) { e.preventDefault(); click("inspTabSpeed"); }
    else if (key === "k" && !shift) { e.preventDefault(); splitAtPlayhead(); }
    else if (key === "k" && shift) { e.preventDefault(); splitAllAtPlayhead(); }
    return;
  }
  if (alt && !ctrl) {
    if (key === "c" && shift) { click("btnExportFull"); }
    return;
  }
  if (shift && !ctrl && !alt) {
    if (key === "z") { toggleTimelineZoom(); }
    else if (key === "a") { stepPlayhead(-1); }
    else if (key === "b") { openSpeedCurve(); }
    else if (key === "backspace") { e.preventDefault(); click("tlCloseGaps"); }
    return;
  }
  if (!ctrl && !shift && !alt) {
    if (key === "delete") { click("btnDelete"); }
    else if (key === " ") {
      const tt = (e.target.tagName || "").toLowerCase();
      if (tt === "button" || tt === "video" || tt === "audio") return;
      e.preventDefault(); click("btnPreviewPlay");
    }
    else if (key === "j") { if (project) stepPlayhead(-Math.round(fps())); }
    else if (key === "k") { const v = $("preview"); if (v && !v.paused) v.pause(); }
    else if (key === "l") { playPreviewFromKey(); }
    else if (key === "arrowleft") { stepPlayhead(-1); }
    else if (key === "arrowright") { stepPlayhead(1); }
    else if (key === "a") { stepPlayhead(1); }
  }
});
/* End round 18 shortcuts. */

/* Round 19: resizable panels, icon tooltip, single import control. */

/* Pure helpers (top-level so tests can extract and check them). */
function clampSize(v, min, max) {
  if (typeof v !== "number" || !isFinite(v)) return null;
  if (v < min) return min;
  if (v > max) return max;
  return Math.round(v);
}
function validStored(v, min, max) {
  if (typeof v !== "number" || !isFinite(v)) return null;
  if (v < min || v > max) return null;
  return v;
}
function panelTemplate(tool, details, detailsHidden) {
  if (detailsHidden) {
    if (tool === null) return "280px minmax(0, 1fr)";
    return tool + "px minmax(0, 1fr)";
  }
  if (tool === null && details === null) return "";
  if (tool === null) return "280px minmax(0, 1fr) " + details + "px";
  if (details === null) return tool + "px minmax(0, 1fr) auto";
  return tool + "px minmax(0, 1fr) " + details + "px";
}
function tooltipPosition(rect, tipW, tipH, vw, vh) {
  let left = rect.left + rect.width / 2 - tipW / 2;
  left = Math.max(8, Math.min(left, vw - tipW - 8));
  let top = rect.bottom + 6;
  let below = true;
  if (top + tipH > vh - 8) { top = rect.top - tipH - 6; below = false; }
  return { left: Math.round(left), top: Math.round(top), below: below };
}

/* Round 19: body-level tooltip for icon-only timeline buttons.
   Root cause of the round-18 bug, read from the code: the toolbar
   has overflow-x: auto, which forces overflow-y to auto, and the
   ::after tooltip drops 6px below a 30px button inside a 40px bar —
   1px past the toolbar's clip edge — so it is always clipped and
   never shows (z-index cannot beat overflow clipping). This div
   lives on <body> with position: fixed, so no ancestor overflow can
   clip it. Text is the aria-label verbatim (== data-tip, locked by
   tests); no title attributes are added, so the native delayed
   tooltip never doubles up. The round-18 ::after rule is kept
   verbatim because old tests lock its strings; it stays inert. */
(function iconTooltip() {
  const tip = document.createElement("div");
  tip.id = "uiTooltip";
  tip.className = "ui-tooltip";
  tip.hidden = true;
  document.body.appendChild(tip);
  function showFor(btn) {
    const text = btn.getAttribute("aria-label") || btn.getAttribute("data-tip") || "";
    if (!text) return;
    tip.textContent = text;
    tip.hidden = false;
    const rect = btn.getBoundingClientRect();
    const pos = tooltipPosition(rect, tip.offsetWidth, tip.offsetHeight, window.innerWidth, window.innerHeight);
    tip.style.left = pos.left + "px";
    tip.style.top = pos.top + "px";
  }
  function hide() { tip.hidden = true; }
  function pick(e) {
    if (!e.target || !e.target.closest) return null;
    return e.target.closest(".tl-icon-btn[data-tip]");
  }
  document.addEventListener("mouseover", (e) => { const b = pick(e); if (b) showFor(b); });
  document.addEventListener("mouseout", (e) => {
    const b = pick(e);
    if (b && !(e.relatedTarget && b.contains(e.relatedTarget))) hide();
  });
  document.addEventListener("focusin", (e) => { const b = pick(e); if (b) showFor(b); });
  document.addEventListener("focusout", (e) => {
    const b = pick(e);
    if (b && !(e.relatedTarget && b.contains(e.relatedTarget))) hide();
  });
  document.addEventListener("pointerdown", (e) => { const b = pick(e); if (b) hide(); }, true);
  window.addEventListener("scroll", hide, true);
})();

/* Round 19: resizable panels. Sizes live ONLY in inline styles set
   here (workbench grid template, timeline flex-basis, drawer width)
   — the locked CSS defaults are never edited. Dragging clamps at
   the edges; sizes persist in localStorage (key below) with strict
   validation on restore; double-click a handle resets that region. */
(function panelResize() {
  const KEY = "vibeedit_panel_sizes";
  const LIMITS = { tool: [180, 480], details: [220, 520], agent: [280, 520] };
  const state = { tool: null, details: null, timeline: null, agent: null };
  function timelineMax() { return Math.round(window.innerHeight * 0.6); }
  function load() {
    let raw = null;
    try { raw = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (err) { raw = null; }
    if (!raw || typeof raw !== "object") return;
    state.tool = validStored(raw.tool, LIMITS.tool[0], LIMITS.tool[1]);
    state.details = validStored(raw.details, LIMITS.details[0], LIMITS.details[1]);
    state.timeline = validStored(raw.timeline, 180, timelineMax());
    state.agent = validStored(raw.agent, LIMITS.agent[0], LIMITS.agent[1]);
  }
  function save() {
    const out = {};
    if (state.tool !== null) out.tool = state.tool;
    if (state.details !== null) out.details = state.details;
    if (state.timeline !== null) out.timeline = state.timeline;
    if (state.agent !== null) out.agent = state.agent;
    try { localStorage.setItem(KEY, JSON.stringify(out)); } catch (err) { /* private mode: sizes just don't persist */ }
  }
  function apply() {
    const wb = document.querySelector(".workbench");
    if (wb) {
      const tpl = panelTemplate(state.tool, state.details, wb.classList.contains("details-hidden"));
      wb.style.gridTemplateColumns = tpl;
    }
    const tw = document.querySelector(".timeline-wrap");
    if (tw) tw.style.flexBasis = state.timeline === null ? "" : state.timeline + "px";
    const ag = document.getElementById("agentCol");
    if (ag) ag.style.width = state.agent === null ? "" : state.agent + "px";
  }
  function bind(handleId, opts) {
    const handle = document.getElementById(handleId);
    if (!handle) return;
    let startPos = 0, startSize = 0;
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      startPos = opts.axis === "x" ? e.clientX : e.clientY;
      startSize = opts.get();
      try { handle.setPointerCapture(e.pointerId); } catch (err) { /* mouse fallback: moves still tracked on window */ }
      document.body.classList.add("resizing");
      const move = (ev) => {
        const pos = opts.axis === "x" ? ev.clientX : ev.clientY;
        const next = clampSize(startSize + (pos - startPos) * opts.sign, opts.min, opts.max());
        if (next !== null) { opts.set(next); }
      };
      const up = () => {
        document.body.classList.remove("resizing");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", up);
        save();
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
      window.addEventListener("pointercancel", up);
    });
    handle.addEventListener("dblclick", () => { opts.reset(); apply(); save(); });
  }
  load();
  apply();
  const wbObs = document.querySelector(".workbench");
  if (wbObs && window.MutationObserver) {
    new MutationObserver(() => apply()).observe(wbObs, { attributes: true, attributeFilter: ["class"] });
  }
  bind("resizeTool", {
    axis: "x", sign: 1, min: LIMITS.tool[0], max: () => LIMITS.tool[1],
    get: () => document.querySelector(".tool-col").getBoundingClientRect().width,
    set: (v) => { state.tool = v; apply(); },
    reset: () => { state.tool = null; },
  });
  bind("resizeDetails", {
    axis: "x", sign: -1, min: LIMITS.details[0], max: () => LIMITS.details[1],
    get: () => document.querySelector(".details-col").getBoundingClientRect().width,
    set: (v) => { state.details = v; apply(); },
    reset: () => { state.details = null; },
  });
  bind("resizeTimeline", {
    axis: "y", sign: 1, min: 180, max: () => timelineMax(),
    get: () => document.querySelector(".timeline-wrap").getBoundingClientRect().height,
    set: (v) => { state.timeline = v; apply(); },
    reset: () => { state.timeline = null; },
  });
  bind("resizeAgent", {
    axis: "x", sign: -1, min: LIMITS.agent[0], max: () => LIMITS.agent[1],
    get: () => document.getElementById("agentCol").getBoundingClientRect().width,
    set: (v) => { state.agent = v; apply(); },
    reset: () => { state.agent = null; },
  });
})();

/* Round 19: single import control. Clicking the dropzone (or Enter /
   Space on it) opens the file picker; choosing a file auto-uploads.
   The drop flow and the upload submit handler are untouched. */
(function singleImportControl() {
  const zone = document.getElementById("importDropzone");
  const input = document.getElementById("uploadFile");
  const form = document.getElementById("uploadForm");
  if (!zone || !input || !form) return;
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => {
    if (input.files && input.files.length) form.requestSubmit();
  });
})();
