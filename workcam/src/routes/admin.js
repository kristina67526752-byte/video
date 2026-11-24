'use strict';
const express = require('express');
const path = require('path');
const fs = require('fs/promises');
const db = require('../db');
const config = require('../config');
const settings = require('../services/settings');
const payments = require('../services/payments');
const { requireAdmin } = require('../middleware/auth');

const router = express.Router();
router.use(requireAdmin);

const AVATAR_DIR = path.join(config.uploadDir, 'avatars');
const PENDING_DIR = path.join(config.uploadDir, 'pending');
const validName = (n) => typeof n === 'string' && /^[\w-]+\.webp$/.test(n);
const PAGE = 30;

/* ---------- Tableau de bord ---------- */
router.get('/', async (req, res, next) => {
  try {
    const stats = await db.one(`SELECT
      (SELECT count(*) FROM users WHERE role='client')::int AS clients,
      (SELECT count(*) FROM users WHERE role='provider')::int AS providers,
      (SELECT count(*) FROM users WHERE created_at > now() - interval '7 days')::int AS new_users_7d,
      (SELECT count(*) FROM listings WHERE status='active')::int AS active_listings,
      (SELECT count(*) FROM listings WHERE status='pending_payment')::int AS pending_listings,
      (SELECT count(*) FROM client_requests WHERE status='open')::int AS open_requests,
      (SELECT count(*) FROM messages WHERE created_at > now() - interval '7 days')::int AS messages_7d,
      (SELECT COALESCE(sum(amount),0) FROM payments WHERE status='successful')::bigint AS revenue_total,
      (SELECT COALESCE(sum(amount),0) FROM payments WHERE status='successful' AND created_at >= date_trunc('month', now()))::bigint AS revenue_month,
      (SELECT count(*) FROM photo_reviews WHERE status='pending')::int AS photo_reviews,
      (SELECT count(*) FROM reports WHERE status='open')::int AS reports`);
    const s = await settings.getAll();
    res.render('admin/dashboard', { title: 'Admin', stats, s, promoActive: settings.promoIsActive(s) });
  } catch (e) { next(e); }
});

/* ---------- Tarifs & gratuité de lancement ---------- */
router.get('/settings', async (req, res, next) => {
  try {
    const s = await settings.getAll();
    const categories = await db.many('SELECT * FROM categories ORDER BY sort_order');
    res.render('admin/settings', { title: res.locals.t('admin.settings'), s, categories, promoActive: settings.promoIsActive(s) });
  } catch (e) { next(e); }
});

router.post('/settings', async (req, res, next) => {
  try {
    const int = (v, def = null) => {
      const n = parseInt(String(v ?? '').replace(/[^\d]/g, ''), 10);
      return Number.isFinite(n) ? n : def;
    };
    const b = req.body;
    await db.tx(async (c) => {
      await settings.set('listing_fee', Math.min(int(b.listing_fee, 0), 10000000), c);
      await settings.set('listing_duration_days', Math.max(1, Math.min(int(b.listing_duration_days, 30), 365)), c);
      await settings.set('promo_enabled', b.promo_enabled === 'on', c);
      await settings.set('promo_end_date', /^\d{4}-\d{2}-\d{2}$/.test(b.promo_end_date || '') ? b.promo_end_date : null, c);
      await settings.set('promo_quota', int(b.promo_quota), c);
      await settings.set('promo_per_provider', int(b.promo_per_provider), c);
      if (b.reset_promo_used === 'on') await settings.set('promo_used', 0, c);
      // Les catégories ne sont modifiées que si le tableau des catégories faisait partie du formulaire.
      const cats = b.categories_form === '1' ? await c.query('SELECT id FROM categories') : { rows: [] };
      for (const { id } of cats.rows) {
        const raw = b[`fee_${id}`];
        const fee = raw === undefined || String(raw).trim() === '' ? null : int(raw);
        await c.query('UPDATE categories SET listing_fee=$2, is_active=$3 WHERE id=$1', [id, fee, b[`active_${id}`] === 'on']);
      }
    });
    settings.invalidate();
    req.flash('success', 'flash.saved');
    res.redirect('/admin/settings');
  } catch (e) { next(e); }
});

router.post('/categories', async (req, res, next) => {
  try {
    const slug = String(req.body.slug || '').toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 40);
    const fr = String(req.body.name_fr || '').trim().slice(0, 60);
    const en = String(req.body.name_en || '').trim().slice(0, 60);
    const icon = String(req.body.icon || '🛠️').trim().slice(0, 8);
    if (slug && fr && en) {
      await db.query(`INSERT INTO categories (slug, name_fr, name_en, icon, sort_order)
        VALUES ($1,$2,$3,$4,(SELECT COALESCE(max(sort_order),0)+1 FROM categories)) ON CONFLICT (slug) DO NOTHING`, [slug, fr, en, icon]);
      req.flash('success', 'flash.saved');
    }
    res.redirect('/admin/settings');
  } catch (e) { next(e); }
});

/* ---------- Validation manuelle des photos ---------- */
router.get('/photos', async (req, res, next) => {
  try {
    const reviews = await db.many(`SELECT r.*, u.full_name, u.phone, u.role, u.photo_path, u.photo_status
      FROM photo_reviews r JOIN users u ON u.id=r.user_id WHERE r.status='pending' ORDER BY r.created_at`);
    const recent = await db.many(`SELECT r.*, u.full_name FROM photo_reviews r JOIN users u ON u.id=r.user_id
      WHERE r.status<>'pending' ORDER BY r.reviewed_at DESC NULLS LAST LIMIT 20`);
    res.render('admin/photos', { title: res.locals.t('admin.photos'), reviews, recent });
  } catch (e) { next(e); }
});

router.get('/photos/:id/image', async (req, res, next) => {
  try {
    const r = await db.one('SELECT file_name FROM photo_reviews WHERE id=$1', [parseInt(req.params.id, 10) || 0]);
    if (!r || !validName(r.file_name)) return next();
    res.set('Cache-Control', 'private, no-store');
    res.sendFile(path.join(PENDING_DIR, r.file_name), (err) => { if (err) next(); });
  } catch (e) { next(e); }
});

router.post('/photos/:id/:decision', async (req, res, next) => {
  try {
    const decision = req.params.decision;
    if (!['approve', 'reject'].includes(decision)) return next();
    const r = await db.one("SELECT r.*, u.photo_path, u.photo_status FROM photo_reviews r JOIN users u ON u.id=r.user_id WHERE r.id=$1 AND r.status='pending'", [parseInt(req.params.id, 10) || 0]);
    if (!r || !validName(r.file_name)) return res.redirect('/admin/photos');
    const note = String(req.body.admin_note || '').slice(0, 500) || null;
    if (decision === 'approve') {
      await fs.rename(path.join(PENDING_DIR, r.file_name), path.join(AVATAR_DIR, r.file_name));
      await db.query("UPDATE users SET photo_path=$2, photo_status='approved', photo_failures=0 WHERE id=$1", [r.user_id, r.file_name]);
      if (r.photo_path && validName(r.photo_path) && r.photo_path !== r.file_name) await fs.unlink(path.join(AVATAR_DIR, r.photo_path)).catch(() => {});
    } else {
      await fs.unlink(path.join(PENDING_DIR, r.file_name)).catch(() => {});
      if (r.photo_status !== 'approved') await db.query("UPDATE users SET photo_status='rejected' WHERE id=$1", [r.user_id]);
    }
    await db.query('UPDATE photo_reviews SET status=$2, admin_note=$3, reviewed_by=$4, reviewed_at=now() WHERE id=$1',
      [r.id, decision === 'approve' ? 'approved' : 'rejected', note, req.user.id]);
    req.flash('success', 'flash.saved');
    res.redirect('/admin/photos');
  } catch (e) { next(e); }
});

/* ---------- Utilisateurs ---------- */
router.get('/users', async (req, res, next) => {
  try {
    const q = String(req.query.q || '').trim();
    const role = String(req.query.role || '');
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const where = ['TRUE']; const params = [];
    if (q) { params.push(`%${q.replace(/\s/g, '')}%`, `%${q}%`); where.push(`(replace(phone,' ','') ILIKE $${params.length - 1} OR full_name ILIKE $${params.length} OR email ILIKE $${params.length})`); }
    if (['client', 'provider', 'admin'].includes(role)) { params.push(role); where.push(`role=$${params.length}`); }
    const users = await db.many(`SELECT id, role, full_name, phone, email, city, photo_status, photo_path, is_banned, created_at, last_seen_at,
        (SELECT count(*)::int FROM listings l WHERE l.provider_id=users.id) AS listings
      FROM users WHERE ${where.join(' AND ')} ORDER BY created_at DESC LIMIT ${PAGE} OFFSET ${(page - 1) * PAGE}`, params);
    res.render('admin/users', { title: res.locals.t('admin.users'), users, q, role, page });
  } catch (e) { next(e); }
});

router.post('/users/:id/:action', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10) || 0;
    if (id === req.user.id) return res.redirect('/admin/users');
    const u = await db.one('SELECT * FROM users WHERE id=$1', [id]);
    if (!u) return next();
    switch (req.params.action) {
      case 'ban':
        await db.query('UPDATE users SET is_banned=TRUE WHERE id=$1', [id]);
        await db.query("UPDATE listings SET status='suspended' WHERE provider_id=$1 AND status='active'", [id]);
        await db.query("DELETE FROM session WHERE (sess->>'userId') = $1", [String(id)]);
        break;
      case 'unban':
        await db.query('UPDATE users SET is_banned=FALSE WHERE id=$1', [id]);
        break;
      case 'remove-photo':
        if (u.photo_path && validName(u.photo_path)) await fs.unlink(path.join(AVATAR_DIR, u.photo_path)).catch(() => {});
        await db.query("UPDATE users SET photo_path=NULL, photo_status='rejected' WHERE id=$1", [id]);
        break;
      default: return next();
    }
    req.flash('success', 'flash.saved');
    res.redirect(String(req.body.back || '/admin/users').startsWith('/admin') ? req.body.back || '/admin/users' : '/admin/users');
  } catch (e) { next(e); }
});

/* ---------- Annonces & demandes ---------- */
router.get('/listings', async (req, res, next) => {
  try {
    const status = String(req.query.status || '');
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const params = []; let where = 'TRUE';
    if (['draft', 'pending_payment', 'active', 'expired', 'suspended'].includes(status)) { params.push(status); where = 'l.status=$1'; }
    const listings = await db.many(`SELECT l.*, u.full_name, u.phone, c.name_fr, c.name_en FROM listings l
      JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id WHERE ${where}
      ORDER BY l.created_at DESC LIMIT ${PAGE} OFFSET ${(page - 1) * PAGE}`, params);
    const requests = await db.many(`SELECT q.*, u.full_name FROM client_requests q JOIN users u ON u.id=q.client_id
      ORDER BY q.created_at DESC LIMIT 20`);
    res.render('admin/listings', { title: res.locals.t('admin.listings'), listings, requests, status, page });
  } catch (e) { next(e); }
});

router.post('/listings/:id/:action', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10) || 0;
    if (req.params.action === 'suspend') await db.query("UPDATE listings SET status='suspended', updated_at=now() WHERE id=$1", [id]);
    else if (req.params.action === 'restore') {
      await db.query(`UPDATE listings SET status = CASE WHEN expires_at > now() THEN 'active' ELSE 'expired' END, updated_at=now()
        WHERE id=$1 AND status='suspended'`, [id]);
    } else return next();
    req.flash('success', 'flash.saved');
    res.redirect('/admin/listings');
  } catch (e) { next(e); }
});

router.post('/requests/:id/:action', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10) || 0;
    if (req.params.action === 'suspend') await db.query("UPDATE client_requests SET status='suspended' WHERE id=$1", [id]);
    else if (req.params.action === 'restore') await db.query("UPDATE client_requests SET status='open' WHERE id=$1 AND status='suspended'", [id]);
    else return next();
    req.flash('success', 'flash.saved');
    res.redirect('/admin/listings');
  } catch (e) { next(e); }
});

/* ---------- Paiements ---------- */
router.get('/payments', async (req, res, next) => {
  try {
    const status = String(req.query.status || '');
    const params = []; let where = 'TRUE';
    if (['pending', 'successful', 'failed'].includes(status)) { params.push(status); where = 'p.status=$1'; }
    const list = await db.many(`SELECT p.*, u.full_name, l.title FROM payments p JOIN users u ON u.id=p.user_id
      LEFT JOIN listings l ON l.id=p.listing_id WHERE ${where} ORDER BY p.created_at DESC LIMIT 100`, params);
    res.render('admin/payments', { title: res.locals.t('admin.payments'), list, status });
  } catch (e) { next(e); }
});

router.post('/payments/:id/recheck', async (req, res, next) => {
  try {
    const p = await db.one('SELECT * FROM payments WHERE id=$1', [parseInt(req.params.id, 10) || 0]);
    if (p) await payments.refresh(p);
    res.redirect('/admin/payments');
  } catch (e) { next(e); }
});

/* ---------- Signalements ---------- */
router.get('/reports', async (req, res, next) => {
  try {
    const reports = await db.many(`SELECT r.*, u.full_name AS reporter FROM reports r LEFT JOIN users u ON u.id=r.reporter_id
      ORDER BY (r.status='open') DESC, r.created_at DESC LIMIT 100`);
    res.render('admin/reports', { title: res.locals.t('admin.reports'), reports });
  } catch (e) { next(e); }
});

router.post('/reports/:id/close', async (req, res, next) => {
  try {
    await db.query("UPDATE reports SET status='closed' WHERE id=$1", [parseInt(req.params.id, 10) || 0]);
    res.redirect('/admin/reports');
  } catch (e) { next(e); }
});

module.exports = router;
