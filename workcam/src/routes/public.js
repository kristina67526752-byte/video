'use strict';
const express = require('express');
const db = require('../db');
const config = require('../config');
const settings = require('../services/settings');

const router = express.Router();
const PAGE = 12;

const LISTING_COLS = `l.*, u.full_name, u.photo_path, u.headline, c.slug AS category_slug, c.name_fr, c.name_en, c.icon`;

router.get('/', async (req, res, next) => {
  try {
    const categories = await db.many(`SELECT c.*, (SELECT count(*)::int FROM listings l WHERE l.category_id=c.id AND l.status='active') AS n
      FROM categories c WHERE is_active ORDER BY sort_order`);
    const latest = await db.many(`SELECT ${LISTING_COLS}
      FROM listings l JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id
      WHERE l.status='active' AND NOT u.is_banned ORDER BY l.published_at DESC LIMIT 8`);
    const stats = await db.one(`SELECT (SELECT count(*) FROM users WHERE role='provider' AND photo_status='approved')::int AS providers,
      (SELECT count(*) FROM listings WHERE status='active')::int AS listings,
      (SELECT count(*) FROM client_requests WHERE status='open')::int AS requests`);
    const s = await settings.getAll();
    res.render('pages/home', { title: null, categories, latest, stats, promo: settings.promoIsActive(s) });
  } catch (e) { next(e); }
});

router.get('/services', async (req, res, next) => {
  try {
    const q = String(req.query.q || '');
    const city = String(req.query.city || '');
    const category = String(req.query.category || '');
    const sort = String(req.query.sort || 'recent');
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const where = ["l.status='active'", 'NOT u.is_banned'];
    const params = [];
    if (q.trim()) {
      params.push(`%${q.trim().slice(0, 80)}%`);
      const i = params.length;
      where.push(`(l.title ILIKE $${i} OR l.description ILIKE $${i} OR u.headline ILIKE $${i})`);
    }
    if (city && config.cities.includes(city)) { params.push(city); where.push(`l.city = $${params.length}`); }
    if (category) { params.push(category); where.push(`c.slug = $${params.length}`); }
    const orders = { price_asc: 'l.price_min ASC NULLS LAST', price_desc: 'l.price_min DESC NULLS LAST', recent: 'l.published_at DESC' };
    const order = orders[sort] || orders.recent;
    const base = `FROM listings l JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id WHERE ${where.join(' AND ')}`;
    const total = (await db.one(`SELECT count(*)::int AS n ${base}`, params)).n;
    const listings = await db.many(`SELECT ${LISTING_COLS} ${base} ORDER BY ${order} LIMIT ${PAGE} OFFSET ${(page - 1) * PAGE}`, params);
    const categories = await db.many('SELECT * FROM categories WHERE is_active ORDER BY sort_order');
    res.render('listings/search', {
      title: res.locals.t('nav.services'), listings, categories, total, page, pages: Math.ceil(total / PAGE),
      filters: { q, city, category, sort },
    });
  } catch (e) { next(e); }
});

router.get('/providers/:id', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (!id) return next();
    const p = await db.one("SELECT * FROM users WHERE id=$1 AND role='provider' AND NOT is_banned", [id]);
    if (!p) return next();
    const listings = await db.many(`SELECT ${LISTING_COLS}
      FROM listings l JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id
      WHERE l.provider_id=$1 AND l.status='active' ORDER BY l.published_at DESC`, [p.id]);
    res.render('pages/provider', { title: p.full_name, p, listings });
  } catch (e) { next(e); }
});

router.get('/lang/:lang', async (req, res) => {
  const lang = req.params.lang === 'en' ? 'en' : 'fr';
  res.cookie('lang', lang, { maxAge: 365 * 24 * 3600 * 1000, sameSite: 'lax', secure: config.isProd });
  if (req.user) await db.query('UPDATE users SET lang=$2 WHERE id=$1', [req.user.id, lang]).catch(() => {});
  let target = '/';
  const back = req.get('referer');
  try {
    if (back) { const u = new URL(back); if (u.host === req.get('host')) target = u.pathname + u.search; }
  } catch (e) { /* ignore */ }
  res.redirect(target);
});

router.get('/how-it-works', (req, res) => res.render('pages/how', { title: res.locals.t('nav.how') }));
router.get('/terms', (req, res) => res.render('pages/terms', { title: res.locals.t('footer.terms') }));
router.get('/privacy', (req, res) => res.render('pages/privacy', { title: res.locals.t('footer.privacy') }));
router.get('/healthz', async (req, res) => {
  try { await db.query('SELECT 1'); res.json({ ok: true }); } catch (e) { res.status(503).json({ ok: false }); }
});

module.exports = router;
