'use strict';
/**
 * Données de DÉMONSTRATION pour visualiser le site (à ne pas lancer en production).
 *   npm run seed:demo            → ajoute des comptes, annonces et demandes fictifs
 *   npm run seed:demo -- --clean → supprime toutes les données de démo
 * Les comptes de démo ont des numéros +23762000000X et le mot de passe "demo-password".
 */
const bcrypt = require('bcryptjs');
const db = require('../src/db');
const { migrate } = require('./migrate');

const PROVIDERS = [
  ['Serge Tchoua', 'Électricien bâtiment · 12 ans d’expérience', 'Douala', 'electricite', 'Dépannage et installation électrique', 'Diagnostic de pannes, installation de tableaux, prises et éclairage, mise à la terre. Intervention rapide à Akwa, Bonapriso, Makepe et Logbessou. Matériel professionnel.', 5000, 25000, 'job', 'Akwa'],
  ['Mireille Ndzana', 'Couturière – tenues traditionnelles & modernes', 'Yaoundé', 'couture', 'Couture sur mesure : kaba, robes, costumes', 'Confection sur mesure en pagne, wax et tissus importés. Retouches rapides. Livraison possible dans tout Yaoundé.', 7000, 60000, 'job', 'Mvog-Mbi'],
  ['Hervé Fotso', 'Répétiteur maths & physique (Bac C/D)', 'Bafoussam', 'cours', 'Cours de maths et physique à domicile', 'Licencié en mathématiques, je prépare vos enfants au BEPC, Probatoire et Baccalauréat. Méthode, exercices types et suivi hebdomadaire.', 3000, 5000, 'hour', 'Tamdja'],
  ['Aïcha Bello', 'Coiffeuse à domicile', 'Garoua', 'coiffure-beaute', 'Tresses, nattes et soins à domicile', 'Tresses africaines, nattes collées, vanilles, soins capillaires. Je me déplace avec mon matériel.', 4000, 20000, 'job', 'Plateau'],
  ['Boris Eto’o Mbida', 'Mécanicien auto – diagnostic électronique', 'Douala', 'mecanique', 'Mécanique auto et diagnostic', 'Vidange, freins, embrayage, diagnostic électronique toutes marques. Garage à Ndokoti, déplacement possible.', 10000, 80000, 'job', 'Ndokoti'],
  ['Clarisse Abena', 'Ménage & repassage', 'Yaoundé', 'menage', 'Ménage, repassage et grand nettoyage', 'Ménage régulier ou ponctuel, repassage, nettoyage après travaux. Sérieuse et ponctuelle, références disponibles.', 15000, 60000, 'month', 'Bastos'],
];
const REQUESTS = [
  ['Réparer une fuite sous l’évier', 'Fuite sous l’évier de la cuisine depuis hier, il faut changer le siphon je pense. Disponible le week-end.', 'plomberie', 'Douala', 'Bonamoussadi', 10000],
  ['Peindre un salon de 25 m²', 'Murs et plafond à repeindre, peinture fournie. Travail à faire avant la fin du mois.', 'peinture', 'Yaoundé', 'Odza', 40000],
  ['Répétiteur d’anglais pour élève de 3e', 'Deux séances par semaine pour préparer le BEPC, en fin d’après-midi.', 'cours', 'Bamenda', null, 25000],
];

async function clean() {
  await db.query("DELETE FROM users WHERE phone LIKE '+23762000000%'");
}

(async () => {
  await migrate();
  await clean();
  if (process.argv.includes('--clean')) { console.log('Données de démo supprimées.'); return db.pool.end(); }
  const hash = await bcrypt.hash('demo-password', 10);
  const cat = Object.fromEntries((await db.many('SELECT id, slug FROM categories')).map((c) => [c.slug, c.id]));
  let i = 0;
  for (const [name, headline, city, slug, title, desc, pmin, pmax, unit, district] of PROVIDERS) {
    i++;
    const u = await db.one(
      `INSERT INTO users (role, full_name, phone, password_hash, city, headline, bio, availability, photo_status, phone_verified)
       VALUES ('provider',$1,$2,$3,$4,$5,$6,'Lun–Sam, 8h–18h','approved',TRUE) RETURNING id`,
      [name, `+23762000000${i}`, hash, city, headline, desc]
    );
    await db.query(
      `INSERT INTO listings (provider_id, category_id, title, description, city, district, price_min, price_max, price_unit, status, published_at, expires_at, is_free_promo, views)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'active', now() - ($10 || ' hours')::interval, now() + interval '30 days', TRUE, $11)`,
      [u.id, cat[slug], title, desc, city, district, pmin, pmax, unit, String(i * 5), 10 + i * 7]
    );
  }
  const c = await db.one(
    `INSERT INTO users (role, full_name, phone, password_hash, city, photo_status, phone_verified)
     VALUES ('client','Nadège Essomba','+237620000009',$1,'Douala','approved',TRUE) RETURNING id`, [hash]);
  for (const [title, desc, slug, city, district, budget] of REQUESTS) {
    await db.query('INSERT INTO client_requests (client_id, category_id, title, description, city, district, budget) VALUES ($1,$2,$3,$4,$5,$6,$7)',
      [c.id, cat[slug], title, desc, city, district, budget]);
  }
  console.log('Données de démo ajoutées (mot de passe : demo-password).');
  await db.pool.end();
})().catch((e) => { console.error(e); process.exit(1); });
