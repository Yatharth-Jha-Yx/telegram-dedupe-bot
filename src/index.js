// Telegram duplicate-file cleaner bot for Cloudflare Workers.
// Remembers every file posted in a group (by Telegram's file_unique_id)
// and deletes later messages that repost the same file.

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("OK");

    // Reject requests that don't come from Telegram.
    const sent = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "").trim();
    const expected = String(env.WEBHOOK_SECRET || "").replace(/^﻿/, "").trim();
    if (!expected || sent !== expected) {
      return new Response("Unauthorized", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad request", { status: 400 });
    }

    // Answer Telegram at once; do the work in the background.
    ctx.waitUntil(handleUpdate(update, env).catch((e) => console.error(e)));
    return new Response("OK");
  },
};

async function handleUpdate(update, env) {
  const msg = update.message || update.channel_post;
  if (!msg) return;

  const chatType = msg.chat.type;
  if (chatType !== "group" && chatType !== "supergroup" && chatType !== "channel") return;

  if (msg.text && msg.text.startsWith("/dupestats")) {
    return sendStats(msg, env);
  }

  const fileId = getFileUniqueId(msg);
  if (!fileId) return;

  const key = `${msg.chat.id}:${fileId}`;
  const original = await env.DUPES.get(key);

  if (original === null) {
    // First time this file is seen in this chat: remember it.
    await env.DUPES.put(key, String(msg.message_id), ttlOptions(env));
    return;
  }

  if (original === String(msg.message_id)) return;

  const deleted = await tg(env, "deleteMessage", {
    chat_id: msg.chat.id,
    message_id: msg.message_id,
  });

  if (deleted.ok) {
    await env.DUPES.put(`${msg.chat.id}:count`,
      String((Number(await env.DUPES.get(`${msg.chat.id}:count`)) || 0) + 1));

    if (env.NOTIFY === "true") {
      const who = msg.from ? (msg.from.username ? "@" + msg.from.username : msg.from.first_name) : "Someone";
      const notice = await tg(env, "sendMessage", {
        chat_id: msg.chat.id,
        text: `🗑 Removed a duplicate file from ${who}. It was already posted earlier.`,
        reply_parameters: { message_id: Number(original), allow_sending_without_reply: true },
        disable_notification: true,
      });

      // Remove the notice itself after a few seconds (max ~25s on Workers).
      const secs = Math.min(25, Math.max(0, Number(env.NOTICE_SECONDS ?? 5)));
      if (notice.ok && secs > 0) {
        await new Promise((r) => setTimeout(r, secs * 1000));
        await tg(env, "deleteMessage", {
          chat_id: msg.chat.id,
          message_id: notice.result.message_id,
        });
      }
    }
  } else {
    console.log("deleteMessage failed:", deleted.description);
  }
}

// Telegram gives each file a file_unique_id that is the same no matter who
// sends it, so identical files have identical IDs.
function getFileUniqueId(msg) {
  if (msg.document) return msg.document.file_unique_id;
  if (msg.photo && msg.photo.length) return msg.photo[msg.photo.length - 1].file_unique_id;
  if (msg.video) return msg.video.file_unique_id;
  if (msg.audio) return msg.audio.file_unique_id;
  if (msg.voice) return msg.voice.file_unique_id;
  if (msg.animation) return msg.animation.file_unique_id;
  if (msg.video_note) return msg.video_note.file_unique_id;
  return null;
}

function ttlOptions(env) {
  const days = Number(env.REMEMBER_DAYS);
  return days > 0 ? { expirationTtl: Math.max(60, Math.floor(days * 86400)) } : undefined;
}

async function sendStats(msg, env) {
  const count = (await env.DUPES.get(`${msg.chat.id}:count`)) || "0";
  await tg(env, "sendMessage", {
    chat_id: msg.chat.id,
    text: `Duplicates removed in this chat: ${count}`,
  });
}

async function tg(env, method, body) {
  const res = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}
