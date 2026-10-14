/**
 * Timing guesses for untimed lyric words.
 *
 * A guess is never an alignment result. These helpers only plan interval edits;
 * the studio saves them as ordinary revision-checked corrections marked
 * `method: "guessed"`, and approving a guess turns it into a user-set time.
 */
export const GUESS_DEFAULTS = Object.freeze({ close: false, successive: false, snap: false, maxGap: 4 });
const MIN_SLOT = 0.03;      // seconds a word needs, at least, to be placed at all
const SLOT_MARGIN = 0.05;   // fraction of an even slot left empty on each side
const SNAP_REACH = 0.15;    // furthest a beat snap may move a guessed word (seconds)

const timed = word => word.start != null && word.end != null;
const round = value => Math.round(value * 1000) / 1000;
const letters = text => (String(text).match(/[\p{L}\p{N}]/gu) || []).length;
/** Typical sung duration for one word; a guess never exceeds the gap it fills. */
export const typicalDuration = text => Math.min(0.6, Math.max(0.15, 0.12 + 0.045 * letters(text)));

/** Maximal runs of consecutive untimed words as {from, to} (to exclusive). */
export function untimedRuns(words) {
  const runs = [];
  for (let i = 0; i < words.length;) {
    if (timed(words[i])) { i++; continue; }
    let j = i; while (j < words.length && !timed(words[j])) j++;
    runs.push({ from: i, to: j }); i = j;
  }
  return runs;
}

function nearestBeat(beats, time) {
  let low = 0, high = beats.length - 1;
  while (low < high) { const mid = (low + high) >> 1; if (beats[mid].time < time) low = mid + 1; else high = mid; }
  const candidates = [beats[low - 1], beats[low]].filter(Boolean);
  return candidates.sort((a, b) => Math.abs(a.time - time) - Math.abs(b.time - time))[0]?.time;
}

/**
 * Plan guesses.
 * @param words ordered lyric words ({id, text, start, end})
 * @param options {close, successive, snap, maxGap}; `successive` only counts when `close` is on
 * @param beats ordered beats ({time}), used only when `snap` is on
 * @param scope optional Set of word ids; only untimed words in scope receive guesses
 * @returns {guesses, skipped, counts}
 */
export function planGuesses(words, options = {}, beats = [], scope = null) {
  const settings = { ...GUESS_DEFAULTS, ...options };
  const guesses = [], skipped = [];
  const counts = { close: 0, successive: 0, snapped: 0, needsSuccessive: 0, noRoom: 0, tooLong: 0, edge: 0, untimed: 0 };
  for (const { from, to } of untimedRuns(words)) {
    const run = words.slice(from, to);
    if (scope && !run.some(word => scope.has(word.id))) continue;
    counts.untimed += scope ? run.filter(word => scope.has(word.id)).length : run.length;
    if (!settings.close) continue;
    const ids = run.map(word => word.id);
    const before = words[from - 1], after = words[to];
    if (!before || !after) { counts.edge += run.length; skipped.push({ ids, reason: 'edge' }); continue; }
    if (run.length > 1 && !settings.successive) { counts.needsSuccessive += run.length; skipped.push({ ids, reason: 'successive_off' }); continue; }
    const gap = after.start - before.end;
    if (gap > settings.maxGap) { counts.tooLong += run.length; skipped.push({ ids, reason: 'gap_too_long', gap }); continue; }
    if (gap < MIN_SLOT * run.length) { counts.noRoom += run.length; skipped.push({ ids, reason: 'no_room', gap }); continue; }
    const planned = run.length === 1 ? [single(run[0], before, after, gap)] : spread(run, before, gap);
    let lastEnd = before.end;
    for (const guess of planned) {
      if (settings.snap && beats.length) {
        const beat = nearestBeat(beats, guess.start);
        const shift = beat == null ? Infinity : beat - guess.start;
        if (Math.abs(shift) <= SNAP_REACH && guess.start + shift >= lastEnd && guess.end + shift <= after.start) {
          guess.start += shift; guess.end += shift; guess.snapped = true; counts.snapped++;
        }
      }
      guess.start = round(guess.start); guess.end = Math.max(round(guess.end), guess.start + 0.001);
      lastEnd = guess.end;
      if (!scope || scope.has(guess.id)) { guesses.push(guess); counts[run.length === 1 ? 'close' : 'successive']++; }
    }
  }
  return { guesses, skipped, counts };
}

function single(word, before, after, gap) {
  const middle = (before.end + after.start) / 2, length = Math.min(gap, typicalDuration(word.text));
  return { id: word.id, start: middle - length / 2, end: middle + length / 2, basis: 'midpoint', snapped: false };
}
function spread(run, before, gap) {
  const slot = gap / run.length;
  return run.map((word, index) => {
    const origin = before.end + index * slot;
    return { id: word.id, start: origin + slot * SLOT_MARGIN, end: origin + slot * (1 - SLOT_MARGIN), basis: 'even_spread', snapped: false };
  });
}

/** Correction operations that save planned guesses as one transaction. */
export const guessOperations = guesses => guesses.map(guess => ({
  op: 'set_word_interval', word_id: guess.id, start: guess.start, end: guess.end, method: 'guessed', basis: guess.basis
}));
/** Correction operations that approve guesses; approved words are ordinary user-set times. */
export const approveOperations = ids => ids.map(id => ({ op: 'set_tags', kind: 'word', id, value: { review_state: 'reviewed' } }));

/** Plain-language outcome for a plan, used in the preview text. */
export function describePlan({ counts }) {
  const parts = [];
  const total = counts.close + counts.successive;
  parts.push(total ? `${total} word${total === 1 ? '' : 's'} can be guessed` : 'Nothing to guess with these settings');
  if (counts.needsSuccessive) parts.push(`${counts.needsSuccessive} more in longer runs (turn on “Guess successive untimed lyrics”)`);
  if (counts.tooLong) parts.push(`${counts.tooLong} skipped: the gap is longer than your limit`);
  if (counts.noRoom) parts.push(`${counts.noRoom} skipped: neighboring words leave no room`);
  if (counts.edge) parts.push(`${counts.edge} skipped: no timed word on one side`);
  return parts.join(' · ');
}
