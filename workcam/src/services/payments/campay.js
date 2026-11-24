'use strict';
/**
 * Passerelle CamPay (MTN Mobile Money + Orange Money Cameroun).
 * Endpoints utilisés (cf. SDK officiel CamPay) :
 *   POST {base}/api/token/                 {username, password}  → {token}
 *   POST {base}/api/collect/               {amount, currency, from, description, external_reference}
 *                                          → {reference, ussd_code, operator}
 *   GET  {base}/api/transaction/{ref}/     → {status: PENDING|SUCCESSFUL|FAILED, amount, operator, ...}
 * Authentification : en-tête « Authorization: Token <token> ».
 * Démo : https://demo.campay.net — Production : https://www.campay.net
 */
const config = require('../../config');

let cachedToken = null;
let cachedAt = 0;
const TOKEN_TTL_MS = 30 * 60 * 1000; // renouvelé par prudence toutes les 30 min

async function getToken(force = false) {
  if (config.campay.permanentToken) return config.campay.permanentToken;
  if (!force && cachedToken && Date.now() - cachedAt < TOKEN_TTL_MS) return cachedToken;
  const res = await fetch(`${config.campay.baseUrl}/api/token/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: config.campay.username, password: config.campay.password }),
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`CamPay token HTTP ${res.status}`);
  const json = await res.json();
  if (!json.token) throw new Error('CamPay : jeton absent de la réponse');
  cachedToken = json.token; cachedAt = Date.now();
  return cachedToken;
}

async function call(method, path, body, retry = true) {
  const token = await getToken();
  const res = await fetch(`${config.campay.baseUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Token ${token}` },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  if (res.status === 401 && retry && !config.campay.permanentToken) {
    cachedToken = null;
    return call(method, path, body, false);
  }
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch (e) { json = { raw: text }; }
  if (!res.ok) {
    const err = new Error(`CamPay ${path} HTTP ${res.status}: ${json.message || text.slice(0, 200)}`);
    err.response = json;
    throw err;
  }
  return json;
}

function mapStatus(s) {
  const v = String(s || '').toUpperCase();
  if (v === 'SUCCESSFUL') return 'successful';
  if (v === 'FAILED') return 'failed';
  return 'pending';
}

module.exports = {
  name: 'campay',
  async initiate({ amount, phone, description, externalReference }) {
    const json = await call('POST', '/api/collect/', {
      amount: String(amount),
      currency: 'XAF',
      from: phone.replace(/^\+/, ''),            // format attendu : 2376XXXXXXXX
      description: description.slice(0, 100),
      external_reference: externalReference,
    });
    if (!json.reference) throw new Error('CamPay : référence absente de la réponse');
    return { gatewayReference: json.reference, ussdCode: json.ussd_code || null, status: 'pending', raw: json };
  },
  async getStatus(gatewayReference) {
    const json = await call('GET', `/api/transaction/${encodeURIComponent(gatewayReference)}/`);
    return { status: mapStatus(json.status), amount: json.amount !== undefined ? Number(json.amount) : null, raw: json };
  },
};
