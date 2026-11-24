'use strict';
const express = require('express');
const path = require('path');
const fs = require('fs/promises');
const crypto = require('crypto');
const multer = require('multer');
const sharp = require('sharp');
const bcrypt = require('bcryptjs');
const rateLimit = require('express-rate-limit');
const db = require('../db');
const config = require('../config');
const { requireAuth } = require('../middleware/auth');
const { verifyCsrf } = require('../middleware/csrf');
const { checkProfilePhoto } = require('../services/faceDetection');

const router = express.Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 8 * 1024 * 1024, files: 1 },
  fileFilter: (req, file, cb) => cb(null, ['image/jpeg', 'image/png', 'image/webp'].includes(file.mimetype)),
});
const photoLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, limit: 15, standardHeaders: 'draft-7', legacyHeaders: false,
  handler: (req, res, next) => { const e = new Error('rate'); e.status = 429; next(e); },
});

const AVATAR_DIR = path.join(config.uploadDir, 'avatars');
const PENDING_DIR = path.join(config.uploadDir, 'pending');

/** Recadre en carré 480 px centré sur la zone d'intérêt, ré-encode en WebP (supprime les métadonnées EXIF/GPS). */
async function processAvatar(buffer) {
  return sharp(buffer).rotate().resize(480, 480, { fit: 'cover', position: sharp.strategy.attention }).webp({ quality: 82 }).toBuffer();
}

async function safeUnlink(dir, name) {
  if (!name || name.includes('/') || name.includes('..')) return;
  await fs.unlink(path.join(dir, name)).catch(() => {});
}

/* ---------- Tableau de bord ---------- */
router.get('/account', requireAuth, async (req, res, next) => {
  try {
    const u = req.user;
    const data = { title: res.locals.t('account.title') };
    if (u.role === 'provider' || u.role === 'admin') {
      data.listings = await db.many(`SELECT l.*, c.name_fr, c.name_en, c.icon,
          (SELECT count(*)::int FROM conversations cv WHERE cv.listing_id=l.id) AS contacts
        FROM listings l JOIN categories c ON c.id=l.category_id WHERE provider_id=$1 ORDER BY l.created_at DESC`, [u.id]);
      data.payments = await db.many('SELECT * FROM payments WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10', [u.id]);
      data.responses = await db.many(`SELECT r.*, q.title, q.city, q.status AS request_status FROM request_responses r
        JOIN client_requests q ON q.id=r.request_id WHERE r.provider_id=$1 ORDER BY r.created_at DESC LIMIT 10`, [u.id]);
    }
    if (u.role === 'client' || u.role === 'admin') {
      data.requests = await db.many(`SELECT q.*, c.name_fr, c.name_en, c.icon,
          (SELECT count(*)::int FROM request_responses r WHERE r.request_id=q.id) AS responses
        FROM client_requests q JOIN categories c ON c.id=q.category_id WHERE client_id=$1 ORDER BY q.created_at DESC`, [u.id]);
    }
    data.pendingReview = await db.one("SELECT * FROM photo_reviews WHERE user_id=$1 AND status='pending' ORDER BY id DESC LIMIT 1", [u.id]);
    res.render('account/dashboard', data);
  } catch (e) { next(e); }
});

/* ---------- Profil ---------- */
router.get('/account/edit', requireAuth, (req, res) => {
  res.render('account/edit', { title: res.locals.t('account.edit'), form: req.user, errors: {} });
});

router.post('/account/edit', requireAuth, async (req, res, next) => {
  try {
    const t = res.locals.t;
    const clip = (v, n) => String(v || '').trim().slice(0, n);
    const form = {
      ...req.user,
      full_name: clip(req.body.full_name, 80),
      email: clip(req.body.email, 200).toLowerCase(),
      city: String(req.body.city || ''),
      headline: clip(req.body.headline, 100),
      bio: clip(req.body.bio, 2000),
      experience: clip(req.body.experience, 2000),
      availability: clip(req.body.availability, 300),
      price_note: clip(req.body.price_note, 300),
      lang: req.body.lang === 'en' ? 'en' : 'fr',
    };
    const errors = {};
    if (form.full_name.length < 3) errors.full_name = t('err.name');
    if (!config.cities.includes(form.city)) errors.city = t('err.city');
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(form.email)) errors.email = t('err.email');
    if (form.email && !errors.email && await db.one('SELECT 1 FROM users WHERE email=$1 AND id<>$2', [form.email, req.user.id])) errors.email = t('err.email_taken');
    if (Object.keys(errors).length) return res.status(422).render('account/edit', { title: t('account.edit'), form, errors });
    await db.query(
      `UPDATE users SET full_name=$2, email=$3, city=$4, headline=$5, bio=$6, experience=$7, availability=$8, price_note=$9, lang=$10 WHERE id=$1`,
      [req.user.id, form.full_name, form.email || null, form.city, form.headline || null, form.bio || null,
        form.experience || null, form.availability || null, form.price_note || null, form.lang]
    );
    res.cookie('lang', form.lang, { maxAge: 365 * 24 * 3600 * 1000, sameSite: 'lax', secure: config.isProd });
    req.flash('success', 'flash.saved');
    res.redirect('/account');
  } catch (e) { next(e); }
});

router.post('/account/password', requireAuth, async (req, res, next) => {
  try {
    const ok = await bcrypt.compare(String(req.body.current || ''), req.user.password_hash);
    const np = String(req.body.password || '');
    if (!ok) { req.flash('error', 'err.current_password'); return res.redirect('/account/edit'); }
    if (np.length < 8) { req.flash('error', 'err.password'); return res.redirect('/account/edit'); }
    await db.query('UPDATE users SET password_hash=$2 WHERE id=$1', [req.user.id, await bcrypt.hash(np, 12)]);
    req.flash('success', 'flash.saved');
    res.redirect('/account');
  } catch (e) { next(e); }
});

/* ---------- Photo de profil avec détection de visage ---------- */
async function renderPhoto(req, res, extra = {}) {
  const pending = await db.one("SELECT * FROM photo_reviews WHERE user_id=$1 AND status='pending' ORDER BY id DESC LIMIT 1", [req.user.id]);
  const lastRejected = req.session.lastRejected || null;
  const fresh = await db.one('SELECT photo_failures FROM users WHERE id=$1', [req.user.id]);
  const canRequestReview = !!lastRejected && !pending &&
    (fresh.photo_failures >= config.photoMaxFailuresBeforeManual || lastRejected.reason === 'provider_error');
  res.status(extra.status || 200).render('account/photo', {
    title: res.locals.t('photo.title'), pending, lastRejected, canRequestReview, result: extra.result || null,
  });
}

router.get('/account/photo', requireAuth, (req, res, next) => renderPhoto(req, res).catch(next));

router.post('/account/photo', requireAuth, photoLimiter, upload.single('photo'), verifyCsrf, async (req, res, next) => {
  try {
    if (!req.file) {
      return renderPhoto(req, res, { status: 422, result: { ok: false, reason: 'invalid_image' } });
    }
    const check = await checkProfilePhoto(req.file.buffer);
    const processed = await processAvatar(req.file.buffer).catch(() => null);
    if (!processed) return renderPhoto(req, res, { status: 422, result: { ok: false, reason: 'invalid_image' } });

    if (check.ok) {
      const name = `${crypto.randomUUID()}.webp`;
      await fs.writeFile(path.join(AVATAR_DIR, name), processed);
      const old = req.user.photo_path;
      await db.query("UPDATE users SET photo_path=$2, photo_status='approved', photo_failures=0 WHERE id=$1", [req.user.id, name]);
      // Une demande manuelle en attente devient inutile.
      const stale = await db.many("UPDATE photo_reviews SET status='rejected', admin_note='auto: remplacée', reviewed_at=now() WHERE user_id=$1 AND status='pending' RETURNING file_name", [req.user.id]);
      for (const r of stale) await safeUnlink(PENDING_DIR, r.file_name);
      if (old && old !== name) await safeUnlink(AVATAR_DIR, old);
      if (req.session.lastRejected) await safeUnlink(PENDING_DIR, req.session.lastRejected.file);
      req.session.lastRejected = null;
      req.flash('success', 'flash.photo_ok');
      return res.redirect(req.user.role === 'provider' ? '/account' : '/account');
    }

    // Rejet automatique : on conserve l'image (privée) au cas où l'utilisateur demande une validation manuelle.
    if (req.session.lastRejected) await safeUnlink(PENDING_DIR, req.session.lastRejected.file);
    const name = `${crypto.randomUUID()}.webp`;
    await fs.writeFile(path.join(PENDING_DIR, name), processed);
    req.session.lastRejected = { file: name, reason: check.reason };
    await db.query('UPDATE users SET photo_failures = photo_failures + 1 WHERE id=$1', [req.user.id]);
    return renderPhoto(req, res, { status: 422, result: check });
  } catch (e) { next(e); }
});

router.post('/account/photo/review', requireAuth, async (req, res, next) => {
  try {
    const lr = req.session.lastRejected;
    const fresh = await db.one('SELECT photo_failures, photo_status FROM users WHERE id=$1', [req.user.id]);
    const existing = await db.one("SELECT 1 FROM photo_reviews WHERE user_id=$1 AND status='pending'", [req.user.id]);
    if (!lr || existing || (fresh.photo_failures < config.photoMaxFailuresBeforeManual && lr.reason !== 'provider_error')) {
      return res.redirect('/account/photo');
    }
    await db.query('INSERT INTO photo_reviews (user_id, file_name, auto_reason, user_note) VALUES ($1,$2,$3,$4)',
      [req.user.id, lr.file, lr.reason, String(req.body.note || '').slice(0, 500) || null]);
    if (fresh.photo_status !== 'approved') await db.query("UPDATE users SET photo_status='pending_review' WHERE id=$1", [req.user.id]);
    req.session.lastRejected = null;
    req.flash('info', 'flash.review_sent');
    res.redirect('/account');
  } catch (e) { next(e); }
});

module.exports = router;
