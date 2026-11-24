'use strict';
const config = require('../config');

/**
 * Envoi de SMS (codes de vérification). Par défaut : affichage dans la console du serveur.
 * Pour la production, brancher ici un fournisseur SMS (ex. API d'un agrégateur local,
 * Africa's Talking, Twilio…) en ajoutant un cas dans le switch.
 */
async function sendSms(phone, text) {
  switch (config.smsProvider) {
    case 'console':
    default:
      console.log(`[SMS → ${phone}] ${text}`);
      return true;
  }
}

module.exports = { sendSms };
