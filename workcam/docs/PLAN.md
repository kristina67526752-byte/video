# Plan de lancement et évolutions

## Étape 1 — MVP (fait, dans ce dépôt)

- Inscription et connexion par téléphone, rôles client / prestataire / admin
- Photo de profil avec détection de visage, validation manuelle en secours
- Annonces de services, recherche par catégorie, ville et mots-clés
- Demandes de clients et réponses des prestataires
- Messagerie interne avec actualisation automatique
- Paiement des annonces par MTN MoMo et Orange Money (CamPay), activation automatique
- Gratuité de lancement pilotée depuis l'admin (date de fin, quota global, quota par prestataire)
- Tarifs modifiables (global et par catégorie), durée de visibilité
- Administration complète : statistiques, photos, utilisateurs, annonces, paiements, signalements
- Site bilingue FR/EN, pensé pour le mobile, sécurisé
- Déploiement Docker + HTTPS automatique, sauvegardes

## Étape 2 — Avant l'ouverture publique (1 à 3 semaines)

1. Ouvrir le compte CamPay, tester en démo puis en réel ([PAIEMENT.md](PAIEMENT.md)).
2. Mettre le site en ligne ([DEPLOIEMENT.md](DEPLOIEMENT.md)).
3. Faire relire les CGU et la politique de confidentialité.
4. Recruter 20 à 50 prestataires dans **une seule ville d'abord** (Douala ou Yaoundé), en personne et via WhatsApp/Facebook, avec la gratuité de lancement.
5. Régler les seuils de la détection de visage d'après les premières demandes manuelles.

## Étape 3 — Après les premiers utilisateurs

Par ordre d'impact :
1. **Notifications** quand un message ou une réponse arrive : SMS (fournisseur à brancher dans `src/services/sms.js`) ou WhatsApp Business. Sans notification, beaucoup d'utilisateurs ne reviendront pas lire leurs messages.
2. **Avis et notes** après une prestation (uniquement entre personnes ayant échangé des messages).
3. **Photos de réalisations** dans les annonces.
4. **Mise en avant payante** (annonce « à la une ») : deuxième source de revenus.
5. **Vérification d'identité** facultative (badge « identité vérifiée ») avec contrôle manuel d'une pièce.
6. Stockage des images sur S3/Cloudinary et CDN quand le trafic augmente.
7. Application mobile (PWA d'abord, puis Flutter/React Native si besoin), avec une API JSON au-dessus des services existants.

## Indicateurs à suivre (tableau de bord admin)

- Prestataires avec photo validée, annonces en ligne
- Demandes publiées et pourcentage ayant reçu au moins une réponse
- Messages par semaine (signe que les mises en relation ont lieu)
- Taux de réussite des paiements et revenus du mois
- Délai de traitement des photos en attente et des signalements
