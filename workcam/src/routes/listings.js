'use strict';
const express = require('express');
const db = require('../db');
const config = require('../config');
const { requireAuth, requireRole, requireApprovedPhoto } = require('../middleware/auth');
const listingsService = require('../services/listings');
const { openConversation } = require('../services/conversations');

const router = express.Router();
const UNITS = ['job', 'hour', 'day', 'month'];

function parseForm(body) {
  const int = (v) => {
    const n = parseInt(String(v || '').replace(/[^\d]/g, ''), 10);
    return Number.isFinite(n) ? n : null;
  };
  return {
    title: String(body.title || '').trim().slice(0, 100),
    description: String(body.description || '').trim().slice(0, 4000),
    category_id: parseInt(body.category_id, 10) || null,
    city: String(body.city || ''),
    district: String(body.district || '').trim().slice(0, 80),
    price_min: int(body.price_min),
    price_max: int(body.price_max),
    price_unit: UNITS.includes(body.price_unit) ? body.price_unit : 'job',
  };
}

async function validate(form, t) {
  const errors = {};
  if (form.title.length < 8) errors.title = t('err.title');
  if (form.description.length < 30) errors.description = t('err.description');
  if (!form.category_id || !(await db.one('SELECT 1 FROM categories WHERE id=$1 AND is_active', [form.category_id]))) errors.category_id = t('err.category');
  if (!config.cities.includes(form.city)) errors.city = t('err.city');
  if (form.price_min !== null && form.price_max !== null && form.price_max < form.price_min) errors.price_max = t('err.price_range');
  if ((form.price_min || 0) > 100000000 || (form.price_max || 0) > 100000000) errors.price_max = t('err.price_range');
  return errors;
}

async function ownListing(req) {
  const l = await db.one('SELECT * FROM listings WHERE id=$1', [parseInt(req.params.id, 10) || 0]);
  if (!l) return null;
  if (l.provider_id !== req.user.id && req.user.role !== 'admin') return null;
  return l;
}

const categoriesList = () => db.many('SELECT * FROM categories WHERE is_active ORDER BY sort_order');

/* ---------- Création ---------- */
router.get('/listings/new', requireRole('provider'), requireApprovedPhoto, async (req, res, next) => {
  try {
    res.render('listings/form', {
      title: res.locals.t('listing.new'), categories: await categoriesList(), errors: {},
      form: { city: req.user.city, price_unit: 'job' }, listing: null,
    });
  } catch (e) { next(e); }
});

router.post('/listings', requireRole('provider'), requireApprovedPhoto, async (req, res, next) => {
  try {
    const form = parseForm(req.body);
    const errors = await validate(form, res.locals.t);
    if (Object.keys(errors).length) {
      return res.status(422).render('listings/form', { title: res.locals.t('listing.new'), categories: await categoriesList(), errors, form, listing: null });
    }
    const listing = await db.one(
      `INSERT INTO listings (provider_id, category_id, title, description, city, district, price_min, price_max, price_unit)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
      [req.user.id, form.category_id, form.title, form.description, form.city, form.district || null, form.price_min, form.price_max, form.price_unit]
    );
    return publishAndRedirect(req, res, listing);
  } catch (e) { next(e); }
});

async function publishAndRedirect(req, res, listing) {
  // Annonce déjà payée et non échue (ex. désactivée puis réactivée) : on la remet en ligne sans repayer.
  if (listing.published_at && listing.expires_at && new Date(listing.expires_at) > new Date()) {
    await db.query("UPDATE listings SET status='active', updated_at=now() WHERE id=$1", [listing.id]);
    req.flash('success', 'flash.listing_active');
    return res.redirect(`/listings/${listing.id}`);
  }
  const r = await listingsService.publish(listing);
  if (r.mode === 'payment') return res.redirect(`/listings/${listing.id}/pay`);
  req.flash('success', r.mode === 'free_promo' ? 'flash.listing_free_promo' : 'flash.listing_active');
  return res.redirect(`/listings/${listing.id}`);
}

/* ---------- Affichage ---------- */
router.get('/listings/:id', async (req, res, next) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (!id) return next();
    const l = await db.one(`SELECT l.*, u.full_name, u.photo_path, u.headline, u.city AS provider_city, u.created_at AS member_since,
        u.availability, u.price_note, u.is_banned, c.slug AS category_slug, c.name_fr, c.name_en, c.icon
      FROM listings l JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id WHERE l.id=$1`, [id]);
    if (!l) return next();
    const isOwner = req.user && (req.user.id === l.provider_id || req.user.role === 'admin');
    if ((l.status !== 'active' || l.is_banned) && !isOwner) return next();
    if (!isOwner) db.query('UPDATE listings SET views = views + 1 WHERE id=$1', [l.id]).catch(() => {});
    const similar = await db.many(`SELECT l.*, u.full_name, u.photo_path, c.name_fr, c.name_en, c.icon
      FROM listings l JOIN users u ON u.id=l.provider_id JOIN categories c ON c.id=l.category_id
      WHERE l.status='active' AND l.category_id=$1 AND l.id<>$2 AND NOT u.is_banned ORDER BY (l.city=$3) DESC, l.published_at DESC LIMIT 4`,
    [l.category_id, l.id, l.city]);
    res.render('listings/show', { title: l.title, l, isOwner, similar });
  } catch (e) { next(e); }
});

/* ---------- Modification ---------- */
router.get('/listings/:id/edit', requireAuth, async (req, res, next) => {
  try {
    const l = await ownListing(req);
    if (!l) return next();
    res.render('listings/form', { title: res.locals.t('listing.edit'), categories: await categoriesList(), errors: {}, form: l, listing: l });
  } catch (e) { next(e); }
});

router.post('/listings/:id/edit', requireAuth, async (req, res, next) => {
  try {
    const l = await ownListing(req);
    if (!l) return next();
    const form = parseForm(req.body);
    const errors = await validate(form, res.locals.t);
    if (Object.keys(errors).length) {
      return res.status(422).render('listings/form', { title: res.locals.t('listing.edit'), categories: await categoriesList(), errors, form, listing: l });
    }
    // Changer de catégorie sur une annonce en attente de paiement peut changer le tarif : on recalcule à la publication.
    await db.query(
      `UPDATE listings SET title=$2, description=$3, category_id=$4, city=$5, district=$6, price_min=$7, price_max=$8, price_unit=$9, updated_at=now() WHERE id=$1`,
      [l.id, form.title, form.description, form.category_id, form.city, form.district || null, form.price_min, form.price_max, form.price_unit]
    );
    req.flash('success', 'flash.saved');
    res.redirect(`/listings/${l.id}`);
  } catch (e) { next(e); }
});

router.post('/listings/:id/publish', requireRole('provider'), requireApprovedPhoto, async (req, res, next) => {
  try {
    const l = await ownListing(req);
    if (!l || l.status === 'suspended' || l.status === 'active') return res.redirect('/account');
    return publishAndRedirect(req, res, l);
  } catch (e) { next(e); }
});

router.post('/listings/:id/deactivate', requireAuth, async (req, res, next) => {
  try {
    const l = await ownListing(req);
    if (!l) return next();
    if (l.status === 'active' || l.status === 'pending_payment') {
      await db.query("UPDATE listings SET status='draft', updated_at=now() WHERE id=$1", [l.id]);
    }
    req.flash('info', 'flash.listing_hidden');
    res.redirect('/account');
  } catch (e) { next(e); }
});

router.post('/listings/:id/delete', requireAuth, async (req, res, next) => {
  try {
    const l = await ownListing(req);
    if (!l) return next();
    await db.query('DELETE FROM listings WHERE id=$1', [l.id]);
    req.flash('info', 'flash.deleted');
    res.redirect('/account');
  } catch (e) { next(e); }
});

/* ---------- Contact & signalement ---------- */
router.post('/listings/:id/contact', requireAuth, async (req, res, next) => {
  try {
    const l = await db.one("SELECT * FROM listings WHERE id=$1 AND status='active'", [parseInt(req.params.id, 10) || 0]);
    if (!l) return next();
    if (l.provider_id === req.user.id) return res.redirect(`/listings/${l.id}`);
    const conv = await openConversation(req.user.id, l.provider_id, { listingId: l.id });
    res.redirect(`/messages/${conv.id}?listing=${l.id}`);
  } catch (e) { next(e); }
});

router.post('/report', requireAuth, async (req, res, next) => {
  try {
    const type = ['listing', 'user', 'request'].includes(req.body.target_type) ? req.body.target_type : null;
    const id = parseInt(req.body.target_id, 10);
    const reason = String(req.body.reason || '').trim().slice(0, 1000);
    if (type && id && reason.length >= 5) {
      await db.query('INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES ($1,$2,$3,$4)', [req.user.id, type, id, reason]);
      req.flash('success', 'flash.reported');
    } else {
      req.flash('error', 'err.report');
    }
    const back = String(req.body.back || '/');
    res.redirect(back.startsWith('/') && !back.startsWith('//') ? back : '/');
  } catch (e) { next(e); }
});

module.exports = router;
