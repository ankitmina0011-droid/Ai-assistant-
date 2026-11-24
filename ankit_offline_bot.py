"""
Ankit Chat Automation Bot — Telegram Business "Chat Automation" ke saath
---------------------------------------------------------------------------
Ye bot Telegram ke apne "Chat Automation" feature (Settings -> Business ->
Chat Automation) me add hota hai. Wahan Telegram khud decide karta hai kab
ye bot aapki taraf se reply kare (jab aap away/busy ho) — isliye humein
khud se online/offline detect karne ki zarurat NAHI hai, na hi userbot
session (StringSession) ki.

Sirf ek normal Telegram Bot (BOT_TOKEN) chahiye, jo Gemini se AI reply
generate karke "Bot:" prefix ke saath bhejta hai.

RENDER PAR DEPLOY (FREE Web Service):
1) @BotFather se bot banao -> BOT_TOKEN lo.
2) Apni Telegram user id lo (e.g. @userinfobot se) -> OWNER_ID.
3) Render environment variables me daalo: BOT_TOKEN, GEMINI_API_KEY, OWNER_ID
4) Start command: python ankit_offline_bot.py
5) Telegram Settings -> Business -> Chat Automation me jaake apna bot
   username add karo ("All private chats except...").
6) Render free service ko sleep se bachane ke liye UptimeRobot se "/" URL
   ko har 5-10 min ping karte raho.
"""

import os
import asyncio
import threading

from flask import Flask
from telethon import TelegramClient, events

import google.generativeai as genai

# ====== ENV VARIABLES (Render dashboard me set karo) ======
API_ID = int(os.environ.get("API_ID", "0"))       # my.telegram.org se (koi bhi account se le sakte ho)
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")       # BotFather se mila token
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))   # aapki Telegram user id (control commands ke liye)
OWNER_NAME = "Ankit"
PORT = int(os.environ.get("PORT", "10000"))
CMD_PREFIX = "/"
# ============================================================

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

bot_client = TelegramClient("control_bot_session", API_ID, API_HASH)

bot_enabled = True  # /off se band, /on se chalu

# ---------- Render ko "zinda" dikhane ke liye chhota web server ----------
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Ankit chat automation bot is running."


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# --------------------------------------------------------------------------


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
    global bot_enabled

    if text.strip().lower() == "/start":
        bot_enabled = True
        await event.reply(
            f"Bot: shuru ho gaya, {OWNER_NAME}!\n\n"
            "Commands:\n"
            "/on - auto-reply chalu karo\n"
            "/off - auto-reply band karo\n"
            "/status - current status dekho\n"
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
        await event.reply(f"Bot status: {'ON' if bot_enabled else 'OFF'}")
    elif cmd == "help":
        await event.reply(
            "Commands:\n"
            "/on - auto-reply chalu karo\n"
            "/off - auto-reply band karo\n"
            "/status - current status dekho"
        )
    else:
        return False

    return True


@bot_client.on(events.NewMessage(incoming=True))
async def on_message(event):
    text = (event.raw_text or "").strip()

    # Sirf owner hi control commands chala sakta hai
    if event.sender_id == OWNER_ID:
        was_command = await handle_command(event, text)
        if was_command:
            return

    if not bot_enabled:
        return

    reply_text = await ai_reply(text)
    await event.reply(f"Bot: {reply_text}")


async def main():
    for attempt in range(5):
        try:
            await bot_client.start(bot_token=BOT_TOKEN)
            print("Bot chalu ho gaya.")
            break
        except Exception as e:
            wait = 10 * (attempt + 1)
            print(f"Bot login fail hua ({e}), {wait}s baad retry karunga...")
            await asyncio.sleep(wait)
    else:
        print("Bot start nahi ho paya 5 koshish ke baad. BOT_TOKEN check karo.")
        return

    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
