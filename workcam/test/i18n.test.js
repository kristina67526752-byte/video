'use strict';
// Vérifie que toutes les clés de traduction utilisées existent en FR et EN.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const dict = require('../src/i18n/messages');

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => (d.isDirectory() ? walk(path.join(dir, d.name)) : [path.join(dir, d.name)]));
}

test('toutes les clés i18n utilisées sont définies dans les deux langues', () => {
  const files = walk(path.join(__dirname, '..', 'src')).filter((f) => /\.(ejs|js)$/.test(f) && !f.includes('i18n'));
  const used = new Set();
  for (const f of files) {
    const src = fs.readFileSync(f, 'utf8');
    for (const m of src.matchAll(/\bt\('([a-z0-9_]+\.[a-z0-9_.]+)'/g)) used.add(m[1]);
    for (const m of src.matchAll(/flash\('[a-z]+', '([a-z0-9_.]+)'/g)) used.add(m[1]);
  }
  const dynamic = {
    'role.': ['client', 'provider', 'admin'],
    'status.': ['draft', 'pending_payment', 'active', 'expired', 'suspended', 'open', 'closed'],
    'pstatus.': ['pending', 'successful', 'failed'],
    'photostatus.': ['none', 'approved', 'pending_review', 'rejected'],
    'unit.': ['job', 'hour', 'day', 'month'],
    'photo.reason.': ['no_face', 'multiple_faces', 'face_too_small', 'blurry', 'too_dark', 'invalid_image', 'provider_error'],
  };
  for (const [p, vals] of Object.entries(dynamic)) vals.forEach((v) => used.add(p + v));
  ['flash.listing_free_promo', 'flash.response_sent', 'flash.already_responded'].forEach((k) => used.add(k));
  const missing = [...used].filter((k) => !k.endsWith('.') && (!dict[k] || !dict[k][0] || !dict[k][1]));
  assert.deepStrictEqual(missing, []);
});
