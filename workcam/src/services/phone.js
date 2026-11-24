'use strict';
/**
 * Numéros camerounais : +237 suivi de 9 chiffres (mobiles : 6XXXXXXXX, fixes : 2XXXXXXXX).
 * Préfixes opérateurs (indicatifs, à vérifier si l'ARCEP/ART réattribue des plages) :
 *  MTN    : 67X, 650–654, 680–684
 *  Orange : 69X, 655–659, 685–689, 640
 */
function normalizePhone(input) {
  let d = String(input || '').replace(/[^\d+]/g, '');
  if (d.startsWith('+')) d = d.slice(1);
  if (d.startsWith('00')) d = d.slice(2);
  if (d.length === 12 && d.startsWith('237')) d = d.slice(3);
  if (!/^[26]\d{8}$/.test(d)) return null;
  return `+237${d}`;
}

function detectOperator(phone) {
  const n = String(phone).replace(/^\+237/, '');
  if (/^6(7\d|5[0-4]|8[0-4])/.test(n)) return 'mtn';
  if (/^6(9\d|5[5-9]|8[5-9]|40)/.test(n)) return 'orange';
  return null;
}

/** Affichage lisible : +237 6 77 12 34 56 */
function formatPhone(phone) {
  const n = String(phone || '').replace(/^\+237/, '');
  if (n.length !== 9) return phone || '';
  return `+237 ${n[0]} ${n.slice(1, 3)} ${n.slice(3, 5)} ${n.slice(5, 7)} ${n.slice(7)}`;
}

module.exports = { normalizePhone, detectOperator, formatPhone };
