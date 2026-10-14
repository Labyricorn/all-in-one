/** Original-audio timebase driven by Web Audio, independent of repaint frequency. */
export class Playback {
  constructor(context, { scheduleLead = 0.03, latencyCorrection = 0 } = {}) {
    this.context = context;
    this.lead = scheduleLead;
    this.latencyCorrection = latencyCorrection;
    this.buffers = new Map(); this.sources = []; this.clicks = [];
    this.duration = 0; this.offset = 0; this.rate = 1;
    this.running = false; this.loop = null; this.track = 'mix';
    this.beats = []; this.metronome = false; this.scheduledUntil = 0;
  }
  async load(artifacts, fetcher = fetch) {
    this.pause();
    const decoded = await Promise.all(artifacts.map(async artifact => {
      if (artifact.offset_seconds !== 0) throw new Error('Playback requires original-origin PCM artifacts.');
      const response = await fetcher(artifact.url);
      if (!response.ok) throw new Error(`Artifact download failed (${response.status}).`);
      const buffer = await this.context.decodeAudioData(await response.arrayBuffer());
      if (Math.abs(buffer.duration - artifact.duration_seconds) > 0.05) throw new Error('Decoded duration does not match the manifest.');
      return [artifact.id, buffer];
    }));
    if (!decoded.length || !decoded.some(([id]) => id === 'mix')) throw new Error('A mix artifact is required.');
    if (decoded.some(([, buffer]) => Math.abs(buffer.duration - decoded[0][1].duration) > 0.05)) throw new Error('Mix and stem timebases differ.');
    this.buffers = new Map(decoded); this.duration = this.buffers.get('mix').duration;
    this.offset = 0; this.loop = null; this.track = 'mix';
  }
  audioTime(audible = false) {
    const stamp = audible && this.context.getOutputTimestamp?.();
    if (stamp && stamp.contextTime > 0) return stamp.contextTime - this.latencyCorrection;
    return this.context.currentTime - (audible ? (this.context.outputLatency || this.context.baseLatency || 0) + this.latencyCorrection : 0);
  }
  position(audible = true) {
    if (!this.running) return this.offset;
    let position = this.offset + Math.max(0, this.audioTime(audible) - this.anchor) * this.rate;
    if (this.loop && position >= this.loop.end) position = this.loop.start + (position - this.loop.start) % (this.loop.end - this.loop.start);
    return Math.min(this.duration, Math.max(0, position));
  }
  stopNodes() {
    for (const item of [...this.sources, ...this.clicks]) { item.node.onended = null; item.node.stop(); item.node.disconnect(); item.gain?.disconnect(); }
    this.sources = []; this.clicks = [];
  }
  startNodes() {
    this.anchor = this.context.currentTime + this.lead;
    this.scheduledUntil = this.anchor;
    for (const [id, buffer] of this.buffers) {
      const node = this.context.createBufferSource(); node.buffer = buffer;
      node.playbackRate.value = this.rate;
      if (this.loop) { node.loop = true; node.loopStart = this.loop.start; node.loopEnd = this.loop.end; }
      const gain = this.context.createGain(); gain.gain.value = id === this.track ? 1 : 0;
      node.connect(gain); gain.connect(this.context.destination);
      node.onended = () => {
        if (this.running && !this.loop && this.position(false) >= this.duration - 0.001) {
          this.offset = this.duration; this.running = false; this.stopNodes();
        }
      };
      node.start(this.anchor, this.offset);
      this.sources.push({ id, node, gain });
    }
  }
  async play() {
    if (!this.buffers.size) throw new Error('Load audio first.');
    await this.context.resume();
    if (this.running) return;
    if (this.offset >= this.duration) this.offset = this.loop?.start || 0;
    this.running = true; this.startNodes();
  }
  pause() {
    if (this.running) this.offset = this.position();
    this.running = false; this.stopNodes();
  }
  seek(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > this.duration) throw new Error('Seek must be within the original duration.');
    const playing = this.running;
    this.stopNodes(); this.offset = seconds;
    if (this.loop && (seconds < this.loop.start || seconds >= this.loop.end)) this.offset = this.loop.start;
    if (playing && this.offset < this.duration) this.startNodes();
    else this.running = false;
  }
  setRate(rate) {
    if (!Number.isFinite(rate) || rate < 0.25 || rate > 2) throw new Error('Playback rate must be 0.25..2.');
    const position = this.position(); this.rate = rate; this.seek(position);
  }
  setLoop(start = null, end = null) {
    if (start !== null && (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > this.duration || start >= end)) throw new Error('Loop must be an ordered original-audio interval.');
    const position = this.position();
    this.loop = start === null ? null : { start, end }; this.seek(position);
  }
  selectTrack(id) {
    if (!this.buffers.has(id)) throw new Error('Unknown playback track.');
    this.track = id;
    // Both sources have always run on the same clock; switching only their gains
    // preserves the audible cursor even during a loop or slow playback.
    const when = this.context.currentTime;
    for (const item of this.sources) item.gain.gain.setValueAtTime(item.id === id ? 1 : 0, when);
  }
  setMetronome(enabled, beats = this.beats) {
    this.metronome = enabled; this.beats = beats;
    for (const item of this.clicks) { item.node.stop(); item.node.disconnect(); item.gain.disconnect(); }
    this.clicks = []; this.scheduledUntil = Math.max(this.anchor || 0, this.context.currentTime);
  }
  scheduleMetronome(horizon = 0.2) {
    if (!this.running || !this.metronome) return;
    const from = Math.max(this.scheduledUntil, this.anchor, this.context.currentTime);
    const until = this.context.currentTime + horizon;
    if (until <= from) return;
    for (const beat of this.beats) {
      let first = this.anchor + (beat.time - this.offset) / this.rate;
      const looping = this.loop && beat.time >= this.loop.start && beat.time < this.loop.end;
      const period = looping ? (this.loop.end - this.loop.start) / this.rate : 0;
      if (this.loop && !looping) continue;
      if (period && first < from) first += Math.ceil((from - first) / period) * period;
      for (let when = first; when < until; when += period || Infinity) {
        if (when < from) continue;
        const node = this.context.createOscillator(), gain = this.context.createGain();
        node.frequency.value = beat.position_in_bar === 1 ? 1200 : 800;
        gain.gain.setValueAtTime(0.08, when); gain.gain.exponentialRampToValueAtTime(0.001, when + 0.025);
        node.connect(gain); gain.connect(this.context.destination);
        const item = { node, gain }; this.clicks.push(item);
        node.onended = () => { node.disconnect(); gain.disconnect(); this.clicks = this.clicks.filter(click => click !== item); };
        node.start(when); node.stop(when + 0.03);
      }
    }
    this.scheduledUntil = until;
  }
  active(rows, time = this.position()) {
    return rows.filter(row => row.start != null && row.end != null && row.start <= time && time < row.end);
  }
  dispose() { this.pause(); this.buffers.clear(); }
}
