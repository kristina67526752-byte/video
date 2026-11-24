'use strict';
const config = require('./config');
const { createApp } = require('./app');
const { migrate } = require('../scripts/migrate');
const { warmUp } = require('./services/faceDetection');
const { expireOld } = require('./services/listings');

(async () => {
  await migrate();
  if (config.isProd && config.paymentGateway === 'simulation' && process.env.ALLOW_SIMULATION !== 'true') {
    console.warn('⚠️  PAYMENT_GATEWAY=simulation est refusé en production : configurez CamPay (voir docs/PAIEMENT.md).');
  }
  const app = createApp();
  app.listen(config.port, () => console.log(`Work.cam en ligne sur ${config.baseUrl} (port ${config.port})`));
  warmUp();
  expireOld().catch(() => {});
  setInterval(() => expireOld().catch((e) => console.error('[expire]', e.message)), 10 * 60 * 1000);
})().catch((e) => { console.error('Démarrage impossible :', e); process.exit(1); });
