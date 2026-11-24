'use strict';
const db = require('../db');
const settings = require('./settings');
const payments = require('./payments');

/**
 * Décide comment publier une annonce :
 *  - gratuité de lancement active (date, quota global, quota par prestataire) → publication immédiate ;
 *  - tarif = 0 → publication immédiate ;
 *  - sinon → l'annonce passe en « pending_payment » et le prestataire est envoyé vers le paiement.
 */
async function publish(listing) {
  const s = await settings.getAll();
  const days = parseInt(s.listing_duration_days, 10) || 30;

  const freeByPromo = await db.tx(async (c) => {
    // Verrou sur le compteur pour que deux publications simultanées ne dépassent pas le quota.
    await c.query("INSERT INTO settings (key, value) VALUES ('promo_used', '0') ON CONFLICT (key) DO NOTHING");
    const usedRow = (await c.query("SELECT value FROM settings WHERE key='promo_used' FOR UPDATE")).rows[0];
    const fresh = { ...s, promo_used: Number(usedRow.value) || 0 };
    if (!settings.promoIsActive(fresh)) return false;
    if (fresh.promo_per_provider !== null && fresh.promo_per_provider !== undefined) {
      const { n } = (await c.query(
        'SELECT count(*)::int AS n FROM listings WHERE provider_id=$1 AND is_free_promo AND id<>$2', [listing.provider_id, listing.id]
      )).rows[0];
      if (n >= Number(fresh.promo_per_provider)) return false;
    }
    await c.query("UPDATE settings SET value = to_jsonb($1::int) WHERE key='promo_used'", [fresh.promo_used + 1]);
    await c.query(
      `UPDATE listings SET status='active', is_free_promo=TRUE, published_at=now(),
         expires_at = now() + ($2 || ' days')::interval, updated_at=now() WHERE id=$1`,
      [listing.id, String(days)]
    );
    return true;
  });
  settings.invalidate();
  if (freeByPromo) return { mode: 'free_promo' };

  const fee = await payments.listingFee(listing.category_id);
  if (fee <= 0) {
    await db.query(
      `UPDATE listings SET status='active', published_at=now(), expires_at = now() + ($2 || ' days')::interval, updated_at=now() WHERE id=$1`,
      [listing.id, String(days)]
    );
    return { mode: 'free' };
  }
  await db.query("UPDATE listings SET status='pending_payment', updated_at=now() WHERE id=$1", [listing.id]);
  return { mode: 'payment', amount: fee };
}

/** Passe en « expired » les annonces arrivées à échéance (appelé périodiquement). */
async function expireOld() {
  await db.query("UPDATE listings SET status='expired', updated_at=now() WHERE status='active' AND expires_at < now()");
}

module.exports = { publish, expireOld };
