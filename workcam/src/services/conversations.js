'use strict';
const db = require('../db');

/** Trouve ou crée la conversation entre deux utilisateurs (une seule par paire). */
async function openConversation(userA, userB, { listingId = null, requestId = null } = {}, client = db) {
  const low = Math.min(userA, userB);
  const high = Math.max(userA, userB);
  const r = await client.query(
    `INSERT INTO conversations (user_low, user_high, listing_id, request_id) VALUES ($1,$2,$3,$4)
     ON CONFLICT (user_low, user_high) DO UPDATE
       SET listing_id = COALESCE($3, conversations.listing_id), request_id = COALESCE($4, conversations.request_id)
     RETURNING *`,
    [low, high, listingId, requestId]
  );
  return r.rows[0];
}

async function postMessage(conversationId, senderId, body, client = db) {
  const m = (await client.query(
    'INSERT INTO messages (conversation_id, sender_id, body) VALUES ($1,$2,$3) RETURNING *', [conversationId, senderId, body]
  )).rows[0];
  await client.query('UPDATE conversations SET last_message_at=now() WHERE id=$1', [conversationId]);
  return m;
}

module.exports = { openConversation, postMessage };
