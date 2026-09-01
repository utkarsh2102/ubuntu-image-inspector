/**
 * Parity between the two diff implementations.
 *
 * collector/uii/diff.py runs in CI to precompute steps; site/js/diff/engine.js
 * runs in the browser for arbitrary comparisons. Duplicating the algorithm is
 * only acceptable because this test holds both to the same golden fixture
 * generated from real published manifests.
 *
 * Run: node --test site/tests/
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { diffManifests } from '../js/diff/engine.js';

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, '..', '..', 'collector', 'tests', 'fixtures');

/** Parse a manifest the same way collector/uii/manifest.py does. */
function parseManifest(text) {
  const packages = [];
  const snaps = [];
  for (const raw of text.split('\n')) {
    if (!raw.trim()) continue;
    let fields = raw.split('\t');
    if (fields.length < 2) fields = raw.split(/\s+/);
    if (fields.length < 2) continue;

    const head = fields[0].trim();
    if (head.startsWith('snap:')) {
      const name = head.slice('snap:'.length).trim();
      const channel = fields[1].trim();
      const digits = (fields[2] || '').replace(/\D/g, '');
      if (name && digits) snaps.push({ name, channel, rev: Number(digits) });
      continue;
    }
    const version = fields[1].trim();
    if (!head || !version) continue;
    const name = head.includes(':') ? head.slice(0, head.indexOf(':')) : head;
    packages.push([name, version]);
  }
  return { packages, snaps };
}

function load(name) {
  return parseManifest(readFileSync(join(fixtures, name), 'utf8'));
}

test('JS diff matches the Python golden fixture exactly', () => {
  const a = load('live-server-amd64.snapshot3.manifest');
  const b = load('live-server-amd64.snapshot4.manifest');
  const got = diffManifests(a, b);

  const golden = JSON.parse(readFileSync(join(fixtures, 'diff.golden.json'), 'utf8'));

  // The JS engine carries extra snap size fields the Python side has no
  // source for; compare the shared contract.
  assert.deepEqual(got.counts, golden.counts);
  assert.deepEqual(got.added, golden.added);
  assert.deepEqual(got.removed, golden.removed);
  assert.deepEqual(got.changed, golden.changed);

  assert.deepEqual(
    got.snapChanged.map((s) => ({
      name: s.name,
      fromRev: s.fromRev,
      toRev: s.toRev,
      fromChannel: s.fromChannel,
      toChannel: s.toChannel,
    })),
    golden.snapChanged
  );
});

test('classification is exclusive', () => {
  const a = { packages: [['keep', '1'], ['gone', '1'], ['bump', '1']], snaps: [] };
  const b = { packages: [['keep', '1'], ['new', '1'], ['bump', '2']], snaps: [] };
  const d = diffManifests(a, b);
  assert.deepEqual(d.added.map((p) => p.name), ['new']);
  assert.deepEqual(d.removed.map((p) => p.name), ['gone']);
  assert.deepEqual(d.changed.map((p) => p.name), ['bump']);
});

test('a channel move at the same revision is still a change', () => {
  const a = { packages: [], snaps: [{ name: 'x', channel: 'edge', rev: 5 }] };
  const b = { packages: [], snaps: [{ name: 'x', channel: 'stable', rev: 5 }] };
  assert.equal(diffManifests(a, b).counts.snapChanged, 1);
});

test('results are sorted, so output is deterministic', () => {
  const a = { packages: [['b', '1']], snaps: [] };
  const b = { packages: [['z', '1'], ['a', '1']], snaps: [] };
  assert.deepEqual(diffManifests(a, b).added.map((p) => p.name), ['a', 'z']);
});
