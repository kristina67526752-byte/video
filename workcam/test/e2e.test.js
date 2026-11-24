'use strict';
/**
 * Test de bout en bout sur une base dédiée.
 *   TEST_DATABASE_URL=postgres://postgres:postgres@localhost:5432/workcam_test npm test
 * Optionnel : FACE_FIXTURE=/chemin/portrait.jpg pour tester une photo acceptée automatiquement.
 * ATTENTION : la base de test est vidée à chaque exécution.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const TEST_DB = process.env.TEST_DATABASE_URL;
if (TEST_DB) {
  process.env.DATABASE_URL = TEST_DB;
  process.env.PAYMENT_GATEWAY = 'simulation';
  process.env.NODE_ENV = 'test';
  process.env.UPLOAD_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'workcam-up-'));
  process.env.PHOTO_MAX_FAILURES = '2';
}

class Client {
  constructor(base) { this.base = base; this.cookie = ''; }
  async req(method, url, { form, multipart, json, follow = false } = {}) {
    const headers = { Cookie: this.cookie };
    let body;
    if (form) { headers['Content-Type'] = 'application/x-www-form-urlencoded'; body = new URLSearchParams(form).toString(); }
    if (multipart) body = multipart;
    if (json) headers.Accept = 'application/json';
    const res = await fetch(this.base + url, { method, headers, body, redirect: 'manual' });
    const sc = res.headers.getSetCookie();
    for (const c of sc) if (c.startsWith('wc.sid=')) this.cookie = c.split(';')[0];
    const text = await res.text();
    const out = { status: res.status, location: res.headers.get('location'), text };
    if (follow && out.location) return this.get(out.location);
    return out;
  }
  get(url, opts) { return this.req('GET', url, opts); }
  async csrf(url = '/') {
    const r = await this.get(url);
    const m = r.text.match(/name="_csrf" value="([a-f0-9]+)"/);
    assert.ok(m, `jeton CSRF absent sur ${url}`);
    return m[1];
  }
  async post(url, form, from) { const _csrf = await this.csrf(from || url); return this.req('POST', url, { form: { ...form, _csrf } }); }
  async upload(url, buffer, type, from) {
    const _csrf = await this.csrf(from || url);
    const fd = new FormData();
    fd.append('_csrf', _csrf);
    fd.append('photo', new Blob([buffer], { type }), 'photo.' + type.split('/')[1]);
    return this.req('POST', url, { multipart: fd });
  }
}

test('parcours complet Work.cam', { skip: !TEST_DB && 'TEST_DATABASE_URL non défini' }, async (t) => {
  const sharp = require('sharp');
  const db = require('../src/db');
  const { migrate } = require('../scripts/migrate');
  await migrate();
  await db.query(`TRUNCATE users, listings, client_requests, request_responses, conversations, messages, payments,
    photo_reviews, reports, otp_codes, session RESTART IDENTITY CASCADE`);
  await db.query("UPDATE settings SET value='0' WHERE key='promo_used'");
  await db.query('UPDATE categories SET is_active=TRUE, listing_fee=NULL');
  await db.query("UPDATE settings SET value='1000' WHERE key='listing_fee'");
  await db.query("UPDATE settings SET value='30' WHERE key='listing_duration_days'");
  await db.query("UPDATE settings SET value='null' WHERE key='promo_quota'");
  await db.query("UPDATE settings SET value='true' WHERE key='promo_enabled'");
  await db.query("UPDATE settings SET value='null' WHERE key='promo_end_date'");
  await db.query("UPDATE settings SET value='1' WHERE key='promo_per_provider'");
  require('../src/services/settings').invalidate();

  const { createApp } = require('../src/app');
  const server = createApp().listen(0);
  const base = `http://127.0.0.1:${server.address().port}`;
  t.after(async () => { server.close(); await db.pool.end(); });

  const admin = new Client(base);
  const pro = new Client(base);
  const cli = new Client(base);

  // Admin créé par le script dédié (simulé ici)
  const bcrypt = require('bcryptjs');
  await db.query("INSERT INTO users (role, full_name, phone, password_hash, photo_status, phone_verified) VALUES ('admin','Admin','+237699000000',$1,'approved',TRUE)", [await bcrypt.hash('admin-password-123', 4)]);

  await t.test('inscription et validations', async () => {
    let r = await pro.post('/register', { role: 'provider', full_name: 'Jean Mbarga', phone: '12345', city: 'Douala', password: 'short', password2: 'x' }, '/register');
    assert.strictEqual(r.status, 422);
    assert.match(r.text, /Numéro camerounais invalide/);
    r = await pro.post('/register', { role: 'provider', full_name: 'Jean Mbarga', phone: '677 12 34 56', city: 'Douala', password: 'motdepasse1', password2: 'motdepasse1', accept: 'on' }, '/register');
    assert.strictEqual(r.status, 302);
    assert.strictEqual(r.location, '/account/photo');
    r = await cli.post('/register', { role: 'client', full_name: 'Awa Ngono', phone: '+237 691 23 45 67', city: 'Douala', password: 'motdepasse2', password2: 'motdepasse2', accept: 'on' }, '/register');
    assert.strictEqual(r.status, 302);
    const dup = new Client(base);
    r = await dup.post('/register', { role: 'client', full_name: 'Autre', phone: '677123456', city: 'Douala', password: 'motdepasse3', password2: 'motdepasse3', accept: 'on' }, '/register');
    assert.strictEqual(r.status, 422);
    assert.match(r.text, /déjà inscrit/);
  });

  await t.test('connexion admin et mauvais mot de passe', async () => {
    let r = await admin.post('/login', { phone: '699000000', password: 'faux' }, '/login');
    assert.strictEqual(r.status, 401);
    r = await admin.post('/login', { phone: '699000000', password: 'admin-password-123' }, '/login');
    assert.strictEqual(r.status, 302);
    assert.strictEqual(r.location, '/admin');
    r = await admin.get('/admin');
    assert.strictEqual(r.status, 200);
    r = await cli.get('/admin');
    assert.strictEqual(r.status, 403);
  });

  await t.test('publication bloquée sans photo validée', async () => {
    const r = await pro.get('/listings/new');
    assert.strictEqual(r.status, 302);
    assert.strictEqual(r.location, '/account/photo');
  });

  await t.test('photo sans visage refusée puis validation manuelle', async () => {
    const landscape = await sharp({ create: { width: 640, height: 480, channels: 3, background: '#4a7a3a' } })
      .composite([{ input: Buffer.from('<svg width="640" height="480"><rect x="0" y="0" width="640" height="200" fill="#8cc0ec"/><circle cx="500" cy="90" r="50" fill="#ffd34d"/><path d="M0 300 L200 180 L400 320 L640 200 L640 480 L0 480Z" fill="#2f5d2a"/></svg>') }])
      .jpeg().toBuffer();
    let r = await pro.upload('/account/photo', landscape, 'image/jpeg');
    assert.strictEqual(r.status, 422);
    assert.match(r.text, /Photo refusée/);
    assert.doesNotMatch(r.text, /photo\/review/);
    r = await pro.upload('/account/photo', landscape, 'image/jpeg');
    assert.strictEqual(r.status, 422);
    assert.match(r.text, /action="\/account\/photo\/review"/, 'la validation manuelle doit être proposée après 2 échecs');
    r = await pro.post('/account/photo/review', { note: 'C’est bien moi' }, '/account/photo');
    assert.strictEqual(r.status, 302);
    const u = await db.one("SELECT photo_status FROM users WHERE phone='+237677123456'");
    assert.strictEqual(u.photo_status, 'pending_review');

    // L'image en attente n'est pas publique, seulement visible par l'admin
    const rev = await db.one("SELECT id FROM photo_reviews WHERE status='pending'");
    r = await cli.get(`/admin/photos/${rev.id}/image`);
    assert.strictEqual(r.status, 403);
    r = await admin.get(`/admin/photos/${rev.id}/image`);
    assert.strictEqual(r.status, 200);
    r = await admin.post(`/admin/photos/${rev.id}/approve`, {}, '/admin/photos');
    assert.strictEqual(r.status, 302);
    const u2 = await db.one("SELECT photo_status, photo_path FROM users WHERE phone='+237677123456'");
    assert.strictEqual(u2.photo_status, 'approved');
    r = await cli.get(`/uploads/avatars/${u2.photo_path}`);
    assert.strictEqual(r.status, 200);
  });

  if (process.env.FACE_FIXTURE) {
    await t.test('portrait accepté automatiquement', async () => {
      const r = await cli.upload('/account/photo', fs.readFileSync(process.env.FACE_FIXTURE), 'image/jpeg');
      assert.strictEqual(r.status, 302);
      const u = await db.one("SELECT photo_status FROM users WHERE phone='+237691234567'");
      assert.strictEqual(u.photo_status, 'approved');
    });
  } else {
    await db.query("UPDATE users SET photo_status='approved' WHERE phone='+237691234567'");
  }

  let listingId;
  await t.test('1re annonce gratuite (offre de lancement)', async () => {
    const r = await pro.post('/listings', { title: 'Dépannage électrique à domicile', description: 'Installation, dépannage et mise aux normes de vos installations électriques, partout à Douala.', category_id: '2', city: 'Douala', district: 'Akwa', price_min: '5000', price_max: '20000', price_unit: 'job' }, '/listings/new');
    assert.strictEqual(r.status, 302);
    listingId = parseInt(r.location.split('/').pop(), 10);
    const l = await db.one('SELECT status, is_free_promo FROM listings WHERE id=$1', [listingId]);
    assert.deepStrictEqual(l, { status: 'active', is_free_promo: true });
    const s = await cli.get('/services?q=électrique&city=Douala');
    assert.match(s.text, /Dépannage électrique/);
  });

  let payId;
  await t.test('2e annonce payante (quota par prestataire atteint) → Mobile Money', async () => {
    let r = await pro.post('/listings', { title: 'Installation de climatiseurs split', description: 'Pose et entretien de climatiseurs split et réfrigérateurs, devis gratuit sur Douala.', category_id: '11', city: 'Douala', price_unit: 'job' }, '/listings/new');
    assert.strictEqual(r.status, 302);
    assert.match(r.location, /\/listings\/\d+\/pay$/);
    const id = parseInt(r.location.split('/')[2], 10);
    const pay = await pro.get(r.location);
    assert.match(pay.text, /1 000 FCFA/);
    // Numéro Orange mais opérateur MTN choisi → refus
    r = await pro.post(`/listings/${id}/pay`, { operator: 'mtn', phone: '699112233' }, `/listings/${id}/pay`);
    assert.strictEqual(r.status, 422);
    r = await pro.post(`/listings/${id}/pay`, { operator: 'mtn', phone: '677123456' }, `/listings/${id}/pay`);
    assert.strictEqual(r.status, 302);
    payId = parseInt(r.location.split('/').pop(), 10);
    let st = JSON.parse((await pro.get(`/api/payments/${payId}/status`, { json: true })).text);
    assert.strictEqual(st.status, 'pending');
    // un autre utilisateur ne voit pas ce paiement
    assert.strictEqual((await cli.get(`/api/payments/${payId}/status`, { json: true })).status, 404);
    await new Promise((res) => setTimeout(res, 6500));
    st = JSON.parse((await pro.get(`/api/payments/${payId}/status`, { json: true })).text);
    assert.strictEqual(st.status, 'successful');
    const l = await db.one('SELECT status, expires_at FROM listings WHERE id=$1', [id]);
    assert.strictEqual(l.status, 'active');
    assert.ok(new Date(l.expires_at) > new Date(Date.now() + 29 * 86400000));
  });

  await t.test('paiement idempotent : un webhook rejoué ne prolonge pas deux fois', async () => {
    const before = await db.one('SELECT l.expires_at FROM payments p JOIN listings l ON l.id=p.listing_id WHERE p.id=$1', [payId]);
    const payments = require('../src/services/payments');
    await payments.finalize(payId, 'successful');
    const after = await db.one('SELECT l.expires_at FROM payments p JOIN listings l ON l.id=p.listing_id WHERE p.id=$1', [payId]);
    assert.strictEqual(before.expires_at.getTime(), after.expires_at.getTime());
  });

  await t.test('admin : tarifs et fin de gratuité', async () => {
    const r = await admin.post('/admin/settings', { listing_fee: '2500', listing_duration_days: '45', promo_quota: '', promo_per_provider: '' }, '/admin/settings');
    assert.strictEqual(r.status, 302);
    const s = await db.many("SELECT key, value FROM settings WHERE key IN ('listing_fee','promo_enabled','listing_duration_days')");
    const m = Object.fromEntries(s.map((x) => [x.key, x.value]));
    assert.deepStrictEqual(m, { listing_fee: 2500, promo_enabled: false, listing_duration_days: 45 });
    const active = await db.one('SELECT count(*)::int AS n FROM categories WHERE is_active');
    assert.ok(active.n > 0, 'les catégories ne doivent pas être désactivées par un formulaire partiel');
  });

  await t.test('demande client, réponse prestataire, messagerie', async () => {
    let r = await cli.post('/requests', { title: 'Fuite sous mon évier', description: 'Fuite importante sous l’évier de la cuisine, à réparer cette semaine.', category_id: '1', city: 'Douala', budget: '10000' }, '/requests/new');
    assert.strictEqual(r.status, 302);
    const reqId = parseInt(r.location.split('/').pop(), 10);
    r = await pro.post(`/requests/${reqId}/respond`, { message: 'Bonjour, je peux passer demain matin.', price: '8000' }, `/requests/${reqId}`);
    assert.strictEqual(r.status, 302);
    const convId = parseInt(r.location.split('/').pop(), 10);
    r = await cli.get('/messages');
    assert.match(r.text, /Jean Mbarga/);
    assert.match(r.text, /badge/);
    r = await cli.get(`/messages/${convId}`);
    assert.match(r.text, /je peux passer demain matin/);
    r = await cli.post(`/messages/${convId}`, { body: 'Parfait, à demain <script>alert(1)</script>' }, `/messages/${convId}`);
    assert.strictEqual(r.status, 302);
    r = await pro.get(`/messages/${convId}`);
    assert.match(r.text, /&lt;script&gt;/, 'le contenu doit être échappé');
    const poll = JSON.parse((await pro.get(`/api/messages/${convId}?after=0`, { json: true })).text);
    assert.strictEqual(poll.messages.length, 2);
    // un tiers n'a pas accès à la conversation
    const other = new Client(base);
    await other.post('/register', { role: 'client', full_name: 'Paul Tiers', phone: '650000001', city: 'Yaoundé', password: 'motdepasse4', password2: 'motdepasse4', accept: 'on' }, '/register');
    assert.strictEqual((await other.get(`/messages/${convId}`)).status, 404);
  });

  await t.test('contact depuis une annonce', async () => {
    const r = await cli.post(`/listings/${listingId}/contact`, {}, `/listings/${listingId}`);
    assert.strictEqual(r.status, 302);
    assert.match(r.location, /^\/messages\/\d+/);
  });

  await t.test('CSRF obligatoire', async () => {
    const r = await cli.req('POST', '/requests', { form: { title: 'x' } });
    assert.strictEqual(r.status, 403);
  });

  await t.test('signalement et suspension par l’admin', async () => {
    let r = await cli.post('/report', { target_type: 'listing', target_id: String(listingId), reason: 'Annonce suspecte', back: `/listings/${listingId}` }, `/listings/${listingId}`);
    assert.strictEqual(r.status, 302);
    r = await admin.post(`/admin/listings/${listingId}/suspend`, {}, '/admin/listings');
    assert.strictEqual(r.status, 302);
    r = await cli.get(`/listings/${listingId}`);
    assert.strictEqual(r.status, 404);
  });

  await t.test('version anglaise', async () => {
    await cli.get('/lang/en');
    const r = await cli.get('/');
    assert.match(r.text, /Find a pro/);
  });
});
