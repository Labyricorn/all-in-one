import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planGuesses, guessOperations, approveOperations, untimedRuns, describePlan } from '../src/guess.mjs';

const w = (id, start = null, end = null) => ({ id, text: id, start, end });

test('close guess centres one untimed word between its timed neighbours', () => {
  const words = [w('a', 1, 2), w('b'), w('c', 4, 5)];
  const { guesses, counts } = planGuesses(words, { close: true });
  assert.equal(guesses.length, 1);
  assert.equal(counts.close, 1);
  const [g] = guesses;
  assert.ok(Math.abs((g.start + g.end) / 2 - 3) < 0.002, 'centred on the midpoint of the gap');
  assert.ok(g.start >= 2 && g.end <= 4, 'stays inside the gap');
  assert.equal(g.basis, 'midpoint');
});

test('a tiny gap is filled by the guess rather than overflowed', () => {
  const { guesses } = planGuesses([w('a', 0, 1), w('b'), w('c', 1.09, 2)], { close: true });
  assert.equal(guesses.length, 1);
  assert.ok(guesses[0].start >= 1 && guesses[0].end <= 1.09);
});

test('nothing is guessed unless the close option is on', () => {
  const { guesses } = planGuesses([w('a', 1, 2), w('b'), w('c', 4, 5)], {});
  assert.equal(guesses.length, 0);
});

test('successive runs need the extra option and are spread evenly', () => {
  const words = [w('a', 0, 1), w('x'), w('y'), w('z'), w('b', 4, 5)];
  const off = planGuesses(words, { close: true });
  assert.equal(off.guesses.length, 0);
  assert.equal(off.counts.needsSuccessive, 3);
  const on = planGuesses(words, { close: true, successive: true });
  assert.equal(on.guesses.length, 3);
  const [x, y, z] = on.guesses;
  assert.ok(x.start >= 1 && z.end <= 4);
  assert.ok(x.end < y.start && y.end < z.start, 'ordered, non-overlapping');
  assert.ok(Math.abs((y.end - y.start) - (x.end - x.start)) < 0.002, 'equal slots');
  assert.equal(x.basis, 'even_spread');
});

test('successive option alone does nothing without close guessing', () => {
  const { guesses } = planGuesses([w('a', 0, 1), w('x'), w('y'), w('b', 3, 4)], { successive: true });
  assert.equal(guesses.length, 0);
});

test('gaps beyond the limit, overlaps and song edges are skipped with reasons', () => {
  const long = planGuesses([w('a', 0, 1), w('x'), w('b', 20, 21)], { close: true });
  assert.equal(long.skipped[0].reason, 'gap_too_long');
  const tight = planGuesses([w('a', 0, 2), w('x'), w('b', 1.9, 3)], { close: true });
  assert.equal(tight.skipped[0].reason, 'no_room');
  const edge = planGuesses([w('x'), w('b', 1, 2)], { close: true });
  assert.equal(edge.skipped[0].reason, 'edge');
  assert.equal(planGuesses([w('a', 0, 1), w('x'), w('b', 20, 21)], { close: true, maxGap: 30 }).guesses.length, 1);
});

test('scope limits guesses to the selection but spaces the whole run', () => {
  const words = [w('a', 0, 1), w('x'), w('y'), w('b', 5, 6)];
  const { guesses } = planGuesses(words, { close: true, successive: true }, [], new Set(['y']));
  assert.deepEqual(guesses.map(g => g.id), ['y']);
  assert.ok(guesses[0].start > 3, 'second slot of the full run, not the whole gap');
  assert.equal(planGuesses(words, { close: true, successive: true }, [], new Set(['a'])).guesses.length, 0);
});

test('beat snapping is optional, bounded and keeps order', () => {
  const beats = [{ time: 2.9 }, { time: 3.1 }];
  const words = [w('a', 1, 2), w('x'), w('b', 4, 5)];
  assert.equal(planGuesses(words, { close: true }, beats).guesses[0].snapped, false);
  const snapped = planGuesses(words, { close: true, snap: true }, beats).guesses[0];
  assert.equal(snapped.snapped, true);
  assert.ok([2.9, 3.1].some(t => Math.abs(snapped.start - t) < 0.002));
  assert.ok(snapped.start >= 2 && snapped.end <= 4);
  const far = planGuesses(words, { close: true, snap: true }, [{ time: 3.9 }]).guesses[0];
  assert.equal(far.snapped, false);
});

test('operations mark guesses and approvals use ordinary tags', () => {
  const { guesses } = planGuesses([w('a', 1, 2), w('x'), w('b', 4, 5)], { close: true });
  const [op] = guessOperations(guesses);
  assert.deepEqual([op.op, op.word_id, op.method, op.basis], ['set_word_interval', 'x', 'guessed', 'midpoint']);
  assert.ok(op.end > op.start);
  assert.deepEqual(approveOperations(['x'])[0], { op: 'set_tags', kind: 'word', id: 'x', value: { review_state: 'reviewed' } });
});

test('runs and plan description', () => {
  assert.deepEqual(untimedRuns([w('a'), w('b', 1, 2), w('c'), w('d')]), [{ from: 0, to: 1 }, { from: 2, to: 4 }]);
  assert.match(describePlan(planGuesses([w('a', 0, 1), w('x'), w('b', 2, 3)], { close: true })), /1 word can be guessed/);
});
