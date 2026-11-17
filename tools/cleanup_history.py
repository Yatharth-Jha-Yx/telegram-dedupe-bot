"""
One-time cleanup of duplicate files already in a Telegram group's history.

The bot only sees new messages, so this script logs in as YOUR Telegram
account (which can read full history), keeps the OLDEST copy of each file
and deletes the later copies.

Safe by default: without --delete it only shows what it WOULD delete.

Setup:
  1. Get api_id and api_hash at https://my.telegram.org -> "API development tools"
  2. pip install -r tools/requirements.txt

Usage:
  python tools/cleanup_history.py "<group link, @username or name>"            # preview
  python tools/cleanup_history.py "<group>" --delete                           # delete
  python tools/cleanup_history.py "<group>" --limit 5000 --delete              # newest 5000 msgs only
"""

import argparse
import asyncio
import getpass
import os
import sys

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

SESSION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleanup")


def file_key(msg):
    """Same file => same key, no matter who sent or forwarded it."""
    media = msg.media
    if isinstance(media, MessageMediaPhoto) and media.photo:
        return ("photo", media.photo.id)
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        # Skip stickers and custom emoji, just like the bot.
        for attr in getattr(doc, "attributes", []):
            if type(attr).__name__ in ("DocumentAttributeSticker", "DocumentAttributeCustomEmoji"):
                return None
        return ("doc", doc.id)
    return None


def describe(msg):
    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"
    name = getattr(msg.file, "name", None) if msg.file else None
    return name or (msg.file.mime_type if msg.file else "file")


async def main():
    p = argparse.ArgumentParser(description="Delete duplicate files from a Telegram group's history.")
    p.add_argument("group", help="Group invite link, @username, numeric id, or exact name")
    p.add_argument("--delete", action="store_true", help="Actually delete (default is preview only)")
    p.add_argument("--limit", type=int, default=None, help="Only scan the newest N messages")
    args = p.parse_args()

    api_id = os.environ.get("TG_API_ID") or input("api_id: ").strip()
    api_hash = os.environ.get("TG_API_HASH") or getpass.getpass("api_hash (hidden): ").strip()

    async with TelegramClient(SESSION, int(api_id), api_hash) as client:
        # First run asks for your phone number and login code in this window.
        await client.start()

        group = args.group
        if group.lstrip("-").isdigit():
            group = int(group)
        chat = None
        if isinstance(group, str) and not group.startswith(("@", "http", "t.me")):
            async for d in client.iter_dialogs():
                if (d.is_group or d.is_channel) and d.name.strip().lower() == group.strip().lower():
                    chat = d.entity
                    break
        if chat is None:
            chat = await client.get_entity(group)
        title = getattr(chat, "title", str(group))
        print(f"\nScanning '{title}' (oldest -> newest)...")

        # Read newest-first (so --limit means "newest N"), then process oldest-first.
        messages = []
        async for msg in client.iter_messages(chat, limit=args.limit):
            if msg.media:
                messages.append(msg)
        messages.reverse()

        seen = {}          # key -> first message id
        duplicates = []    # later copies
        for msg in messages:
            key = file_key(msg)
            if key is None:
                continue
            if key in seen:
                duplicates.append(msg)
            else:
                seen[key] = msg.id

        print(f"Files checked: {len(seen) + len(duplicates)}   unique: {len(seen)}   duplicates: {len(duplicates)}\n")
        for msg in duplicates[:50]:
            when = msg.date.strftime("%Y-%m-%d %H:%M")
            print(f"  #{msg.id:<8} {when}  {describe(msg)}  (original #{seen[file_key(msg)]})")
        if len(duplicates) > 50:
            print(f"  ... and {len(duplicates) - 50} more")

        if not duplicates:
            print("Nothing to clean up.")
            return
        if not args.delete:
            print("\nPreview only. Run again with --delete to remove these.")
            return

        confirm = input(f"\nDelete {len(duplicates)} messages for everyone? Type YES: ")
        if confirm.strip() != "YES":
            print("Cancelled.")
            return

        ids = [m.id for m in duplicates]
        deleted = 0
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            while True:
                try:
                    res = await client.delete_messages(chat, batch, revoke=True)
                    deleted += sum(r.pts_count for r in res) if res else 0
                    break
                except FloodWaitError as e:
                    print(f"Telegram asked to wait {e.seconds}s...")
                    await asyncio.sleep(e.seconds + 1)
            print(f"  deleted {min(i + 100, len(ids))}/{len(ids)}")

        print(f"\nDone. Telegram confirmed {deleted} deletions.")
        print("Tip: delete tools/cleanup.session when you're finished; it keeps you logged in.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
