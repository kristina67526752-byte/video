'use strict';
/**
 * Passerelle de SIMULATION pour développer et tester sans argent réel.
 * - Un paiement devient « réussi » 6 secondes après l'initiation.
 * - Un numéro se terminant par 0000 simule un refus (solde insuffisant / annulation).
 * Interdite en production sauf si ALLOW_SIMULATION=true.
 */
const crypto = require('crypto');

const store = new Map();

module.exports = {
  name: 'simulation',
  async initiate({ amount, phone }) {
    const ref = `SIM-${crypto.randomUUID()}`;
    store.set(ref, { at: Date.now(), fail: /0000$/.test(phone), amount });
    const op = /^\+2376(9\d|5[5-9]|8[5-9]|40)/.test(phone) ? '#150*50#' : '*126#';
    return { gatewayReference: ref, ussdCode: op, status: 'pending', raw: { simulated: true } };
  },
  async getStatus(ref) {
    const t = store.get(ref);
    if (!t) return { status: 'failed', amount: null, raw: { simulated: true, error: 'unknown reference' } };
    if (Date.now() - t.at < 6000) return { status: 'pending', amount: t.amount, raw: { simulated: true } };
    return { status: t.fail ? 'failed' : 'successful', amount: t.amount, raw: { simulated: true } };
  },
};
