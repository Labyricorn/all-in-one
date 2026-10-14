import { Playback } from './playback.mjs';
import { planGuesses, guessOperations, approveOperations, describePlan, typicalDuration } from './guess.mjs';

const $ = id => document.getElementById(id);
const projectPath = () => '/api/v1/projects/' + project.project_id;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const keep = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch {} }
};

let token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
let project = null, playback = null, previewUrl = null;
let uploadedFile = null, uploadedMedia = null, jobsLoading = false, jobsKey = '', modelStatus, offlineTouched = false;
let pcm = null, peakCache = new Map();
let wordIndex = new Map(), lines = [], lineOfWord = new Map(), wordEls = [], lineEls = [];
let selectedWord = null, selectedBeatId = null, selectedSectionId = null;
let sideTab = 'word', issueFilter = 'all', follow = true, skipNextFollow = false;
let activeKey = '', activeLine = -1, auditionEnd = null, planned = new Set();
let undoStack = [], redoStack = [];
const jobLogs = new Map();
const timingText = value => value == null ? '' : String(Number(value.toFixed(3)));
const round3 = value => Math.round(value * 1000) / 1000;
const editedTiming = (input, original) => input.value === timingText(original) ? original : input.value === '' ? null : Number(input.value);
try {
  if (token) sessionStorage.setItem('mgmv-token', token);
  else token = sessionStorage.getItem('mgmv-token') || '';
} catch {}
if (location.hash) history.replaceState(null, '', location.pathname + location.search);
$('token').value = token;

function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
}
const songName = source => String(source || 'Untitled song').split(/[\\/]/).pop().replace(/^input-/, '');
const seconds = value => Math.floor(value / 60) + ':' + String(Math.floor(value % 60)).padStart(2, '0');
function handle(action) {
  return async event => {
    if (event?.type === 'submit') event.preventDefault();
    const button = event?.submitter;
    if (button) button.disabled = true;
    try { await action(event); }
    catch (error) { status(error.message, true); }
    finally { if (button) button.disabled = false; }
  };
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options, headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...options.headers}
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) $('connectionStatus').textContent = 'Reconnect with song-service.cmd';
    if (response.status === 409) throw new Error('This project was saved somewhere else since you opened it (another window, the command line or an assistant). Choose Reload to see the newest version, then repeat your change.');
    throw new Error(body.error || 'Request failed (' + response.status + ').');
  }
  return body;
}
const post = (path, body) => api(path, {method:'POST', body:JSON.stringify(body)});
const words = () => project?.analysis.lyrics?.words || [];
const beats = () => project?.analysis.beats || [];
const sections = () => project?.analysis.sections || [];

/* ---------- Steps ---------- */
const TAB_PROMPTS = {
  song: () => 'Choose a song, say whether it has lyrics, and start the analysis.',
  progress: () => 'Analysis updates here. When a song finishes, open it in Review.',
  review: () => project ? 'Play the song and click any word to check its timing.' : 'Choose a saved project, or open a finished analysis.',
  export: () => project ? 'Download the corrected timing file.' : 'Open a project in Review before exporting.'
};
function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach(tab => {
    const active = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    $('panel-' + tab.dataset.tab).hidden = !active;
  });
  if (name === 'export') renderExport();
  if (name === 'review') requestAnimationFrame(() => { resizeCanvas(); drawWaveform(); });
  status(TAB_PROMPTS[name]());
}
document.querySelectorAll('[data-tab]').forEach(tab => {
  tab.onclick = () => showTab(tab.dataset.tab);
  tab.onkeydown = event => {
    const tabs = [...document.querySelectorAll('[data-tab]')];
    let index = tabs.indexOf(tab);
    if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = tabs.length - 1;
    else return;
    event.preventDefault(); showTab(tabs[index].dataset.tab); tabs[index].focus();
  };
});
document.addEventListener('click', event => {
  const go = event.target.closest('[data-go]');
  if (go) showTab(go.dataset.go);
});
const currentTab = () => document.querySelector('[data-tab][aria-selected=true]')?.dataset.tab;
function markProgress(jobs) {
  $('tab-song').classList.toggle('done', jobs.length > 0);
  $('tab-progress').classList.toggle('done', jobs.some(j => ['complete', 'partial'].includes(j.status)));
  $('tab-review').classList.toggle('done', !!project);
}

/* ---------- Welcome and help ---------- */
if (keep.get('two-in-one.welcome-hidden') !== '1') $('welcome').hidden = false;
$('welcomeStart').onclick = () => { $('audioFile').focus(); $('audioFile').scrollIntoView({block:'center'}); };
$('welcomeOpen').onclick = () => showTab('review');
$('welcomeHide').onclick = () => { keep.set('two-in-one.welcome-hidden', '1'); $('welcome').hidden = true; };
$('helpButton').onclick = () => $('helpDialog').showModal();
$('showWelcome').onclick = () => { keep.set('two-in-one.welcome-hidden', '0'); $('welcome').hidden = false; $('helpDialog').close(); showTab('song'); };

/* ---------- Projects and jobs ---------- */
async function refreshList() {
  const result = await api('/api/v1/projects');
  const selected = project?.project_id || $('projects').value;
  const names = result.projects.map(p => songName(p.name || p.project_id));
  $('projects').innerHTML = '<option value="">Choose a project</option>' +
    result.projects.map((p, i) => '<option value="' + p.project_id + '">' + escapeHtml(names[i]) +
      (names.filter(n => n === names[i]).length > 1 ? ' [' + p.project_id.slice(0, 6) + ']' : '') +
      (p.revision ? ' · ' + p.revision + (p.revision === 1 ? ' edit' : ' edits') : ' · no edits yet') + '</option>').join('');
  $('projects').value = selected;
  $('emptyProjects').hidden = result.projects.length > 0 || !!project;
}
const STAGE_LABELS = ['Preparing the audio', 'Finding beats and sections', 'Working out the lyrics', 'Saving the results'];
function stageIndex(job) {
  if (['complete', 'partial'].includes(job.status)) return 4;
  const stage = job.stage || '';
  if (stage.startsWith('lyrics_')) return 2;
  if (stage === 'music_structure_and_demixing') return 1;
  if (stage === 'finished') return 3;
  return 0;
}
function stageList(job) {
  const at = stageIndex(job), failed = ['failed', 'cancelled'].includes(job.status);
  return '<ol class="stages">' + STAGE_LABELS.map((label, i) =>
    '<li class="' + (i < at ? 'done' : i === at && !failed ? 'current' : '') + '">' + label + '</li>').join('') + '</ol>';
}
const STATUS_WORDS = {queued:'Waiting', running:'Working', complete:'Finished', partial:'Finished with problems', failed:'Failed', cancelled:'Cancelled'};
async function refreshJobs() {
  if (jobsLoading) return;
  jobsLoading = true;
  try {
    const result = await api('/api/v1/jobs');
    const active = result.jobs.filter(j => ['queued', 'running'].includes(j.status)).length;
    $('jobCount').textContent = active || '';
    markProgress(result.jobs);
    $('emptyJobs').hidden = result.jobs.length > 0;
    const key = JSON.stringify(result.jobs) + [...jobLogs.keys()].join();
    if (key === jobsKey) return;
    jobsKey = key;
    $('jobs').innerHTML = result.jobs.map(job => {
      const isActive = ['queued', 'running'].includes(job.status);
      const ready = ['complete', 'partial'].includes(job.status);
      return '<article class="job-card">' +
        '<div class="row spread" style="justify-content:space-between"><h3>' + escapeHtml(songName(job.source)) + '</h3>' +
        '<span class="badge ' + escapeHtml(job.status) + '">' + escapeHtml(STATUS_WORDS[job.status] || job.status) + '</span></div>' +
        stageList(job) + (isActive ? '<div class="activity" aria-label="Analysis in progress"></div>' : '') +
        (job.status === 'partial' ? '<p class="hint">The beats and sections finished, but the lyrics did not. You can still review what was found.</p>' : '') +
        (job.status === 'failed' ? '<p class="hint">Choose Details to see why. A missing model is the most common cause: open Advanced settings on the first step and allow downloads, then try again.</p>' : '') +
        (job.error ? '<p class="job-error">' + escapeHtml(job.error) + '</p>' : '') +
        '<small>' + (job.created ? new Date(job.created * 1000).toLocaleString() + ' · ' : '') + escapeHtml(job.job_id.slice(0, 8)) + '</small>' +
        '<div class="job-actions">' +
        (ready ? '<button class="primary" data-open-job="' + job.job_id + '">Open in Review</button>' : '') +
        (isActive ? '<button class="quiet" data-cancel-job="' + job.job_id + '">Cancel analysis</button>' : '') +
        (['failed', 'partial', 'cancelled'].includes(job.status) ? '<button class="quiet" data-job-log="' + job.job_id + '">Details</button>' : '') +
        (['failed', 'cancelled'].includes(job.status) ? '<button class="quiet" data-go="song">Try again</button>' : '') +
        '</div><pre id="log-' + job.job_id + '"' + (jobLogs.has(job.job_id) ? '' : ' hidden') + '>' + escapeHtml(jobLogs.get(job.job_id) || '') + '</pre></article>';
    }).join('');
    document.querySelectorAll('[data-open-job]').forEach(button => button.onclick = handle(async () => {
      button.disabled = true;
      try {
        const id = button.dataset.openJob;
        let saved;
        try { saved = sessionStorage.getItem('job-project-' + id); } catch {}
        if (!saved) {
          status('Opening the analysis and its audio…');
          const result = await post('/api/v1/projects', {job_id: id});
          saved = result.project_id;
          try { sessionStorage.setItem('job-project-' + id, saved); } catch {}
        }
        await loadProject(saved); await refreshList(); showTab('review');
      } finally { button.disabled = false; }
    }));
    document.querySelectorAll('[data-cancel-job]').forEach(button => button.onclick = handle(async () => {
      button.disabled = true;
      try {
        await post('/api/v1/jobs/' + button.dataset.cancelJob + '/cancel', {});
        jobsKey = ''; await refreshJobs(); status('Analysis cancelled. Its log is kept in case you need it.');
      } finally { button.disabled = false; }
    }));
    document.querySelectorAll('[data-job-log]').forEach(button => button.onclick = handle(async () => {
      const job = await api('/api/v1/jobs/' + button.dataset.jobLog);
      const log = $('log-' + job.job_id);
      log.textContent = job.diagnostic_log_tail || job.error || 'No further details were recorded.';
      log.hidden = !log.hidden;
      if (log.hidden) jobLogs.delete(job.job_id); else jobLogs.set(job.job_id, log.textContent);
    }));
  } finally { jobsLoading = false; }
}
async function loadModels() {
  try { modelStatus = await api('/api/v1/models'); } catch { modelStatus = null; }
  updateModelState();
}
async function connect() {
  token = $('token').value.trim();
  try { sessionStorage.setItem('mgmv-token', token); } catch {}
  await Promise.all([refreshList(), refreshJobs(), loadModels()]);
  $('connectionStatus').textContent = '● Connected';
  status('Connected. Choose a song to analyze, or open a saved project in Review.');
}
$('connect').onclick = handle(connect);
$('refresh').onclick = handle(refreshList);
$('refreshJobs').onclick = handle(() => { jobsKey = ''; return refreshJobs(); });

/* ---------- Step 1: choose a song ---------- */
const PRESETS = {quick: ['harmonix-fold0', 'tiny'], balanced: ['harmonix-all', 'base'], thorough: ['harmonix-all', 'medium']};
const lyricsMode = () => document.querySelector('[name=lyricsMode]:checked').value;
function applyPreset(name) {
  const [music, lyric] = PRESETS[name];
  $('musicModel').value = music; $('lyricModel').value = lyric;
  updateModelState();
}
function updateModelState() {
  const mode = lyricsMode(), needsLyrics = mode === 'auto' || mode === 'align';
  const box = $('modelState');
  if (modelStatus === undefined) { box.textContent = 'Checking which models are on this computer…'; box.className = 'model-state'; return; }
  if (!modelStatus) { box.textContent = 'Could not check which models are on this computer. If a job fails for a missing model, allow downloads in Advanced settings.'; box.className = 'model-state'; return; }
  const missing = [];
  if (!modelStatus.music_models[$('musicModel').value]) missing.push('the music model');
  if (needsLyrics && !modelStatus.lyric_models[$('lyricModel').value]) missing.push('the “' + $('lyricModel').value + '” lyric model');
  if (needsLyrics && !modelStatus.alignment_model) missing.push('the word-timing model');
  const ready = missing.length === 0;
  box.className = 'model-state ' + (ready ? 'ready' : 'download');
  box.textContent = ready ? 'Everything this setting needs is already on this computer, so it works offline.'
    : 'Not on this computer yet: ' + missing.join(', ') + '. The first run will download them, so stay online and allow extra time.';
  if (!offlineTouched) $('offline').checked = ready;
}
$('audioFile').onchange = () => {
  const file = $('audioFile').files[0];
  uploadedFile = uploadedMedia = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  $('audioPreview').pause(); $('audioPreview').hidden = !file;
  $('audioName').textContent = file?.name || 'Select an audio or video file';
  $('audioDetails').textContent = file ? (file.size / 1024 / 1024).toFixed(1) + ' MB · you can preview it below' : 'WAV, MP3, FLAC, M4A, or a video with sound';
  if (file) { previewUrl = URL.createObjectURL(file); $('audioPreview').src = previewUrl; }
  $('submissionState').textContent = file ? 'Ready when you are.' : 'Choose a file to begin.';
};
function updateMode() {
  const mode = lyricsMode();
  $('lyricsInput').hidden = mode !== 'align';
  $('lyricsText').required = mode === 'align';
  $('language').required = mode === 'align';
  $('languageHint').hidden = mode !== 'align';
  $('lyricModel').disabled = ['none', 'instrumental'].includes(mode);
  updateModelState();
}
document.querySelectorAll('[name=lyricsMode]').forEach(radio => radio.onchange = updateMode);
document.querySelectorAll('[name=preset]').forEach(radio => radio.onchange = () => applyPreset(radio.value));
for (const id of ['musicModel', 'lyricModel']) $(id).onchange = () => {
  document.querySelectorAll('[name=preset]').forEach(radio => radio.checked = false);
  updateModelState();
};
$('offline').onchange = () => { offlineTouched = true; };
$('lyricsFile').onchange = handle(async () => {
  const file = $('lyricsFile').files[0];
  if (file) $('lyricsText').value = (await file.text()).replace(/^﻿/, '');
});
$('analyzeForm').onsubmit = handle(async () => {
  const file = $('audioFile').files[0];
  if (!file) throw new Error('Choose an audio or video file first.');
  const mode = lyricsMode();
  if (mode === 'align' && !$('lyricsText').value.trim()) throw new Error('Paste the lyrics, or choose another option for “Does the song have lyrics?”.');
  if (mode === 'align' && !$('language').value) throw new Error('Choose the language of the lyrics.');
  $('audioPreview').pause();
  try {
    if (uploadedFile !== file) {
      $('submissionState').textContent = 'Copying and checking ' + file.name + '…';
      status('Copying the song into the local workspace…');
      uploadedMedia = await api('/api/v1/media', {method:'POST', body:file,
        headers:{'Content-Type':'application/octet-stream', 'X-Filename':encodeURIComponent(file.name)}});
      uploadedFile = file;
    }
    $('submissionState').textContent = 'Starting…';
    const result = await post('/api/v1/jobs', {
      path:uploadedMedia.path, lyrics_mode:mode,
      lyrics_text:mode === 'align' ? $('lyricsText').value : null,
      language:$('language').value || null,
      music_model:$('musicModel').value, lyric_model:$('lyricModel').value,
      offline:$('offline').checked
    });
    $('submissionState').textContent = 'Started. Job ' + result.job_id.slice(0, 8) + '.';
    jobsKey = ''; await refreshJobs(); showTab('progress');
    status('Analysis started. This page will show each stage as it finishes.');
  } catch (error) {
    $('submissionState').textContent = error.message;
    throw error;
  }
});

/* ---------- Loading a project ---------- */
async function loadProject(id, reloadAudio = true) {
  status('Loading the project…');
  const changed = project?.project_id !== id;
  project = await api('/api/v1/projects/' + encodeURIComponent(id));
  if (changed) {
    selectedWord = selectedBeatId = selectedSectionId = null; undoStack = []; redoStack = [];
    $('wordFilter').value = ''; planned = new Set();
  }
  $('editor').hidden = false; $('emptyProjects').hidden = true; $('projects').value = id;
  $('projectMeta').textContent = songName(project.analysis.source) + ' · ' + words().length + ' words';
  $('saveState').textContent = project.revision ? project.revision + (project.revision === 1 ? ' edit saved' : ' edits saved') : 'No edits yet'; $('saveState').className = 'save-state';
  buildStructure(); renderAll();
  if (reloadAudio) await loadAudio();
  else { playback?.setMetronome($('metro').checked, beats()); drawWaveform(); }
  $('tab-review').classList.add('done');
  status('Project ready. Press Space to play, or click a word.');
}
function buildStructure() {
  const ws = words(), ss = sections();
  wordIndex = new Map(ws.map((w, i) => [w.id, i]));
  lines = (project.analysis.lyrics?.phrases || []).map((phrase, i) => {
    const idx = phrase.word_ids.map(id => wordIndex.get(id)).filter(i => i != null);
    const timed = idx.map(i => ws[i]).filter(w => w.start != null && w.end != null);
    return {id: phrase.id, n: i + 1, idx, start: timed.length ? Math.min(...timed.map(w => w.start)) : null,
      end: timed.length ? Math.max(...timed.map(w => w.end)) : null};
  });
  lineOfWord = new Map();
  lines.forEach((line, li) => line.idx.forEach(i => lineOfWord.set(i, li)));
  const orphans = ws.map((_, i) => i).filter(i => !lineOfWord.has(i));
  if (orphans.length) { lines.push({id: null, n: lines.length + 1, idx: orphans, start: null, end: null}); orphans.forEach(i => lineOfWord.set(i, lines.length - 1)); }
  let current = -1;
  lines.forEach(line => {
    if (line.start != null) { const s = ss.findIndex(sec => line.start >= sec.start && line.start < sec.end); if (s >= 0) current = s; }
    line.section = current;
  });
}
function renderAll() {
  renderLyrics(); renderIssues(); renderGuessPanel(); renderGrid(); chooseWord(selectedWord, {quiet: true}); updateHistory();
}
async function loadAudio() {
  if (playback) { const context = playback.context; playback.dispose(); await context.close(); }
  playback = null; pcm = null; peakCache = new Map(); auditionEnd = null;
  const artifacts = project.artifacts || [];
  const hasMix = artifacts.some(a => a.id === 'mix');
  $('play').disabled = $('seek').disabled = $('track').disabled = $('rate').disabled = $('metro').disabled = !hasMix;
  $('track').querySelector('[value="vocals"]').disabled = !artifacts.some(a => a.id === 'vocals');
  $('track').value = 'mix'; $('rate').value = '1'; $('seek').value = '0';
  $('duration').textContent = seconds(project.analysis.duration_seconds);
  $('clearLoop').hidden = true;
  if (!hasMix) { $('clock').textContent = 'No audio'; $('waveHint').textContent = 'This project has no audio attached, so you can edit times but not play them.'; resizeCanvas(); drawWaveform(); return; }
  $('waveHint').textContent = 'Click the waveform to jump. Drag across it to loop a region.';
  playback = new Playback(new AudioContext());
  await playback.load(artifacts.map(a => ({...a, url: projectPath() + '/artifacts/' + a.id})),
    url => fetch(url, {headers: {Authorization: 'Bearer ' + token}}));
  $('seek').max = playback.duration;
  playback.setMetronome($('metro').checked, beats());
  pcm = playback.buffers.get('mix').getChannelData(0);
  resizeCanvas(); drawWaveform();
}

/* ---------- Waveform ---------- */
const canvas = $('waveform');
function resizeCanvas() {
  const ratio = devicePixelRatio || 1, width = canvas.clientWidth;
  if (!width) return;
  if (canvas.width !== Math.round(width * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(96 * ratio); }
}
function peaksFor(count) {
  if (!pcm) return null;
  if (!peakCache.has(count)) {
    const peaks = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const start = Math.floor(i * pcm.length / count), end = Math.floor((i + 1) * pcm.length / count);
      let peak = 0;
      for (let j = start; j < end; j += 8) peak = Math.max(peak, Math.abs(pcm[j]));
      peaks[i] = peak;
    }
    peakCache.set(count, peaks);
  }
  return peakCache.get(count);
}
function drawWaveform() {
  if (!project) return;
  const ratio = devicePixelRatio || 1, ctx = canvas.getContext('2d');
  const width = canvas.width / ratio, height = 96;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const duration = project.analysis.duration_seconds || 1, x = t => t / duration * width;
  sections().forEach((s, i) => {
    ctx.fillStyle = i % 2 ? '#13232c' : '#17303a';
    ctx.fillRect(x(s.start), 0, x(s.end) - x(s.start), height);
    ctx.fillStyle = s.id === selectedSectionId ? '#5ed3b4' : '#9fb4ba'; ctx.font = '11px "Segoe UI", system-ui';
    ctx.fillText(s.label || '', x(s.start) + 5, 13);
  });
  const peaks = peaksFor(Math.max(1, Math.floor(width)));
  ctx.fillStyle = '#4fbfae';
  peaks?.forEach((peak, i) => {
    const amplitude = Math.max(1, peak * (height - 34) / 2);
    ctx.fillRect(i, height / 2 + 6 - amplitude, 1, amplitude * 2);
  });
  ctx.strokeStyle = '#b7f0d94d';
  beats().filter(b => b.position_in_bar === 1).forEach(b => { ctx.beginPath(); ctx.moveTo(x(b.time), height - 10); ctx.lineTo(x(b.time), height); ctx.stroke(); });
  const selectedBeat = beats().find(b => b.id === selectedBeatId);
  if (selectedBeat) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x(selectedBeat.time), 18); ctx.lineTo(x(selectedBeat.time), height); ctx.stroke(); ctx.lineWidth = 1; }
  words().forEach(w => {
    if (w.start == null) return;
    if (w.timing_status === 'guessed') { ctx.fillStyle = '#e9b44c'; ctx.fillRect(x(w.start), height - 5, Math.max(2, x(w.end) - x(w.start)), 5); }
    else if (isWeak(w)) { ctx.fillStyle = '#8ea3aa'; ctx.fillRect(x(w.start), height - 3, Math.max(1.5, x(w.end) - x(w.start)), 3); }
  });
  const word = words()[selectedWord];
  if (word?.start != null) { ctx.fillStyle = '#5ed3b455'; ctx.fillRect(x(word.start), 0, Math.max(2, x(word.end) - x(word.start)), height); }
}
const timeAt = clientX => {
  const rect = canvas.getBoundingClientRect();
  return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * (project?.analysis.duration_seconds || 0);
};
function showLoop() {
  const loop = playback?.loop, duration = playback?.duration || 1;
  $('loopBand').hidden = !loop; $('clearLoop').hidden = !loop;
  if (loop) { $('loopBand').style.left = loop.start / duration * 100 + '%'; $('loopBand').style.width = (loop.end - loop.start) / duration * 100 + '%'; }
}
let drag = null;
canvas.onpointerdown = event => { canvas.setPointerCapture(event.pointerId); drag = {x0: event.clientX, t0: timeAt(event.clientX), moved: false}; };
canvas.onpointermove = event => {
  if (!drag) return;
  if (Math.abs(event.clientX - drag.x0) > 6) drag.moved = true;
  if (drag.moved && playback) {
    const a = Math.min(drag.t0, timeAt(event.clientX)), b = Math.max(drag.t0, timeAt(event.clientX)), d = playback.duration;
    $('loopBand').hidden = false; $('loopBand').style.left = a / d * 100 + '%'; $('loopBand').style.width = (b - a) / d * 100 + '%';
  }
};
canvas.onpointerup = handle(event => {
  if (!drag) return;
  const info = drag; drag = null;
  const t = timeAt(event.clientX);
  if (info.moved && playback) {
    const a = Math.min(info.t0, t), b = Math.max(info.t0, t);
    if (b - a >= 0.2) { playback.setLoop(a, b); showLoop(); if (!playback.running) return playback.play(); return; }
  }
  if (!info.moved) {
    const section = event.offsetY < 18 ? sections().find(s => t >= s.start && t < s.end) : null;
    if (section) { selectSection(section.id); setSideTab('grid'); }
    seekTo(t);
  }
  showLoop();
});
canvas.onpointercancel = () => { drag = null; showLoop(); };
$('clearLoop').onclick = handle(() => { playback?.setLoop(); showLoop(); });
window.addEventListener('resize', () => { resizeCanvas(); drawWaveform(); });

/* ---------- Playback controls ---------- */
function seekTo(time) {
  if (!playback) return;
  auditionEnd = null; playback.seek(Math.max(0, Math.min(playback.duration, time)));
}
function audition(start, end) {
  if (!playback || start == null) return;
  playback.seek(Math.max(0, start - 0.25));
  auditionEnd = end + 0.05;
  return playback.play();
}
$('play').onclick = handle(() => togglePlay());
function togglePlay() {
  if (!playback) return;
  auditionEnd = null;
  return playback.running ? playback.pause() : playback.play();
}
$('track').onchange = handle(() => playback?.selectTrack($('track').value));
$('rate').onchange = handle(() => playback?.setRate(Number($('rate').value)));
$('seek').oninput = handle(() => seekTo(Number($('seek').value)));
$('metro').onchange = handle(() => playback?.setMetronome($('metro').checked, beats()));
setInterval(() => playback?.scheduleMetronome(), 50);

/* ---------- Lyrics ---------- */
function isWeak(w) { return w.start != null && w.model_score != null && w.model_score < 0.5 && w.provenance?.method !== 'user_set' && w.timing_status !== 'guessed'; }
function wordState(w) { return w.start == null ? 'untimed' : w.timing_status === 'guessed' ? 'guessed' : isWeak(w) ? 'weak' : 'timed'; }
function renderLyrics() {
  const box = $('lyrics'), scroll = box.scrollTop, ws = words(), ss = sections();
  const filter = $('wordFilter').value.trim().toLowerCase();
  let html = '', lastSection = -2;
  lines.forEach((line, li) => {
    if (line.section !== lastSection && line.section >= 0) {
      const s = ss[line.section];
      html += '<div class="section-label">' + escapeHtml(s.label || 'Section') + '<span>' + seconds(s.start) + ' to ' + seconds(s.end) + '</span></div>';
    }
    lastSection = line.section;
    const matches = filter ? line.idx.some(i => ws[i].text.toLowerCase().includes(filter)) : true;
    html += '<div class="line' + (matches ? '' : ' dim') + '" data-line="' + li + '">' +
      '<button class="line-time" type="button" data-seek-line="' + li + '" title="Jump to this line"' + (line.start == null ? ' disabled' : '') + '>' + (line.start == null ? '–' : seconds(line.start)) + '</button>' +
      '<div class="words">' + line.idx.map(i => {
        const w = ws[i], state = wordState(w);
        const title = w.start == null ? 'No timing yet' : state === 'guessed' ? 'Guessed time ' + w.start.toFixed(2) + ' to ' + w.end.toFixed(2) + ' s'
          : w.start.toFixed(2) + ' to ' + w.end.toFixed(2) + ' s' + (state === 'weak' ? ' (low confidence)' : '');
        return '<button class="word ' + state + (filter && w.text.toLowerCase().includes(filter) ? ' match' : '') + (planned.has(w.id) ? ' planned' : '') +
          (i === selectedWord ? ' selected' : '') + '" type="button" data-i="' + i + '" title="' + title + '">' + escapeHtml(w.text) + '</button>';
      }).join('') + '</div></div>';
  });
  box.innerHTML = html || '<p class="hint">This project has no lyrics.</p>';
  box.scrollTop = scroll;
  wordEls = []; lineEls = [];
  box.querySelectorAll('.word').forEach(el => { wordEls[Number(el.dataset.i)] = el; });
  box.querySelectorAll('.line').forEach(el => { lineEls[Number(el.dataset.line)] = el; });
  activeKey = ''; activeLine = -1;
}
/* Where the playhead should go when a word is clicked. Untimed words have no start of their
   own, so use the end of the nearest earlier timed word (or the start of the next one). */
function wordSeekTime(index) {
  const all = words(), word = all[index];
  if (word.start != null) return {time: word.start, end: word.end, own: true};
  for (let i = index - 1; i >= 0; i--) if (all[i].end != null) return {time: all[i].end, own: false};
  for (let i = index + 1; i < all.length; i++) if (all[i].start != null) return {time: all[i].start, own: false};
  return null;
}
/* A loop pulls the playhead back inside it, so a click outside the loop ends the loop. */
function releaseLoopFor(time) {
  const loop = playback?.loop;
  if (!loop || (time >= loop.start && time < loop.end)) return;
  playback.setLoop(); showLoop();
  status('Loop cleared so the playhead could move there.');
}
function moveToWord(index, {audible = true} = {}) {
  if (!playback) return;
  const target = wordSeekTime(index);
  if (!target) return;
  releaseLoopFor(target.time);
  skipNextFollow = true;
  if (target.own && !playback.running && audible) return audition(target.time, target.end);
  seekTo(target.time);
}
function clearSelection() {
  if (selectedWord == null) return;
  chooseWord(null);
  $('wordForm').hidden = true; $('wordEmpty').hidden = false;
}
$('clearSelection').onclick = () => clearSelection();
$('lyrics').onclick = handle(event => {
  const lineButton = event.target.closest('[data-seek-line]');
  if (lineButton) {
    const line = lines[Number(lineButton.dataset.seekLine)];
    if (line.start != null) { releaseLoopFor(line.start); skipNextFollow = true; seekTo(line.start); }
    return;
  }
  const button = event.target.closest('.word');
  if (!button) { if (!event.target.closest('button,a,input,label')) clearSelection(); return; }
  const index = Number(button.dataset.i);
  chooseWord(index, {tab: true});
  moveToWord(index);
});
$('wordFilter').oninput = () => renderLyrics();
function setFollow(on) {
  follow = on; $('follow').checked = on;
  $('jumpNow').hidden = on || !playback;
  if (on && activeLine >= 0) scrollToLine(activeLine, true);
}
$('follow').onchange = () => setFollow($('follow').checked);
$('jumpNow').onclick = () => setFollow(true);
for (const type of ['wheel', 'touchmove']) $('lyrics').addEventListener(type, () => { if (follow) setFollow(false); }, {passive: true});
$('lyrics').addEventListener('pointerdown', event => { if (event.target === $('lyrics') && event.offsetX > $('lyrics').clientWidth && follow) setFollow(false); });
function scrollToLine(li, force = false) {
  const el = lineEls[li];
  if (!el) return;
  const box = $('lyrics').getBoundingClientRect(), rect = el.getBoundingClientRect();
  const delta = rect.top - box.top - box.height * 0.3;
  const visible = rect.top >= box.top + 40 && rect.bottom <= box.bottom - 40 && Math.abs(delta) < box.height * 0.22;
  if (!force && visible) return;
  $('lyrics').scrollBy({top: delta, behavior: reduceMotion ? 'auto' : 'smooth'});
}
function lineAt(time) {
  let found = -1;
  lines.forEach((line, li) => { if (line.start != null && line.start <= time + 0.05) found = li; });
  if (found >= 0 && lines[found].end != null && time > lines[found].end + 2) return -1;
  return found;
}

/* ---------- Selected word ---------- */
function setSideTab(name) {
  sideTab = name;
  document.querySelectorAll('[data-side]').forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.side === name)));
  document.querySelectorAll('[data-side-panel]').forEach(panel => { panel.hidden = panel.dataset.sidePanel !== name; });
  if (name === 'grid' && playback && !selectedBeatId) selectNearestBeat();
  if (name === 'issues') updateGuessPreview(); else clearPlanned();
}
document.querySelectorAll('[data-side]').forEach(tab => tab.onclick = () => setSideTab(tab.dataset.side));
const BADGES = {timed: ['timed', 'Timed'], weak: ['weak', 'Low confidence'], untimed: ['missing', 'No timing'], guessed: ['guessed', 'Guessed']};
function chooseWord(index, {tab = false, reveal = false, quiet = false} = {}) {
  selectedWord = index;
  const word = index == null ? null : words()[index];
  $('wordEmpty').hidden = !!word; $('wordForm').hidden = !word;
  wordEls.forEach(el => el?.classList.remove('selected'));
  if (word) {
    wordEls[index]?.classList.add('selected');
    if (reveal) wordEls[index]?.scrollIntoView({block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth'});
    $('wordTitle').textContent = word.text;
    const state = wordState(word), [kind, label] = BADGES[state];
    $('wordBadge').className = 'badge ' + (word.provenance?.method === 'user_set' ? 'user' : kind);
    $('wordBadge').textContent = word.provenance?.method === 'user_set' ? 'Set by you' : label;
    $('guessNote').hidden = state !== 'guessed';
    $('wordText').value = word.text;
    $('wordStart').value = timingText(word.start); $('wordEnd').value = timingText(word.end);
    if (tab) setSideTab('word');
  }
  if (!quiet) { updateGuessPreview(); drawWaveform(); }
  updateScopeOptions();
}
function nudge(inputId, by) {
  const input = $(inputId);
  const base = input.value === '' ? (playback ? playback.position() : 0) : Number(input.value);
  input.value = timingText(Math.max(0, round3(base + by)));
}
document.addEventListener('click', event => {
  const nudgeButton = event.target.closest('[data-nudge]');
  if (nudgeButton) nudge(nudgeButton.dataset.nudge, Number(nudgeButton.dataset.by));
  const here = event.target.closest('[data-playhead]');
  if (here) {
    const time = round3(playback ? playback.position() : 0);
    $(here.dataset.playhead).value = timingText(time);
    if (here.dataset.playhead === 'wordStart' && $('wordEnd').value === '') {
      const word = words()[selectedWord];
      $('wordEnd').value = timingText(round3(time + typicalDuration(word?.text || '')));
    }
  }
});
async function saveSelectedWord() {
  const word = words()[selectedWord];
  if (!word) throw new Error('Select a word first.');
  const startText = $('wordStart').value, endText = $('wordEnd').value;
  if ((startText === '') !== (endText === '')) throw new Error('Fill in both the start and the end, or leave both empty.');
  const start = editedTiming($('wordStart'), word.start), end = editedTiming($('wordEnd'), word.end);
  if (start != null && end <= start) throw new Error('The end must come after the start.');
  const operations = [];
  if ($('wordText').value !== word.text) operations.push({op: 'replace_word', word_id: word.id, text: $('wordText').value});
  if (start !== word.start || end !== word.end) operations.push({op: 'set_word_interval', word_id: word.id, start, end});
  if (!operations.length) throw new Error('Nothing to save yet. Change the text or a time first.');
  await commit(operations, 'Saved “' + $('wordText').value + '”.');
}
$('wordForm').onsubmit = handle(saveSelectedWord);
$('saveNext').onclick = handle(async () => { await saveSelectedWord(); gotoIssue(1); });
$('approveWord').onclick = handle(() => commit(approveOperations([words()[selectedWord].id]), 'Approved. This time is now yours, not a guess.'));
$('approveNext').onclick = handle(async () => { await commit(approveOperations([words()[selectedWord].id]), 'Approved. Here is the next one.'); gotoIssue(1); });
$('prevIssueWord').onclick = () => gotoIssue(-1);
$('nextIssueWord').onclick = () => gotoIssue(1);
$('playWord').onclick = handle(() => {
  const word = words()[selectedWord], start = $('wordStart').value === '' ? null : Number($('wordStart').value), end = Number($('wordEnd').value);
  if (start == null || !(end > start)) throw new Error('Give this word a start and end time to play it.');
  return audition(start, end);
});
$('loopLine').onclick = handle(() => loopSelectedLine());
function loopSelectedLine() {
  if (selectedWord == null) throw new Error('Select a word in the line first.');
  const line = lines[lineOfWord.get(selectedWord)];
  if (!playback) throw new Error('There is no audio to loop.');
  if (line.start == null) throw new Error('This line has no timing yet. Give its words times, or guess them, then loop it.');
  playback.setLoop(Math.max(0, line.start - 0.2), Math.min(playback.duration, line.end + 0.2));
  showLoop(); auditionEnd = null; seekTo(Math.max(0, line.start - 0.2));
  return playback.play();
}

/* ---------- Needs attention ---------- */
const ISSUES = {
  missing_word_timing: ['missing', 'No timing', 'missing'],
  weak_word_timing: ['weak', 'Low confidence', 'weak'],
  overlapping_words: ['overlap', 'Overlaps the word before', 'weak'],
  guessed_word_timing: ['guessed', 'Guessed time', 'guessed']
};
const FILTERS = [['all', 'All'], ['missing', 'No timing'], ['weak', 'Low confidence'], ['overlap', 'Overlaps'], ['guessed', 'Guessed']];
let issues = [];
function computeIssues() {
  const found = new Map();
  for (const item of project.analysis.review_items || []) {
    const info = ISSUES[item.code];
    if (!info || item.id == null || !wordIndex.has(item.id)) continue;
    const index = wordIndex.get(item.id);
    if (!found.has(index)) found.set(index, {index, group: info[0], label: info[1], badge: info[2]});
  }
  issues = [...found.values()].sort((a, b) => a.index - b.index);
}
const shownIssues = () => issues.filter(i => issueFilter === 'all' || i.group === issueFilter);
function renderIssues() {
  computeIssues();
  $('issueCount').textContent = issues.length || '';
  if (issueFilter !== 'all' && !issues.some(i => i.group === issueFilter)) issueFilter = 'all';
  $('issueChips').innerHTML = FILTERS.map(([key, label]) => {
    const count = key === 'all' ? issues.length : issues.filter(i => i.group === key).length;
    return key === 'all' || count ? '<button type="button" class="chip" data-filter="' + key + '" aria-pressed="' + (issueFilter === key) + '">' + label + ' ' + count + '</button>' : '';
  }).join('');
  const ws = words(), list = shownIssues();
  $('issueList').innerHTML = list.map(issue => {
    const w = ws[issue.index], line = lines[lineOfWord.get(issue.index)];
    return '<li><button type="button" class="issue' + (issue.index === selectedWord ? ' current' : '') + '" data-issue="' + issue.index + '"><strong>' + escapeHtml(w.text) + '</strong>' +
      '<small>Line ' + (line?.n ?? '?') + (w.start == null ? ' · no time yet' : ' · ' + w.start.toFixed(2) + ' s') + '</small><span class="badge ' + issue.badge + '">' + issue.label + '</span></button></li>';
  }).join('');
  $('issueEmpty').hidden = list.length > 0;
  const guessed = issues.filter(i => i.group === 'guessed');
  $('approveAll').hidden = guessed.length === 0;
  $('approveAll').textContent = 'Approve all ' + guessed.length + ' guesses';
  const tail = (project.analysis.review_items || []).find(i => i.code === 'uncovered_beat_tail');
  $('issueNotes').textContent = tail ? 'The beat grid stops ' + tail.seconds.toFixed(1) + ' seconds before the song ends, so the last part has no beats.' : '';
}
$('issueChips').onclick = event => { const chip = event.target.closest('[data-filter]'); if (chip) { issueFilter = chip.dataset.filter; renderIssues(); } };
$('issueList').onclick = handle(event => {
  const item = event.target.closest('[data-issue]');
  if (!item) return;
  openIssue(Number(item.dataset.issue));
});
function openIssue(index) {
  const word = words()[index];
  chooseWord(index, {reveal: true, tab: true});
  renderIssues();
  moveToWord(index);
}
function gotoIssue(direction) {
  const list = shownIssues();
  if (!list.length) { status('Nothing left to check in this list.'); return; }
  const here = selectedWord ?? -1;
  const next = direction > 0 ? (list.find(i => i.index > here) || list[0]) : ([...list].reverse().find(i => i.index < here) || list[list.length - 1]);
  openIssue(next.index);
}
$('nextIssue').onclick = () => gotoIssue(1);
$('prevIssue').onclick = () => gotoIssue(-1);
$('approveAll').onclick = handle(() => {
  const ids = issues.filter(i => i.group === 'guessed').map(i => words()[i.index].id);
  return commit(approveOperations(ids), 'Approved ' + ids.length + ' guessed times.');
});

/* ---------- Guessing ---------- */
const guessSettings = () => ({close: $('guessClose').checked, successive: $('guessSuccessive').checked && $('guessClose').checked,
  snap: $('guessSnap').checked, maxGap: Math.max(0.5, Number($('guessGap').value) || 4)});
function guessScope() {
  const scope = document.querySelector('[name=guessScope]:checked').value;
  if (scope === 'song' || selectedWord == null) return null;
  const line = lines[lineOfWord.get(selectedWord)];
  const chosen = scope === 'line' ? [line] : lines.filter(l => l.section === line.section);
  return new Set(chosen.flatMap(l => l.idx.map(i => words()[i].id)));
}
function updateScopeOptions() {
  const none = selectedWord == null;
  document.querySelectorAll('[name=guessScope][value=line],[name=guessScope][value=section]').forEach(r => { r.disabled = none; if (none && r.checked) document.querySelector('[name=guessScope][value=song]').checked = true; });
}
function renderGuessPanel() {
  const untimed = words().filter(w => w.start == null).length;
  $('guessPanel').hidden = untimed === 0 && !words().some(w => w.timing_status === 'guessed');
  if (untimed === 0) { $('guessClose').checked = false; }
  $('guessMore').hidden = !$('guessClose').checked;
  updateGuessPreview();
}
function clearPlanned() {
  if (!planned.size) return;
  planned.forEach(id => wordEls[wordIndex.get(id)]?.classList.remove('planned'));
  planned = new Set();
}
function updateGuessPreview() {
  $('guessMore').hidden = !$('guessClose').checked;
  if (!project || !$('guessClose').checked || sideTab !== 'issues') { clearPlanned(); $('applyGuess').disabled = true; $('guessPreview').textContent = ''; return; }
  const plan = planGuesses(words(), guessSettings(), beats(), guessScope());
  $('guessPreview').textContent = describePlan(plan);
  $('applyGuess').disabled = plan.guesses.length === 0;
  $('applyGuess').textContent = plan.guesses.length ? 'Apply ' + plan.guesses.length + ' guess' + (plan.guesses.length === 1 ? '' : 'es') : 'Apply guesses';
  clearPlanned();
  planned = new Set(plan.guesses.map(g => g.id));
  planned.forEach(id => wordEls[wordIndex.get(id)]?.classList.add('planned'));
  $('applyGuess')._plan = plan;
}
for (const id of ['guessClose', 'guessSuccessive', 'guessSnap', 'guessGap']) $(id).addEventListener('input', updateGuessPreview);
document.querySelectorAll('[name=guessScope]').forEach(r => r.addEventListener('change', updateGuessPreview));
$('applyGuess').onclick = handle(async () => {
  const plan = $('applyGuess')._plan;
  if (!plan?.guesses.length) throw new Error('There is nothing to guess with these settings.');
  const count = plan.guesses.length;
  clearPlanned();
  $('guessPanel').open = false;
  await commit(guessOperations(plan.guesses), 'Guessed ' + count + ' time' + (count === 1 ? '' : 's') + '. They are marked ≈. Play them, then approve or adjust. Undo reverses all of them.');
  issueFilter = 'guessed'; renderIssues();
});

/* ---------- Beats and sections ---------- */
function nearestBeatIndex(time) {
  const all = beats(); let best = -1, gap = Infinity;
  all.forEach((b, i) => { const d = Math.abs(b.time - time); if (d < gap) { gap = d; best = i; } });
  return best;
}
function selectBeatIndex(index) {
  const all = beats();
  if (!all.length) return;
  const beat = all[Math.max(0, Math.min(all.length - 1, index))];
  selectedBeatId = beat.id; renderBeat(); drawWaveform();
  if (playback) seekTo(Math.max(0, beat.time - 0.05));
}
function selectNearestBeat() { if (beats().length) { selectedBeatId = beats()[nearestBeatIndex(playback ? playback.position() : 0)].id; renderBeat(); drawWaveform(); } }
function renderBeat() {
  const all = beats(), index = all.findIndex(b => b.id === selectedBeatId), beat = all[index];
  $('beatLabel').textContent = beat ? 'Beat ' + (index + 1) + ' of ' + all.length + ' · count ' + (beat.position_in_bar ?? '?') + ' · ' + beat.time.toFixed(3) + ' s' : 'No beats in this project.';
  $('beatTime').value = beat ? timingText(beat.time) : '';
  $('beatForm').querySelector('button.primary').disabled = !beat;
}
$('prevBeat').onclick = handle(() => selectBeatIndex(beats().findIndex(b => b.id === selectedBeatId) - 1));
$('nextBeat').onclick = handle(() => selectBeatIndex(beats().findIndex(b => b.id === selectedBeatId) + 1));
$('nearBeat').onclick = () => selectNearestBeat();
$('beatForm').onsubmit = handle(async () => {
  const beat = beats().find(b => b.id === selectedBeatId);
  if (!beat) throw new Error('Choose a beat first.');
  const time = editedTiming($('beatTime'), beat.time);
  if (time === beat.time) throw new Error('Nothing to save yet. Change the beat time first.');
  await commit([{op: 'set_beat', beat_id: beat.id, time}], 'Moved the beat to ' + time.toFixed(3) + ' s.');
});
function selectSection(id) {
  selectedSectionId = id; renderSections(); drawWaveform();
  const section = sections().find(s => s.id === id);
  if (section && playback) seekTo(section.start);
}
function renderSections() {
  const all = sections();
  if (!all.some(s => s.id === selectedSectionId)) selectedSectionId = all[0]?.id ?? null;
  $('sectionList').innerHTML = all.map(s => '<li><button type="button" data-section="' + s.id + '"' + (s.id === selectedSectionId ? ' aria-current="true"' : '') + '><span>' + escapeHtml(s.label || 'Section') + '</span><small>' + seconds(s.start) + ' to ' + seconds(s.end) + '</small></button></li>').join('');
  const section = all.find(s => s.id === selectedSectionId);
  $('sectionLabel').value = section?.label || '';
  $('sectionStart').value = timingText(section?.start); $('sectionEnd').value = timingText(section?.end);
  $('sectionForm').querySelector('button.primary').disabled = !section;
}
$('sectionList').onclick = event => { const button = event.target.closest('[data-section]'); if (button) selectSection(button.dataset.section); };
$('sectionForm').onsubmit = handle(async () => {
  const section = sections().find(s => s.id === selectedSectionId), operations = [];
  if (!section) throw new Error('Choose a section first.');
  if ($('sectionLabel').value !== section.label) operations.push({op: 'set_section', section_id: section.id, value: {label: $('sectionLabel').value}});
  const start = editedTiming($('sectionStart'), section.start), end = editedTiming($('sectionEnd'), section.end);
  if (start == null || end == null || end <= start) throw new Error('A section needs a start and an end, and the end must come after the start.');
  if (start !== section.start || end !== section.end) operations.push({op: 'set_section_interval', section_id: section.id, start, end});
  if (!operations.length) throw new Error('Nothing to save yet. Change the label or a time first.');
  await commit(operations, 'Saved the section.');
});
function renderGrid() {
  if (!beats().some(b => b.id === selectedBeatId)) selectedBeatId = null;
  renderSections();
  if (selectedBeatId) renderBeat(); else { $('beatLabel').textContent = beats().length ? 'Choose “Beat at playhead” to start.' : 'No beats in this project.'; $('beatTime').value = ''; $('beatForm').querySelector('button.primary').disabled = true; }
}

/* ---------- Saving, undo and redo ---------- */
function updateHistory() { $('undo').disabled = !undoStack.length; $('redo').disabled = !redoStack.length; }
async function commit(operations, message) {
  if (!operations.length) throw new Error('Nothing to save yet.');
  const before = project.revision;
  const result = await post(projectPath() + '/corrections', {
    schema_version: 1, project_id: project.project_id, base_revision: project.revision,
    base_analysis_sha256: project.base_analysis_sha256, transaction_id: crypto.randomUUID(), operations
  });
  undoStack.push(before); redoStack = [];
  await loadProject(project.project_id, false); await refreshList();
  $('saveState').textContent = 'Saved · ' + project.revision + (project.revision === 1 ? ' edit' : ' edits'); $('saveState').className = 'save-state ok';
  status(message || 'Saved.');
  return result;
}
async function moveInHistory(from, to, label) {
  if (!from.length) return;
  const target = from.pop(), current = project.revision;
  try {
    await post(projectPath() + '/restore', {correction: {schema_version: 1, project_id: project.project_id, base_revision: current,
      base_analysis_sha256: project.base_analysis_sha256, transaction_id: crypto.randomUUID()}, target_revision: target});
  } catch (error) { from.push(target); throw error; }
  to.push(current);
  await loadProject(project.project_id, false); await refreshList();
  status(label);
}
$('undo').onclick = handle(() => moveInHistory(undoStack, redoStack, 'Undid your last change.'));
$('redo').onclick = handle(() => moveInHistory(redoStack, undoStack, 'Redid the change.'));
$('reload').onclick = handle(() => loadProject(project.project_id));
$('projects').onchange = handle(async () => { if ($('projects').value) await loadProject($('projects').value); });
$('analysisFile').onchange = () => { if ($('analysisFile').files.length) $('analysisPath').value = ''; };
$('analysisPath').oninput = () => { if ($('analysisPath').value.trim()) $('analysisFile').value = ''; };
$('import').onsubmit = handle(async () => {
  const file = $('analysisFile').files[0], path = $('analysisPath').value.trim();
  if (!file && !path) throw new Error('Choose an analysis JSON file first.');
  let body;
  if (file) {
    try { body = {analysis_data: JSON.parse((await file.text()).replace(/^﻿/, ''))}; }
    catch { throw new Error('That file is not valid JSON. Choose an analysis file made by this studio or the command line.'); }
  } else body = {analysis_path: path};
  const result = await post('/api/v1/projects', body);
  await loadProject(result.project_id); await refreshList();
});

/* ---------- Step 4: export ---------- */
function renderExport() {
  const ready = !!project;
  $('exportJson').disabled = !ready; $('exportSummary').hidden = !ready; $('exportBack').hidden = !ready;
  if (!ready) { $('exportTitle').textContent = 'Export'; $('exportInfo').textContent = 'Open a project in Review first, then come back here.'; $('exportWarning').hidden = true; return; }
  const ws = words(), untimed = ws.filter(w => w.start == null).length, guessed = ws.filter(w => w.timing_status === 'guessed').length;
  const edited = ws.filter(w => w.provenance?.method === 'user_set').length;
  $('exportTitle').textContent = songName(project.analysis.source);
  $('exportInfo').textContent = 'Revision ' + project.revision + ' includes everything you have saved.';
  $('exportSummary').innerHTML = [['Words', ws.length], ['Still without a time', untimed], ['Guessed, not yet approved', guessed], ['Words you set or approved', edited], ['Sections', sections().length], ['Beats', beats().length]]
    .map(([label, value]) => '<div><b>' + value + '</b><span>' + label + '</span></div>').join('');
  const problems = [];
  if (untimed) problems.push(untimed + ' word' + (untimed === 1 ? ' has' : 's have') + ' no time');
  if (guessed) problems.push(guessed + ' time' + (guessed === 1 ? ' is' : 's are') + ' still a guess');
  $('exportWarning').hidden = !problems.length;
  $('exportWarningText').textContent = problems.join(' and ') + '. You can export anyway, or go back and finish them first.';
}
$('toExport').onclick = () => showTab('export');
$('exportBack').onclick = () => showTab('review');
$('exportReview').onclick = () => { showTab('review'); setSideTab('issues'); };
$('exportJson').onclick = handle(async () => {
  if (!project) throw new Error('Open a project in Review first.');
  const analysis = await post(projectPath() + '/export', {});
  const url = URL.createObjectURL(new Blob([JSON.stringify(analysis, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url;
  link.download = songName(analysis.source).replace(/\.[^.]+$/, '') + '.analysis.json';
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  status('Downloaded ' + link.download + '.');
});

/* ---------- Keyboard ---------- */
document.addEventListener('keydown', event => {
  if (event.defaultPrevented || event.altKey || $('helpDialog').open) return;
  if (event.key === 'Escape' && currentTab() === 'review' && selectedWord != null) { clearSelection(); if (document.activeElement?.blur) document.activeElement.blur(); return; }
  const typing = event.target.closest('input,textarea,select,[contenteditable]');
  if (event.key === 'Enter' && event.ctrlKey && selectedWord != null && !$('wordForm').hidden) { event.preventDefault(); handle(saveSelectedWord)(); return; }
  if (typing || event.ctrlKey || event.metaKey) return;
  if (event.key === '?') { event.preventDefault(); $('helpDialog').showModal(); return; }
  if (currentTab() !== 'review' || !project) return;
  const onButton = event.target.closest('button');
  if (event.key === ' ' && (!onButton || onButton.closest('#lyrics'))) { event.preventDefault(); handle(togglePlay)(); }
  else if (event.key.toLowerCase() === 'n') { gotoIssue(1); }
  else if (event.key.toLowerCase() === 'p') { gotoIssue(-1); }
  else if (event.key.toLowerCase() === 'l') { handle(loopSelectedLine)(); }
  else if (event.key.toLowerCase() === 'f') { setFollow(!follow); }
});

/* ---------- Frame loop ---------- */
let shownClock = '';
function repaint() {
  if (playback && !$('panel-review').hidden && project) {
    const time = playback.position();
    const clock = seconds(time);
    if (clock !== shownClock) { shownClock = clock; $('clock').textContent = clock; }
    $('seek').value = time;
    $('playhead').style.left = (time / playback.duration * 100) + '%';
    const label = playback.running ? '❚❚ Pause' : '▶ Play';
    if ($('play').textContent !== label) $('play').textContent = label;
    if (auditionEnd != null && playback.running && time >= auditionEnd) { auditionEnd = null; playback.pause(); }
    const active = playback.active(words()), key = active.map(w => w.id).join(',');
    if (key !== activeKey) {
      wordEls.forEach(el => el?.classList.remove('active'));
      active.forEach(w => wordEls[wordIndex.get(w.id)]?.classList.add('active'));
      activeKey = key;
    }
    const li = lineAt(time);
    if (li !== activeLine) {
      lineEls[activeLine]?.classList.remove('active');
      lineEls[li]?.classList.add('active');
      activeLine = li;
      if (skipNextFollow) skipNextFollow = false;
      else if (follow && li >= 0) scrollToLine(li);
    }
    $('jumpNow').hidden = follow;
  }
  requestAnimationFrame(repaint);
}

applyPreset(document.querySelector('[name=preset]:checked').value); updateMode(); setSideTab('word'); repaint();
if (token) handle(connect)();
else { $('connectionStatus').textContent = 'Not connected'; status('Run song-service.cmd to open and connect the studio.'); }
setInterval(() => {
  if (token && !document.hidden) refreshJobs().catch(error => { $('connectionStatus').textContent = 'Service disconnected'; status(error.message, true); });
}, 3000);
