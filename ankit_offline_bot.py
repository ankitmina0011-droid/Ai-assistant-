"""
Ankit Offline Auto-Reply Userbot — Render (free) ke liye
-----------------------------------------------------------
- Telethon (free) + Google Gemini (free tier) use karta hai.
- Aapke hi Telegram account (userbot) se connect hota hai.
- Jab aap offline/inactive ho to DM ka AI se reply deta hai, "Bot:" prefix ke saath.
- Jaise hi aap khud kisi ko manually message bhejte ho, bot samajh jata hai aap online ho.

RENDER PAR DEPLOY (FREE Web Service):
1) generate_session.py apne computer/Termux me ek baar chalao -> SESSION_STRING milega.
2) Render.com par "New -> Web Service" banao, ye repo/files connect karo.
3) Environment variables me daalo:
     API_ID
     API_HASH
     GEMINI_API_KEY
     SESSION_STRING
4) Start command: python ankit_offline_bot.py
5) Render free web service ko "sleep" se bachane ke liye ek uptime pinger
   (jaise UptimeRobot, free hai) is bot ke URL (/) ko har 10 min me ping karte rehna.
"""

import os
import asyncio
import time
import threading

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

import google.generativeai as genai

# ====== ENV VARIABLES (Render dashboard me set karo) ======
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")       # BotFather se mila token (control bot)
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))   # aapki Telegram user id (sirf aap control kar sako)
OWNER_NAME = "Ankit"
PORT = int(os.environ.get("PORT", "10000"))
# ============================================================

OFFLINE_AFTER_SECONDS = 120   # itni der manual activity na ho to "offline" maano
ONLINE_NOTICE_GAP = 180       # 3 min se zyada gap ke baad reply aaye to "online" notice
CMD_PREFIX = "/"              # Saved Messages me command bhejne ka prefix

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient("control_bot_session", API_ID, API_HASH)  # control bot (BOT_TOKEN se login)

chat_state = {}  # chat_id -> {"active": bool, "last_bot_reply": float}
last_manual_activity = time.time()
bot_enabled = True   # .off se poora bot band, .on se wapas chalu
my_id = None          # client.start() ke baad fill hoga (Saved Messages pehchanne ke liye)

# ---------- Render ko "zinda" dikhane ke liye chhota web server ----------
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Ankit offline auto-reply bot is running."


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# --------------------------------------------------------------------------


def is_offline() -> bool:
    return (time.time() - last_manual_activity) > OFFLINE_AFTER_SECONDS


async def ai_reply(user_text: str) -> str:
    prompt = (
        f"Tum {OWNER_NAME} ki taraf se casual, friendly Hinglish me chat kar rahe ho. "
        f"Normal insaan jaisa short reply do, robot jaisa mat lagna.\n\n"
        f"Doosre insaan ka message: {user_text}"
    )
    try:
        resp = await asyncio.to_thread(model.generate_content, prompt)
        return resp.text.strip()
    except Exception:
        return "abhi thoda busy hu, thodi der me baat karta hu."


async def handle_command(event, text: str) -> bool:
    """Saved Messages (khud ko bheja message) me commands handle karta hai.
    True return kare to iska matlab command tha, aage kuch aur nahi hoga."""
    global bot_enabled, OFFLINE_AFTER_SECONDS, ONLINE_NOTICE_GAP

    if text.strip().lower() == "/start":
        bot_enabled = True
        await event.reply(
            f"Bot: shuru ho gaya, {OWNER_NAME}!\n\n"
            "Commands (Saved Messages me bhejo):\n"
            "/on - auto-reply chalu karo\n"
            "/off - auto-reply band karo\n"
            "/status - current status dekho\n"
            "/setoffline <seconds> - offline-timeout badlo\n"
            "/setonlinegap <seconds> - online-notice-gap badlo\n"
            "/reset - saari chat states reset karo\n"
            "/help - ye list dobara dekho"
        )
        return True

    if not text.startswith(CMD_PREFIX):
        return False

    cmd_parts = text[len(CMD_PREFIX):].strip().split()
    if not cmd_parts:
        return False
    cmd = cmd_parts[0].lower()

    if cmd == "on":
        bot_enabled = True
        await event.reply("Bot: auto-reply ON kar diya.")
    elif cmd == "off":
        bot_enabled = False
        await event.reply("Bot: auto-reply OFF kar diya.")
    elif cmd == "status":
        state_txt = "ON" if bot_enabled else "OFF"
        offline_txt = "haan" if is_offline() else "nahi"
        active_chats = sum(1 for s in chat_state.values() if s.get("active"))
        await event.reply(
            f"Bot status: {state_txt}\n"
            f"Abhi offline mode: {offline_txt}\n"
            f"Active auto-reply chats: {active_chats}"
        )
    elif cmd == "setoffline" and len(cmd_parts) > 1 and cmd_parts[1].isdigit():
        OFFLINE_AFTER_SECONDS = int(cmd_parts[1])
        await event.reply(f"Bot: offline-timeout {OFFLINE_AFTER_SECONDS} sec set kar diya.")
    elif cmd == "setonlinegap" and len(cmd_parts) > 1 and cmd_parts[1].isdigit():
        ONLINE_NOTICE_GAP = int(cmd_parts[1])
        await event.reply(f"Bot: online-notice-gap {ONLINE_NOTICE_GAP} sec set kar diya.")
    elif cmd == "reset":
        chat_state.clear()
        await event.reply("Bot: saari chat states reset kar di.")
    elif cmd == "help":
        await event.reply(
            "Bot commands (Saved Messages me bhejo):\n"
            "/on - auto-reply chalu karo\n"
            "/off - auto-reply band karo\n"
            "/status - current status dekho\n"
            "/setoffline <seconds> - offline-timeout badlo\n"
            "/setonlinegap <seconds> - online-notice-gap badlo\n"
            "/reset - saari chat states reset karo"
        )
    else:
        return False

    return True


@bot_client.on(events.NewMessage(incoming=True))
async def on_control_bot_message(event):
    """Control bot (BotFather bot) ki DM se commands handle karta hai.
    Sirf OWNER_ID wala insaan hi control kar sakta hai."""
    if event.sender_id != OWNER_ID:
        await event.reply("Ye bot sirf owner control kar sakta hai.")
        return

    text = (event.raw_text or "").strip()
    was_command = await handle_command(event, text)
    if not was_command:
        await event.reply("Pehchana nahi. /help bhejo commands dekhne ke liye.")


@client.on(events.NewMessage(outgoing=True))
async def on_my_message(event):
    global last_manual_activity
    if getattr(event.message, "_sent_by_bot_script", False):
        return

    # Saved Messages (apne aap ko bheja gaya message) control-commands ke liye hai
    if event.chat_id == my_id:
        was_command = await handle_command(event, event.raw_text or "")
        if was_command:
            return

    last_manual_activity = time.time()

    chat_id = event.chat_id
    state = chat_state.get(chat_id)
    if state and state.get("active"):
        state["active"] = False
        msg = await client.send_message(chat_id, f"Bot: {OWNER_NAME} online hai.")
        msg._sent_by_bot_script = True


@client.on(events.NewMessage(incoming=True))
async def on_incoming(event):
    if not event.is_private or not bot_enabled:
        return

    chat_id = event.chat_id
    state = chat_state.setdefault(chat_id, {"active": False, "last_bot_reply": 0})

    if not is_offline():
        return

    gap = time.time() - state["last_bot_reply"]

    if not state["active"]:
        intro = (
            f"Bot: {OWNER_NAME} offline hai. "
            f"Vo jaldi online aayenge aur aapke message ka reply denge. "
            f"Aap kis baare me baat karna chahte ho?"
        )
        msg = await client.send_message(chat_id, intro)
        msg._sent_by_bot_script = True
        state["active"] = True
        state["last_bot_reply"] = time.time()
        return

    if gap > ONLINE_NOTICE_GAP and not is_offline():
        notice = await client.send_message(chat_id, f"Bot: {OWNER_NAME} online hai.")
        notice._sent_by_bot_script = True
        state["active"] = False
        return

    reply_text = await ai_reply(event.raw_text or "")
    msg = await client.send_message(chat_id, f"Bot: {reply_text}")
    msg._sent_by_bot_script = True
    state["last_bot_reply"] = time.time()


async def main():
    global my_id
    await client.start()
    me = await client.get_me()
    my_id = me.id

    if BOT_TOKEN:
        for attempt in range(5):
            try:
                await bot_client.start(bot_token=BOT_TOKEN)
                print("Control bot bhi chalu ho gaya.")
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"Control bot login fail hua ({e}), {wait}s baad retry karunga...")
                await asyncio.sleep(wait)
        else:
            print("Control bot start nahi ho paya 5 koshish ke baad. BOT_TOKEN check karo.")

    print("Ankit offline auto-reply bot chal raha hai...")
    await asyncio.gather(
        client.run_until_disconnected(),
        bot_client.run_until_disconnected() if BOT_TOKEN else asyncio.sleep(0),
    )


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
