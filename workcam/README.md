# Work.cam

Plateforme bilingue (FR/EN) de mise en relation entre particuliers et prestataires de services au Cameroun.

- **Comptes par numéro de téléphone** (+237), rôles *client*, *prestataire* et *administrateur*.
- **Photo de profil vérifiée** : détection automatique d'**exactement un visage** humain net, avec **validation manuelle** par l'administrateur en secours.
- **Annonces de services** (catégorie, ville, quartier, fourchette de prix) et **demandes de clients** auxquelles les prestataires répondent.
- **Messagerie interne** entre clients et prestataires.
- **Paiement de la publication** par **MTN Mobile Money** et **Orange Money** (agrégateur CamPay), activation automatique de l'annonce.
- **Gratuité de lancement** réglable depuis l'administration : activation, date de fin, quota global, quota par prestataire. Les tarifs payants s'appliquent seuls ensuite.
- **Administration** : tarifs (global et par catégorie), photos à vérifier, utilisateurs (suspension), annonces et demandes, paiements, signalements, statistiques.

## Démarrage rapide (développement)

Prérequis : Node.js 20+ et PostgreSQL 14+.

```bash
npm install
cp .env.example .env    # puis adaptez DATABASE_URL, mettez NODE_ENV=development et PAYMENT_GATEWAY=simulation
npm start               # crée les tables et lance http://localhost:3000
```

Créer le compte administrateur :

```bash
npm run create-admin -- 6XXXXXXXX "MotDePasseTrèsSolide" "Votre Nom"
```

Données de démonstration (facultatif, **jamais en production**) : `npm run seed:demo`, puis suppression avec `npm run seed:demo -- --clean`.

En mode `PAYMENT_GATEWAY=simulation`, un paiement réussit 6 secondes après la demande (un numéro finissant par `0000` simule un refus).

## Tests

```bash
npm test   # vérifie que chaque texte existe en FR et en EN
TEST_DATABASE_URL=postgres://postgres:postgres@localhost:5432/workcam_test npm test   # + parcours complet (base VIDÉE)
```

Le test de bout en bout couvre : inscription, connexion, refus d'une photo sans visage, demande de validation manuelle et approbation par l'admin, annonce gratuite (promotion), annonce payante via Mobile Money (simulation), idempotence du paiement, changement de tarifs, demande client, réponse, messagerie, protection CSRF, échappement HTML, signalement et suspension, version anglaise. Ajoutez `FACE_FIXTURE=/chemin/portrait.jpg` pour tester aussi l'acceptation automatique d'un vrai portrait.

## Documentation

| Document | Contenu |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, schéma de base de données, routes, flux de paiement et de modération |
| [docs/PAIEMENT.md](docs/PAIEMENT.md) | Intégration MTN MoMo / Orange Money via CamPay, démarches, pièges à éviter |
| [docs/MODERATION_PHOTOS.md](docs/MODERATION_PHOTOS.md) | Détection de visage : fonctionnement, réglages, faux positifs, validation manuelle |
| [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md) | Hébergement pas à pas sur un VPS, coûts, HTTPS, sauvegardes |
| [docs/PLAN.md](docs/PLAN.md) | Plan de lancement et évolutions prévues |

## Structure

```
src/
  server.js            démarrage (migration, préchargement du modèle de visage, expiration des annonces)
  app.js               Express : sécurité (Helmet/CSP), sessions PostgreSQL, CSRF, routes
  routes/              public, auth, account (profil + photo), listings, requests, messages, payments, admin
  services/            faceDetection, payments (campay, simulation), listings (gratuité/paiement), settings, phone, sms
  views/               pages EJS (rendu serveur, léger en 3G)
  i18n/messages.js     tous les textes, en français et en anglais
db/schema.sql          schéma PostgreSQL
scripts/               migrate, create-admin, seed-demo
public/                CSS, JavaScript, logo
deploy/                Caddyfile (HTTPS automatique), script de sauvegarde
test/                  tests automatisés
```
