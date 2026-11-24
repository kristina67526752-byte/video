'use strict';
require('dotenv').config();

const env = process.env;
const isProd = env.NODE_ENV === 'production';

if (isProd && (!env.SESSION_SECRET || env.SESSION_SECRET.length < 32)) {
  throw new Error('SESSION_SECRET doit faire au moins 32 caractères en production');
}

module.exports = {
  isProd,
  port: parseInt(env.PORT || '3000', 10),
  baseUrl: (env.BASE_URL || 'http://localhost:3000').replace(/\/$/, ''),
  databaseUrl: env.DATABASE_URL || 'postgres://postgres:postgres@localhost:5432/workcam',
  sessionSecret: env.SESSION_SECRET || 'dev-secret-change-me-dev-secret-change-me',
  uploadDir: env.UPLOAD_DIR || require('path').join(__dirname, '..', 'uploads'),
  phoneVerification: env.PHONE_VERIFICATION === 'on',
  smsProvider: env.SMS_PROVIDER || 'console',
  paymentGateway: env.PAYMENT_GATEWAY || 'simulation', // 'campay' | 'simulation'
  campay: {
    baseUrl: (env.CAMPAY_BASE_URL || 'https://demo.campay.net').replace(/\/$/, ''),
    username: env.CAMPAY_USERNAME || '',
    password: env.CAMPAY_PASSWORD || '',
    permanentToken: env.CAMPAY_TOKEN || '',
  },
  photoMaxFailuresBeforeManual: parseInt(env.PHOTO_MAX_FAILURES || '2', 10),
  supportPhone: env.SUPPORT_PHONE || '',
  supportEmail: env.SUPPORT_EMAIL || '',
  cities: [
    'Douala', 'Yaoundé', 'Bafoussam', 'Garoua', 'Bamenda', 'Maroua', 'Ngaoundéré', 'Bertoua',
    'Ebolowa', 'Kribi', 'Limbé', 'Buea', 'Kumba', 'Nkongsamba', 'Dschang', 'Edéa', 'Foumban',
    'Mbouda', 'Sangmélima', 'Kousséri', 'Mbalmayo', 'Bafang', 'Bangangté', 'Batouri', 'Autre',
  ],
};
