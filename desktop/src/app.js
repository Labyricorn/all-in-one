import { Playback } from './playback.mjs';

const $ = id => document.getElementById(id);
const projectPath = () => '/api/v1/projects/' + project.project_id;
let token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
let project = null, playback = null, selectedWord = null, previewUrl = null;
let uploadedFile = null, uploadedMedia = null, jobsLoading = false, waveformPeaks = null;
const jobLogs = new Map();
let wordLines = new Map();
const timingText = value => value == null ? '' : String(Number(value.toFixed(3)));
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
  return String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
}
function songName(source) {
  return String(source || 'Untitled song').split(/[\\/]/).pop().replace(/^input-/, '');
}
function seconds(value) {
  return Math.floor(value / 60) + ':' + String(Math.floor(value % 60)).padStart(2, '0');
}
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
    ...options, headers: {Authorization: 'Bearer ' + token,
      'Content-Type': 'application/json', ...options.headers}
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) $('connectionStatus').textContent = 'Reconnect with song-service.cmd';
    throw new Error(body.error || 'Request failed (' + response.status + ').');
  }
  return body;
}
const post = (path, body) => api(path, {method:'POST', body:JSON.stringify(body)});
const words = () => project?.analysis.lyrics?.words || [];
const beats = () => project?.analysis.beats || [];
const sections = () => project?.analysis.sections || [];

function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach(tab => {
    const active = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    $('panel-' + tab.dataset.tab).hidden = !active;
  });
  const prompts = {
    analyze:'Choose audio, set the lyric workflow and start analysis.',
    jobs:'Job stages update automatically. Open a completed result to review it.',
    review:project ? 'Select a word to inspect its text and timing.' : 'Choose a saved project or open a completed analysis.',
    export:project ? 'Download the selected project’s latest saved analysis.' : 'Choose a project in Review before exporting.'
  };
  status(prompts[name]);
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

async function refreshList() {
  const result = await api('/api/v1/projects');
  const selected = project?.project_id || $('projects').value;
  $('projects').innerHTML = '<option value="">Choose a project</option>' +
    result.projects.map(p => '<option value="' + p.project_id + '">' +
      escapeHtml((p.name || p.project_id).replace(/^input-/, '')) + ' · rev ' + p.revision + '</option>').join('');
  $('projects').value = selected;
  $('emptyProjects').hidden = result.projects.length > 0;
}
async function refreshJobs() {
  if (jobsLoading) return;
  jobsLoading = true;
  try {
    const result = await api('/api/v1/jobs');
    $('jobCount').textContent = result.jobs.filter(j => ['queued','running'].includes(j.status)).length || '';
    $('emptyJobs').hidden = result.jobs.length > 0;
    $('jobs').innerHTML = result.jobs.map(job => {
      const active = ['queued','running'].includes(job.status);
      const ready = ['complete','partial'].includes(job.status);
      return '<article class="card job-card">' +
        '<div class="row spread"><h3>' + escapeHtml(songName(job.source)) + '</h3>' +
        '<span class="badge ' + escapeHtml(job.status) + '">' + escapeHtml(job.status) + '</span></div>' +
        '<p class="job-stage">' + escapeHtml((job.stage || 'waiting').replaceAll('_',' ')) + '</p>' +
        (active ? '<div class="activity" aria-label="Analysis in progress"></div>' : '') +
        (job.error ? '<p class="job-error">' + escapeHtml(job.error) + '</p>' : '') +
        '<small>' + (job.created ? new Date(job.created * 1000).toLocaleString() + ' · ' : '') +
        escapeHtml(job.job_id.slice(0,8)) + '</small>' +
        '<div class="job-actions">' +
        (ready ? '<button data-open-job="' + job.job_id + '">Open in Review →</button>' : '') +
        (active ? '<button class="secondary" data-cancel-job="' + job.job_id + '">Cancel analysis</button>' : '') +
        (['failed','partial','cancelled'].includes(job.status) ? '<button class="secondary" data-job-log="' + job.job_id + '">Details</button>' : '') +
        '</div><pre id="log-' + job.job_id + '"' + (jobLogs.has(job.job_id) ? '' : ' hidden') + '>' +
        escapeHtml(jobLogs.get(job.job_id) || '') + '</pre></article>';
    }).join('');
    document.querySelectorAll('[data-open-job]').forEach(button => button.onclick = handle(async () => {
      button.disabled = true;
      try {
        const id = button.dataset.openJob;
        let saved;
        try { saved = sessionStorage.getItem('job-project-' + id); } catch {}
        if (!saved) {
          status('Opening analysis and cached audio…');
          const result = await post('/api/v1/projects', {job_id:id});
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
        await refreshJobs(); status('Analysis cancelled; its diagnostics are retained.');
      } finally { button.disabled = false; }
    }));
    document.querySelectorAll('[data-job-log]').forEach(button => button.onclick = handle(async () => {
      const job = await api('/api/v1/jobs/' + button.dataset.jobLog);
      const log = $('log-' + job.job_id);
      log.textContent = job.diagnostic_log_tail || job.error || 'No additional diagnostics.';
      log.hidden = !log.hidden;
      if (log.hidden) jobLogs.delete(job.job_id); else jobLogs.set(job.job_id, log.textContent);
    }));
  } finally { jobsLoading = false; }
}
async function connect() {
  token = $('token').value.trim();
  try { sessionStorage.setItem('mgmv-token', token); } catch {}
  await Promise.all([refreshList(), refreshJobs()]);
  $('connectionStatus').textContent = '● Local service connected';
  status('Ready. Choose audio to analyze, or open a saved project in Review.');
}
$('connect').onclick = handle(connect);
$('refresh').onclick = handle(refreshList);
$('refreshJobs').onclick = handle(refreshJobs);

$('audioFile').onchange = () => {
  const file = $('audioFile').files[0];
  uploadedFile = uploadedMedia = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  $('audioPreview').pause(); $('audioPreview').hidden = !file;
  $('audioName').textContent = file?.name || 'Choose a song';
  $('audioDetails').textContent = file ? (file.size / 1024 / 1024).toFixed(1) + ' MB · ready to analyze' : 'WAV, MP3, FLAC, M4A or video with audio';
  if (file) { previewUrl = URL.createObjectURL(file); $('audioPreview').src = previewUrl; }
  $('submissionState').textContent = file ? 'Ready to start.' : 'Choose a file to begin.';
};
function updateMode() {
  const mode = $('lyricsMode').value;
  $('lyricsInput').hidden = mode !== 'align';
  $('lyricsText').required = mode === 'align';
  $('language').required = mode === 'align';
  $('lyricModel').disabled = ['none','instrumental'].includes(mode);
}
$('lyricsMode').onchange = updateMode;
$('lyricsFile').onchange = handle(async () => {
  const file = $('lyricsFile').files[0];
  if (file) $('lyricsText').value = (await file.text()).replace(/^\uFEFF/, '');
});
$('analyzeForm').onsubmit = handle(async () => {
  const file = $('audioFile').files[0];
  if (!file) throw new Error('Choose an audio or video file.');
  const mode = $('lyricsMode').value;
  if (mode === 'align' && (!$('lyricsText').value.trim() || !$('language').value))
    throw new Error('Supplied lyrics need lyric text and a language.');
  $('audioPreview').pause();
  try {
    if (uploadedFile !== file) {
      $('submissionState').textContent = 'Copying and checking ' + file.name + '…';
      status('Loading selected audio into the local analysis workspace…');
      uploadedMedia = await api('/api/v1/media', {method:'POST', body:file,
        headers:{'Content-Type':'application/octet-stream', 'X-Filename':encodeURIComponent(file.name)}});
      uploadedFile = file;
    }
    $('submissionState').textContent = 'Starting analysis…';
    const result = await post('/api/v1/jobs', {
      path:uploadedMedia.path, lyrics_mode:mode,
      lyrics_text:mode === 'align' ? $('lyricsText').value : null,
      language:$('language').value || null,
      music_model:$('musicModel').value, lyric_model:$('lyricModel').value,
      offline:$('offline').checked
    });
    $('submissionState').textContent = 'Job accepted · ' + result.job_id.slice(0,8);
    await refreshJobs(); showTab('jobs');
    status('Analysis started. You can follow its stages here.');
  } catch (error) {
    $('submissionState').textContent = error.message;
    throw error;
  }
});

async function loadProject(id, reloadAudio = true) {
  status('Loading project…');
  const changed = project?.project_id !== id;
  project = await api('/api/v1/projects/' + encodeURIComponent(id));
  if (changed) { selectedWord = null; $('wordFilter').value = ''; $('lineSelect').value = ''; }
  $('editor').hidden = false; $('projects').value = id;
  const name = songName(project.analysis.source);
  $('projectTitle').textContent = name;
  $('revision').textContent = 'Revision ' + project.revision + ' · ' + project.analysis.duration_seconds.toFixed(2) + ' s · ' + words().length + ' words';
  $('exportTitle').textContent = name;
  $('exportInfo').textContent = 'Revision ' + project.revision + ' · includes your saved corrections.';
  $('exportJson').disabled = false;
  renderEditor();
  if (reloadAudio) await loadAudio();
  else { playback?.setMetronome($('metro').checked, beats()); drawWaveform(); }
  status('Project ready. Select a word to inspect or audition it.');
}
async function loadAudio() {
  if (playback) { const context = playback.context; playback.dispose(); await context.close(); }
  playback = null; waveformPeaks = null;
  const artifacts = project.artifacts || [];
  const hasMix = artifacts.some(a => a.id === 'mix');
  document.querySelectorAll('.player button,.player select,.player input').forEach(el => el.disabled = !hasMix);
  $('track').querySelector('[value="vocals"]').disabled = !artifacts.some(a => a.id === 'vocals');
  $('track').value = 'mix'; $('rate').value = '1'; $('seek').value = '0';
  $('duration').textContent = seconds(project.analysis.duration_seconds);
  if (!hasMix) { $('clock').textContent = 'No audio attached'; drawWaveform(); return; }
  playback = new Playback(new AudioContext());
  await playback.load(artifacts.map(a => ({...a, url:projectPath() + '/artifacts/' + a.id})),
    url => fetch(url, {headers:{Authorization:'Bearer ' + token}}));
  $('seek').max = playback.duration;
  $('loopEnd').value = Math.min(5, playback.duration);
  playback.setMetronome($('metro').checked, beats());
  const pcm = playback.buffers.get('mix').getChannelData(0);
  waveformPeaks = Array.from({length:600}, (_, i) => {
    const start = Math.floor(i * pcm.length / 600), end = Math.floor((i + 1) * pcm.length / 600);
    let peak = 0;
    for (let j = start; j < end; j += 8) peak = Math.max(peak, Math.abs(pcm[j]));
    return peak;
  });
  drawWaveform();
}
function drawWaveform() {
  const canvas = $('waveform'), ctx = canvas.getContext('2d'), width = canvas.width, height = canvas.height;
  ctx.clearRect(0,0,width,height);
  const duration = project?.analysis.duration_seconds || 1;
  sections().forEach((s,i) => {
    ctx.fillStyle = i % 2 ? '#142735' : '#172e35';
    ctx.fillRect(s.start / duration * width,0,(s.end-s.start) / duration * width,height);
    ctx.fillStyle = '#9aaeb4'; ctx.font = '11px system-ui';
    ctx.fillText(s.label || '',s.start / duration * width + 5,14);
  });
  ctx.fillStyle = '#57c2b4';
  waveformPeaks?.forEach((peak,i) => {
    const amplitude = Math.max(1,peak * (height - 30) / 2);
    ctx.fillRect(i * width / waveformPeaks.length,height / 2 - amplitude,1.5,amplitude * 2);
  });
  ctx.strokeStyle = '#b7f0d955';
  beats().filter(b => b.position_in_bar === 1).forEach(b => {
    const x = b.time / duration * width; ctx.beginPath(); ctx.moveTo(x,height-12); ctx.lineTo(x,height); ctx.stroke();
  });
}
function renderWords() {
  const filter = $('wordFilter').value.toLowerCase(), line = $('lineSelect').value;
  $('words').innerHTML = words().map((w,i) => ({w,i}))
    .filter(({w}) => (!filter || w.text.toLowerCase().includes(filter)) && (!line || wordLines.get(w.id)?.id === line))
    .map(({w,i}) => '<button class="word' + (selectedWord === i ? ' selected' : '') + '" data-index="' + i + '">' +
      '<span>' + escapeHtml(w.text) + '</span><span>' + (w.start == null ? 'untimed' : w.start.toFixed(2) + ' s') +
      '</span><small>' + escapeHtml(wordLines.get(w.id)?.name || '') + ' · ' + (w.end == null ? '—' : w.end.toFixed(2) + ' s') + '</small></button>').join('');
  document.querySelectorAll('[data-index]').forEach(button => button.onclick = handle(() => {
    chooseWord(Number(button.dataset.index));
    const w = words()[selectedWord];
    if (playback && w.start != null) playback.seek(w.start);
  }));
}
function chooseWord(index) {
  selectedWord = index; const word = words()[index];
  $('wordText').value = word?.text || '';
  $('wordStart').value = timingText(word?.start); $('wordEnd').value = timingText(word?.end);
  $('wordForm').querySelector('button').disabled = !word;
  renderWords();
}
function chooseBeat() { $('beatTime').value = timingText(beats()[Number($('beatSelect').value)]?.time); }
function chooseSection() {
  const section = sections()[Number($('sectionSelect').value)];
  $('sectionLabel').value = section?.label || '';
  $('sectionStart').value = timingText(section?.start); $('sectionEnd').value = timingText(section?.end);
}
function renderEditor() {
  const line = $('lineSelect').value;
  const lines = (project.analysis.lyrics?.phrases || []).map((line,i) => ({...line,name:'Line ' + (i+1)}));
  wordLines = new Map(lines.flatMap(line => line.word_ids.map(id => [id,line])));
  $('lineSelect').innerHTML = '<option value="">All lines</option>' + lines.map(line => '<option value="' + escapeHtml(line.id) + '">' + line.name + ' · ' + escapeHtml(line.text.slice(0,45)) + '</option>').join('');
  $('lineSelect').value = line;
  const beatIndex = $('beatSelect').value, sectionIndex = $('sectionSelect').value;
  $('beatSelect').innerHTML = beats().map((b,i) => '<option value="' + i + '">Beat ' + (i+1) + ' · ' + b.time.toFixed(2) + ' s</option>').join('');
  $('sectionSelect').innerHTML = sections().map((s,i) => '<option value="' + i + '">' + escapeHtml(s.label) + '</option>').join('');
  if (beatIndex) $('beatSelect').value = beatIndex;
  if (sectionIndex) $('sectionSelect').value = sectionIndex;
  chooseBeat(); chooseSection(); chooseWord(selectedWord);
  $('review').textContent = JSON.stringify(project.analysis.review_items || [],null,2);
  $('wordForm').querySelector('button').disabled = !words()[selectedWord];
  $('beatForm').querySelector('button').disabled = !beats().length;
  $('sectionForm').querySelector('button').disabled = !sections().length;
}
async function commit(operations) {
  if (!operations.length) throw new Error('No changes to save.');
  const result = await post(projectPath() + '/corrections', {
    schema_version:1, project_id:project.project_id, base_revision:project.revision,
    base_analysis_sha256:project.base_analysis_sha256, transaction_id:crypto.randomUUID(), operations
  });
  await loadProject(project.project_id,false); await refreshList();
  status('Saved revision ' + result.revision + '.');
}
$('projects').onchange = handle(async () => { if ($('projects').value) await loadProject($('projects').value); });
$('reload').onclick = handle(() => loadProject(project.project_id));
$('wordFilter').oninput = renderWords; $('lineSelect').onchange = renderWords;
$('beatSelect').onchange = chooseBeat; $('sectionSelect').onchange = chooseSection;
$('analysisFile').onchange = () => { if ($('analysisFile').files.length) $('analysisPath').value = ''; };
$('analysisPath').oninput = () => { if ($('analysisPath').value.trim()) $('analysisFile').value = ''; };
$('import').onsubmit = handle(async () => {
  const file = $('analysisFile').files[0], path = $('analysisPath').value.trim();
  if (!file && !path) throw new Error('Choose an analysis JSON file.');
  let body;
  if (file) {
    try { body = {analysis_data:JSON.parse((await file.text()).replace(/^\uFEFF/,''))}; }
    catch { throw new Error('The selected file is not valid JSON.'); }
  } else body = {analysis_path:path};
  const result = await post('/api/v1/projects',body);
  await loadProject(result.project_id); await refreshList();
});
$('wordForm').onsubmit = handle(async () => {
  const word = words()[selectedWord];
  if (!word) throw new Error('Choose a word first.');
  const operations = [], start = editedTiming($('wordStart'),word.start);
  const end = editedTiming($('wordEnd'),word.end);
  if ($('wordText').value !== word.text) operations.push({op:'replace_word',word_id:word.id,text:$('wordText').value});
  if (start !== word.start || end !== word.end) operations.push({op:'set_word_interval',word_id:word.id,start,end});
  await commit(operations);
});
$('beatForm').onsubmit = handle(async () => {
  const beat = beats()[Number($('beatSelect').value)], time = editedTiming($('beatTime'),beat.time);
  await commit(time === beat.time ? [] : [{op:'set_beat',beat_id:beat.id,time}]);
});
$('sectionForm').onsubmit = handle(async () => {
  const section = sections()[Number($('sectionSelect').value)], operations = [];
  if ($('sectionLabel').value !== section.label) operations.push({op:'set_section',section_id:section.id,value:{label:$('sectionLabel').value}});
  const start = editedTiming($('sectionStart'),section.start), end = editedTiming($('sectionEnd'),section.end);
  if (start !== section.start || end !== section.end) operations.push({op:'set_section_interval',section_id:section.id,start,end});
  await commit(operations);
});
$('play').onclick = handle(() => playback?.play()); $('pause').onclick = () => playback?.pause();
$('track').onchange = handle(() => playback?.selectTrack($('track').value));
$('rate').onchange = handle(() => playback?.setRate(Number($('rate').value)));
$('seek').oninput = handle(() => playback?.seek(Number($('seek').value)));
$('metro').onchange = handle(() => playback?.setMetronome($('metro').checked,beats()));
$('setLoop').onclick = handle(() => playback?.setLoop(Number($('loopStart').value),Number($('loopEnd').value)));
$('clearLoop').onclick = handle(() => playback?.setLoop());
$('waveform').onclick = handle(event => {
  if (playback) { const rect = event.currentTarget.getBoundingClientRect(); playback.seek(Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*playback.duration); }
});
$('exportJson').onclick = handle(async () => {
  if (!project) throw new Error('Choose a project in Review.');
  const analysis = await post(projectPath() + '/export',{});
  const url = URL.createObjectURL(new Blob([JSON.stringify(analysis,null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href = url;
  link.download = songName(analysis.source).replace(/\.[^.]+$/, '') + '.analysis.json';
  link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  status('Downloaded the latest saved analysis.');
});

let previousActive = '';
function repaint() {
  if (playback && !$('panel-review').hidden) {
    const time = playback.position();
    $('seek').value = time; $('clock').textContent = seconds(time);
    $('playhead').style.left = (time / playback.duration * 100) + '%';
    const active = playback.active(words()), ids = new Set(active.map(w => w.id));
    const activeKey = active.map(w => w.id).join(',');
    if (activeKey !== previousActive) {
      previousActive = activeKey;
      $('activeWords').textContent = active.map(w => w.text).join(' / ');
      document.querySelectorAll('.word').forEach(el => el.classList.toggle('active',ids.has(words()[Number(el.dataset.index)]?.id)));
    }
  }
  requestAnimationFrame(repaint);
}
setInterval(() => playback?.scheduleMetronome(),50);
setInterval(() => {
  if (token && !document.hidden) refreshJobs().catch(error => {
    $('connectionStatus').textContent = 'Service disconnected';
    status(error.message,true);
  });
},3000);
updateMode(); repaint();
if (token) handle(connect)();
else { $('connectionStatus').textContent = 'Not connected'; status('Run song-service.cmd to open and connect the studio.'); }
