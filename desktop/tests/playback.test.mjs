import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Playback } from '../src/playback.mjs';

function setup() {
  const nodes = [];
  const context = { currentTime: 10, destination: {}, resume: async () => {},
    getOutputTimestamp: () => ({ contextTime: context.currentTime - 0.04 }),
    createGain: () => ({ gain: { value: 0, setValueAtTime(value) { this.value = value; }, exponentialRampToValueAtTime() {} }, connect() {}, disconnect() {} }),
    createBufferSource() { const node = { playbackRate: {}, connect() {}, disconnect() {}, start(when, offset) { this.when = when; this.offset = offset; }, stop() {} }; nodes.push(node); return node; },
    createOscillator() { const node = { frequency: {}, connect() {}, disconnect() {}, start(when) { this.when = when; }, stop() {} }; nodes.push(node); return node; }
  };
  const playback = new Playback(context); playback.duration = 20;
  playback.buffers = new Map([['mix', { duration: 20 }], ['vocals', { duration: 20 }]]);
  return { playback, context, nodes };
}

test('audio clock, output latency, slow playback, track selection and seek share origin', async () => {
  const { playback: p, context: c } = setup();
  await p.play(); assert.equal(p.sources[0].node.when, p.sources[1].node.when);
  c.currentTime = 12.03; assert.ok(Math.abs(p.position() - 1.96) < 1e-9);
  p.selectTrack('vocals'); assert.ok(Math.abs(p.position() - 1.96) < 1e-9);
  assert.equal(p.sources[0].gain.gain.value, 0);
  p.setRate(0.5); c.currentTime += 2.07;
  assert.ok(Math.abs(p.position() - 2.96) < 1e-9);
  p.seek(5); c.currentTime += 1.07; assert.ok(Math.abs(p.position() - 5.5) < 1e-9);
  p.pause(); const paused = p.position(); c.currentTime += 10; assert.equal(p.position(), paused);
});

test('loop wraps audio time and overlapping words remain active', async () => {
  const { playback: p, context: c } = setup();
  p.setLoop(2, 4); await p.play(); c.currentTime += 5.07;
  assert.ok(Math.abs(p.position() - 3) < 1e-9);
  assert.equal(p.active([{ start: 2, end: 4 }, { start: 2.5, end: 3.5 }, { start: null, end: null }]).length, 2);
  assert.throws(() => p.setLoop(4, 2)); assert.throws(() => p.seek(NaN));
});

test('metronome schedules audio nodes once per beat, including repeated loop', async () => {
  const { playback: p, context: c, nodes } = setup();
  p.setLoop(2, 4); await p.play();
  p.setMetronome(true, [{ time: 2.1, position_in_bar: 1 }, { time: 3.9 }]);
  p.scheduleMetronome(0.5); p.scheduleMetronome(0.5);
  assert.equal(nodes.filter(n => n.frequency).length, 1);
  c.currentTime += 2; p.scheduleMetronome(0.5);
  assert.equal(nodes.filter(n => n.frequency).length, 2);
});

test('manifest mismatch and nonzero offsets are rejected', async () => {
  const { playback: p, context: c } = setup();
  c.decodeAudioData = async () => ({ duration: 20 });
  const fetcher = async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(0) });
  await assert.rejects(p.load([{ id: 'mix', offset_seconds: 1, duration_seconds: 20 }], fetcher));
  await assert.rejects(p.load([{ id: 'mix', offset_seconds: 0, duration_seconds: 10 }], fetcher));
});
