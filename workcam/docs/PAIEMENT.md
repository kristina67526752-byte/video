# Paiement MTN Mobile Money et Orange Money

## Le choix : un agrégateur, CamPay

Intégrer MTN MoMo et Orange Money séparément veut dire deux contrats, deux API, deux procédures d'agrément. Un **agrégateur** donne une seule API pour les deux opérateurs et reverse l'argent sur votre compte.

Work.cam est branché sur **CamPay** (société camerounaise), qui propose une API REST simple :

| Étape | Appel CamPay |
|---|---|
| Authentification | `POST /api/token/` avec `username` et `password` de votre application → `token` |
| Demande de paiement | `POST /api/collect/` avec `amount`, `currency: "XAF"`, `from: "2376XXXXXXXX"`, `description`, `external_reference` → `reference`, `ussd_code`, `operator` |
| Vérification | `GET /api/transaction/{reference}/` → `status` : `PENDING`, `SUCCESSFUL` ou `FAILED` |

En-tête : `Authorization: Token <token>`. Serveurs : démo `https://demo.campay.net`, production `https://www.campay.net`.

Ces informations viennent du SDK officiel de CamPay (sa documentation en ligne n'était pas lisible sans compte). **Avant la mise en production, ouvrez votre compte et confirmez ces points dans leur documentation** : le code est isolé dans `src/services/payments/campay.js`, et une correction se fait à cet endroit seulement.

Autres agrégateurs camerounais si CamPay ne vous convient pas : **Notch Pay**, **Monetbil**, **Fapshi**. Pour en changer, ajoutez un fichier dans `src/services/payments/` avec les deux fonctions `initiate()` et `getStatus()` (voir `simulation.js`, 30 lignes), puis déclarez-le dans `index.js`.

## Démarches

1. **Créez un compte marchand** sur campay.net. Prévoyez les pièces d'identité demandées (KYC) et, selon leurs conditions, un document d'entreprise. Vous êtes en Russie : il vous faudra probablement **un numéro Mobile Money camerounais** pour recevoir les fonds et, si une entreprise est exigée, **un associé ou mandataire au Cameroun**. Renseignez-vous dès maintenant, c'est souvent l'étape la plus longue.
2. **Créez une application** dans le tableau de bord : vous obtenez un *username* et un *password* d'API.
3. **Testez en démo** : dans `.env`, mettez
   ```
   PAYMENT_GATEWAY=campay
   CAMPAY_BASE_URL=https://demo.campay.net
   CAMPAY_USERNAME=...
   CAMPAY_PASSWORD=...
   ```
   Payez une annonce avec votre propre numéro et un petit montant (l'environnement de démo limite souvent les montants : fixez provisoirement un tarif de 5 à 25 FCFA dans l'admin).
4. **Déclarez l'URL de notification** (webhook) dans le tableau de bord CamPay : `https://VOTRE-DOMAINE/webhooks/campay`.
5. **Passez en production** : `CAMPAY_BASE_URL=https://www.campay.net` avec les identifiants de production, puis remettez votre vrai tarif dans l'admin.

## Sécurité du flux

- **On ne fait jamais confiance à la notification** : quand CamPay appelle `/webhooks/campay`, Work.cam retrouve le paiement puis **redemande le statut à l'API CamPay** avec ses identifiants. Une fausse notification ne peut donc pas activer une annonce.
- Le **montant** renvoyé par CamPay est comparé au montant attendu.
- La finalisation est **idempotente** : une notification reçue deux fois ne prolonge pas l'annonce deux fois (testé).
- Même sans webhook (serveur injoignable, configuration oubliée), la page de paiement interroge CamPay toutes les quelques secondes : le paiement est quand même confirmé.
- Un paiement sans réponse après 20 minutes passe en `failed` ; l'utilisateur peut réessayer.
- L'administrateur peut **revérifier** un paiement en attente depuis `/admin/payments`.

## Pièges à éviter

- **Format du numéro** : CamPay attend `2376XXXXXXXX` (sans `+`). Le site normalise automatiquement les saisies (`677 12 34 56`, `+237677123456`, `00237…`).
- **Mauvais opérateur** : un numéro Orange payé en « MTN » échoue. Le site contrôle le préfixe (MTN : 67X, 650–654, 680–684 ; Orange : 69X, 655–659, 685–689, 640). Mettez à jour `src/services/phone.js` si l'autorité de régulation attribue de nouvelles plages.
- **L'utilisateur ne reçoit pas la demande de confirmation** : la page affiche le code USSD (`*126#` MTN, `#150*50#` Orange) pour valider manuellement.
- **Solde insuffisant / délai dépassé** : statut `FAILED`, message clair et bouton « Réessayer ».
- **Commission** : l'agrégateur prélève un pourcentage sur chaque transaction. Intégrez-le dans vos tarifs.
- **Jamais de simulation en production** : le serveur refuse `PAYMENT_GATEWAY=simulation` quand `NODE_ENV=production` (sauf `ALLOW_SIMULATION=true` explicite).
- **Fiscalité** : renseignez-vous sur les obligations déclaratives des revenus perçus au Cameroun.
