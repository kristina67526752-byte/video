'use strict';
const db = require('../db');

const DEFAULT_SETTINGS = {
  listing_fee: 1000,             // FCFA — frais de publication par défaut
  listing_duration_days: 30,     // durée de visibilité d'une annonce payée/gratuite
  promo_enabled: true,           // gratuité de lancement active
  promo_end_date: null,          // 'YYYY-MM-DD' ou null (sans date de fin)
  promo_quota: null,             // nombre max de publications gratuites, ou null (illimité)
  promo_used: 0,                 // compteur de publications gratuites déjà consommées
  promo_per_provider: 3,         // max d'annonces gratuites par prestataire (null = illimité)
};

let cache = null;
let cacheAt = 0;

async function getAll() {
  if (cache && Date.now() - cacheAt < 5000) return cache;
  const rows = await db.many('SELECT key, value FROM settings');
  const s = { ...DEFAULT_SETTINGS };
  for (const r of rows) s[r.key] = r.value;
  cache = s; cacheAt = Date.now();
  return s;
}

async function set(key, value, client = db) {
  await client.query(
    'INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
    [key, JSON.stringify(value)]
  );
  cache = null;
}

/** La gratuité de lancement est-elle active aujourd'hui (date + quota global) ? */
function promoIsActive(s, now = new Date()) {
  if (!s.promo_enabled) return false;
  if (s.promo_end_date) {
    const end = new Date(`${s.promo_end_date}T23:59:59+01:00`); // heure du Cameroun (WAT)
    if (now > end) return false;
  }
  if (s.promo_quota !== null && s.promo_quota !== undefined && s.promo_used >= s.promo_quota) return false;
  return true;
}

module.exports = { DEFAULT_SETTINGS, getAll, set, promoIsActive, invalidate: () => { cache = null; } };
