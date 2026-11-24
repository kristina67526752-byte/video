'use strict';
const crypto = require('crypto');
const config = require('../../config');
const db = require('../../db');
const settings = require('../settings');

const gateways = {
  campay: require('./campay'),
  simulation: require('./simulation'),
};

function gateway(name = config.paymentGateway) {
  const g = gateways[name];
  if (!g) throw new Error(`Passerelle de paiement inconnue : ${name}`);
  if (name === 'simulation' && config.isProd && process.env.ALLOW_SIMULATION !== 'true') {
    throw new Error('La passerelle de simulation est désactivée en production');
  }
  return g;
}

const PAYMENT_TIMEOUT_MIN = 20;

/** Montant à payer pour publier une annonce de cette catégorie. */
async function listingFee(categoryId) {
  const s = await settings.getAll();
  const cat = await db.one('SELECT listing_fee FROM categories WHERE id = $1', [categoryId]);
  if (cat && cat.listing_fee !== null && cat.listing_fee !== undefined) return cat.listing_fee;
  return Number(s.listing_fee) || 0;
}

/** Démarre la collecte Mobile Money et enregistre le paiement en « pending ». */
async function startListingPayment({ user, listing, operator, phone, amount }) {
  const g = gateway();
  const externalReference = crypto.randomUUID();
  const payment = await db.one(
    `INSERT INTO payments (user_id, listing_id, amount, gateway, operator, phone, external_reference)
     VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *`,
    [user.id, listing.id, amount, g.name, operator, phone, externalReference]
  );
  try {
    const r = await g.initiate({
      amount, phone, externalReference,
      description: `Work.cam - publication annonce #${listing.id}`,
    });
    return await db.one(
      'UPDATE payments SET gateway_reference=$2, ussd_code=$3, raw=$4, updated_at=now() WHERE id=$1 RETURNING *',
      [payment.id, r.gatewayReference, r.ussdCode, JSON.stringify(r.raw || {})]
    );
  } catch (e) {
    console.error('[payments] initiation échouée', e.message);
    await db.query("UPDATE payments SET status='failed', failure_reason=$2, updated_at=now() WHERE id=$1", [payment.id, 'initiation_error']);
    throw e;
  }
}

/** Active (ou prolonge) l'annonce après paiement confirmé. Idempotent. */
async function finalize(paymentId, status, { reason = null, raw = null, amount = null } = {}) {
  return db.tx(async (c) => {
    const p = (await c.query('SELECT * FROM payments WHERE id=$1 FOR UPDATE', [paymentId])).rows[0];
    if (!p || p.status !== 'pending') return p;
    let finalStatus = status;
    let failure = reason;
    if (status === 'successful' && amount !== null && Number.isFinite(amount) && amount < p.amount) {
      finalStatus = 'failed'; failure = 'amount_mismatch';
    }
    const upd = (await c.query(
      'UPDATE payments SET status=$2, failure_reason=$3, raw=COALESCE($4, raw), updated_at=now() WHERE id=$1 RETURNING *',
      [p.id, finalStatus, failure, raw ? JSON.stringify(raw) : null]
    )).rows[0];
    if (finalStatus === 'successful' && p.listing_id) {
      const s = await settings.getAll();
      const days = parseInt(s.listing_duration_days, 10) || 30;
      await c.query(
        `UPDATE listings SET status='active',
           published_at = COALESCE(published_at, now()),
           expires_at = GREATEST(COALESCE(expires_at, now()), now()) + ($2 || ' days')::interval,
           updated_at = now()
         WHERE id=$1 AND status IN ('pending_payment','expired','active')`,
        [p.listing_id, String(days)]
      );
    }
    return upd;
  });
}

/** Interroge la passerelle si le paiement est encore en attente (utilisé par le polling et le webhook). */
async function refresh(payment) {
  if (!payment || payment.status !== 'pending' || !payment.gateway_reference) return payment;
  try {
    const r = await gateway(payment.gateway).getStatus(payment.gateway_reference);
    if (r.status !== 'pending') return await finalize(payment.id, r.status, { raw: r.raw, amount: r.amount });
  } catch (e) {
    console.error('[payments] vérification échouée', e.message);
  }
  const ageMin = (Date.now() - new Date(payment.created_at).getTime()) / 60000;
  if (ageMin > PAYMENT_TIMEOUT_MIN) return finalize(payment.id, 'failed', { reason: 'timeout' });
  return db.one('SELECT * FROM payments WHERE id=$1', [payment.id]);
}

module.exports = { listingFee, startListingPayment, refresh, finalize, gateway };
