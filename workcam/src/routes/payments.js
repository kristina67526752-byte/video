'use strict';
const express = require('express');
const rateLimit = require('express-rate-limit');
const db = require('../db');
const { requireAuth } = require('../middleware/auth');
const { normalizePhone, detectOperator } = require('../services/phone');
const payments = require('../services/payments');
const settings = require('../services/settings');

const router = express.Router();
const payLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, limit: 10, standardHeaders: 'draft-7', legacyHeaders: false,
  handler: (req, res, next) => { const e = new Error('rate'); e.status = 429; next(e); },
});

async function ownPendingListing(req) {
  const l = await db.one(`SELECT l.*, c.name_fr, c.name_en FROM listings l JOIN categories c ON c.id=l.category_id WHERE l.id=$1`, [parseInt(req.params.id, 10) || 0]);
  if (!l || l.provider_id !== req.user.id) return null;
  return l;
}

router.get('/listings/:id/pay', requireAuth, async (req, res, next) => {
  try {
    const l = await ownPendingListing(req);
    if (!l) return next();
    if (l.status !== 'pending_payment') return res.redirect(`/listings/${l.id}`);
    const amount = await payments.listingFee(l.category_id);
    const s = await settings.getAll();
    const phone = req.user.phone.replace(/^\+237/, '');
    res.render('listings/pay', {
      title: res.locals.t('pay.title'), l, amount, days: s.listing_duration_days,
      form: { phone, operator: detectOperator(req.user.phone) || 'mtn' }, error: null,
    });
  } catch (e) { next(e); }
});

router.post('/listings/:id/pay', requireAuth, payLimiter, async (req, res, next) => {
  try {
    const t = res.locals.t;
    const l = await ownPendingListing(req);
    if (!l) return next();
    if (l.status !== 'pending_payment') return res.redirect(`/listings/${l.id}`);
    const amount = await payments.listingFee(l.category_id);
    const s = await settings.getAll();
    const operator = req.body.operator === 'orange' ? 'orange' : 'mtn';
    const phone = normalizePhone(req.body.phone);
    const render = (error) => res.status(422).render('listings/pay', {
      title: t('pay.title'), l, amount, days: s.listing_duration_days, form: { phone: req.body.phone, operator }, error,
    });
    if (!phone) return render(t('err.phone'));
    const detected = detectOperator(phone);
    if (detected && detected !== operator) return render(t('err.operator_mismatch'));
    if (amount <= 0) return res.redirect(`/listings/${l.id}`);
    // Un seul paiement en attente à la fois pour une annonce.
    const pending = await db.one("SELECT id FROM payments WHERE listing_id=$1 AND status='pending' AND created_at > now() - interval '20 minutes'", [l.id]);
    if (pending) return res.redirect(`/payments/${pending.id}`);
    let p;
    try {
      p = await payments.startListingPayment({ user: req.user, listing: l, operator, phone, amount });
    } catch (e) {
      return render(t('err.payment_init'));
    }
    res.redirect(`/payments/${p.id}`);
  } catch (e) { next(e); }
});

router.get('/payments/:id', requireAuth, async (req, res, next) => {
  try {
    let p = await db.one('SELECT * FROM payments WHERE id=$1 AND user_id=$2', [parseInt(req.params.id, 10) || 0, req.user.id]);
    if (!p) return next();
    p = await payments.refresh(p);
    res.render('listings/payment_status', { title: res.locals.t('pay.title'), p });
  } catch (e) { next(e); }
});

router.get('/api/payments/:id/status', requireAuth, async (req, res, next) => {
  try {
    let p = await db.one('SELECT * FROM payments WHERE id=$1 AND user_id=$2', [parseInt(req.params.id, 10) || 0, req.user.id]);
    if (!p) return res.status(404).json({ error: 'not_found' });
    p = await payments.refresh(p);
    res.json({ status: p.status, listing_id: p.listing_id });
  } catch (e) { next(e); }
});

/**
 * Webhook CamPay (URL à déclarer dans le tableau de bord CamPay : {BASE_URL}/webhooks/campay).
 * Sécurité : on ne fait PAS confiance au contenu de la notification. Elle sert uniquement de signal :
 * on retrouve le paiement par sa référence puis on interroge l'API CamPay (authentifiée) pour connaître
 * le vrai statut. Une notification falsifiée ne peut donc pas activer une annonce.
 */
async function campayWebhook(req, res) {
  try {
    const src = { ...req.query, ...(req.body || {}) };
    const ref = String(src.reference || '').slice(0, 100);
    const ext = String(src.external_reference || '').slice(0, 100);
    const p = await db.one(
      "SELECT * FROM payments WHERE gateway='campay' AND ((gateway_reference=$1 AND $1<>'') OR (external_reference=$2 AND $2<>''))",
      [ref, ext]
    );
    if (p) await payments.refresh(p);
  } catch (e) {
    console.error('[webhook campay]', e.message);
  }
  res.status(200).json({ received: true });
}
router.get('/webhooks/campay', campayWebhook);
router.post('/webhooks/campay', campayWebhook);

module.exports = router;
