'use strict';
const express = require('express');
const db = require('../db');
const config = require('../config');
const { requireAuth, requireRole, requireApprovedPhoto } = require('../middleware/auth');
const { openConversation, postMessage } = require('../services/conversations');

const router = express.Router();
const PAGE = 15;

router.get('/requests', async (req, res, next) => {
  try {
    const city = String(req.query.city || '');
    const category = String(req.query.category || '');
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const where = ["q.status='open'", 'NOT u.is_banned'];
    const params = [];
    if (city && config.cities.includes(city)) { params.push(city); where.push(`q.city=$${params.length}`); }
    if (category) { params.push(category); where.push(`c.slug=$${params.length}`); }
    const base = `FROM client_requests q JOIN users u ON u.id=q.client_id JOIN categories c ON c.id=q.category_id WHERE ${where.join(' AND ')}`;
    const total = (await db.one(`SELECT count(*)::int AS n ${base}`, params)).n;
    const requests = await db.many(`SELECT q.*, split_part(u.full_name, ' ', 1) AS first_name, u.photo_path, c.name_fr, c.name_en, c.icon,
        (SELECT count(*)::int FROM request_responses r WHERE r.request_id=q.id) AS responses
      ${base} ORDER BY q.created_at DESC LIMIT ${PAGE} OFFSET ${(page - 1) * PAGE}`, params);
    const categories = await db.many('SELECT * FROM categories WHERE is_active ORDER BY sort_order');
    res.render('requests/list', { title: res.locals.t('nav.requests'), requests, categories, total, page, pages: Math.ceil(total / PAGE), filters: { city, category } });
  } catch (e) { next(e); }
});

router.get('/requests/new', requireRole('client'), requireApprovedPhoto, async (req, res, next) => {
  try {
    const categories = await db.many('SELECT * FROM categories WHERE is_active ORDER BY sort_order');
    res.render('requests/form', { title: res.locals.t('request.new'), categories, form: { city: req.user.city, category_id: parseInt(req.query.category, 10) || null }, errors: {} });
  } catch (e) { next(e); }
});

router.post('/requests', requireRole('client'), requireApprovedPhoto, async (req, res, next) => {
  try {
    const t = res.locals.t;
    const form = {
      title: String(req.body.title || '').trim().slice(0, 100),
      description: String(req.body.description || '').trim().slice(0, 3000),
      category_id: parseInt(req.body.category_id, 10) || null,
      city: String(req.body.city || ''),
      district: String(req.body.district || '').trim().slice(0, 80),
      budget: parseInt(String(req.body.budget || '').replace(/[^\d]/g, ''), 10) || null,
    };
    const errors = {};
    if (form.title.length < 8) errors.title = t('err.title');
    if (form.description.length < 20) errors.description = t('err.description_short');
    if (!form.category_id || !(await db.one('SELECT 1 FROM categories WHERE id=$1', [form.category_id]))) errors.category_id = t('err.category');
    if (!config.cities.includes(form.city)) errors.city = t('err.city');
    const recent = await db.one("SELECT count(*)::int AS n FROM client_requests WHERE client_id=$1 AND created_at > now() - interval '1 day'", [req.user.id]);
    if (recent.n >= 10) errors.title = t('err.too_many');
    if (Object.keys(errors).length) {
      const categories = await db.many('SELECT * FROM categories WHERE is_active ORDER BY sort_order');
      return res.status(422).render('requests/form', { title: t('request.new'), categories, form, errors });
    }
    const r = await db.one(
      'INSERT INTO client_requests (client_id, category_id, title, description, city, district, budget) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id',
      [req.user.id, form.category_id, form.title, form.description, form.city, form.district || null, form.budget]
    );
    req.flash('success', 'flash.request_posted');
    res.redirect(`/requests/${r.id}`);
  } catch (e) { next(e); }
});

router.get('/requests/:id', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (!id) return next();
    const q = await db.one(`SELECT q.*, split_part(u.full_name, ' ', 1) AS first_name, u.photo_path, c.name_fr, c.name_en, c.icon
      FROM client_requests q JOIN users u ON u.id=q.client_id JOIN categories c ON c.id=q.category_id WHERE q.id=$1`, [id]);
    if (!q) return next();
    const isOwner = req.user && (req.user.id === q.client_id || req.user.role === 'admin');
    if (q.status === 'suspended' && !isOwner) return next();
    let responses = [];
    let myResponse = null;
    if (isOwner) {
      responses = await db.many(`SELECT r.*, u.full_name, u.photo_path, u.headline,
          (SELECT cv.id FROM conversations cv WHERE cv.user_low=LEAST(r.provider_id,$2::int) AND cv.user_high=GREATEST(r.provider_id,$2::int)) AS conversation_id
        FROM request_responses r JOIN users u ON u.id=r.provider_id WHERE r.request_id=$1 AND NOT u.is_banned ORDER BY r.created_at`, [q.id, q.client_id]);
    } else if (req.user) {
      myResponse = await db.one('SELECT * FROM request_responses WHERE request_id=$1 AND provider_id=$2', [q.id, req.user.id]);
    }
    res.render('requests/show', { title: q.title, q, isOwner, responses, myResponse });
  } catch (e) { next(e); }
});

router.post('/requests/:id/respond', requireRole('provider'), requireApprovedPhoto, async (req, res, next) => {
  try {
    const q = await db.one("SELECT * FROM client_requests WHERE id=$1 AND status='open'", [parseInt(req.params.id, 10) || 0]);
    if (!q || q.client_id === req.user.id) return next();
    const message = String(req.body.message || '').trim().slice(0, 2000);
    const price = parseInt(String(req.body.price || '').replace(/[^\d]/g, ''), 10) || null;
    if (message.length < 10) {
      req.flash('error', 'err.response_short');
      return res.redirect(`/requests/${q.id}`);
    }
    const created = await db.tx(async (c) => {
      const r = await c.query(
        'INSERT INTO request_responses (request_id, provider_id, message, price) VALUES ($1,$2,$3,$4) ON CONFLICT (request_id, provider_id) DO NOTHING RETURNING id',
        [q.id, req.user.id, message, price]
      );
      if (!r.rows.length) return null;
      const conv = await openConversation(req.user.id, q.client_id, { requestId: q.id }, c);
      const head = `« ${q.title} »${price ? ` — ${price.toLocaleString('fr-FR')} FCFA` : ''}\n`;
      await postMessage(conv.id, req.user.id, head + message, c);
      return conv;
    });
    req.flash(created ? 'success' : 'info', created ? 'flash.response_sent' : 'flash.already_responded');
    res.redirect(created ? `/messages/${created.id}` : `/requests/${q.id}`);
  } catch (e) { next(e); }
});

router.post('/requests/:id/close', requireAuth, async (req, res, next) => {
  try {
    const q = await db.one('SELECT * FROM client_requests WHERE id=$1', [parseInt(req.params.id, 10) || 0]);
    if (!q || (q.client_id !== req.user.id && req.user.role !== 'admin')) return next();
    const status = q.status === 'open' ? 'closed' : 'open';
    if (q.status !== 'suspended') await db.query('UPDATE client_requests SET status=$2 WHERE id=$1', [q.id, status]);
    res.redirect(`/requests/${q.id}`);
  } catch (e) { next(e); }
});

module.exports = router;
