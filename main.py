import os
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters
from groq import Groq
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# CONFIG
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LEMON_LINK = os.getenv("LEMON_LINK", "https://google.com")

# Clients
groq_client = Groq(api_key=GROQ_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()
application = None  # Will be created once

# Simple memory & paywall
async def save_memory(user_id: int, text: str):
    supabase.table("memory").upsert({"user_id": user_id, "content": text[-10000:]}).execute()

async def get_memory(user_id: int) -> str:
    try:
        res = supabase.table("memory").select("content").eq("user_id", user_id).execute()
        return res.data[0]["content"] if res.data else ""
    except:
        return ""

async def increment_msg(user_id: int):
    current = supabase.table("users").select("msgs").eq("user_id", user_id).execute()
    msgs = (current.data[0]["msgs"] if current.data else 0) + 1
    supabase.table("users").upsert({"user_id": user_id, "msgs": msgs}).execute()
    return msgs

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or "voice"

    # Init user
    if not supabase.table("users").select("user_id").eq("user_id", user_id).execute().data:
        supabase.table("users").insert({"user_id": user_id, "msgs": 0}).execute()

    msgs = await increment_msg(user_id)
    if msgs == 30:
        await update.message.reply_text("Bhai 30 messages ho gaye! 🔥")
        return
    if msgs >= 60:
        keyboard = [[InlineKeyboardButton("₹99/week – 7 Days FREE", url=LEMON_LINK)]]
        await update.message.reply_text("Bas kar bhai! Unlimited chahiye?\n₹99/week (7 din FREE trial)", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    memory = await get_memory(user_id)
    prompt = f"""You are Twin — exact clone of this user.
Talk 100% like them: same Hinglish, emojis, tone.
Past: {memory[-2500:]}
User says: {text}
Reply in their style only."""

    reply = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        temperature=0.9,
        max_tokens=600
    ).choices[0].message.content

    await save_memory(user_id, f"{memory}\nUser: {text}\nTwin: {reply}")
    await update.message.reply_text(reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Arre bhai! Main tera Twin hoon 😎\nJo bolega bilkul waise hi bolunga!\nPehle 60 messages FREE 🔥")

# WEBHOOK — 100% WORKING FOR RENDER
@app.post("/")
async def webhook(request: Request):
    global application
    if application is None:
        application = await Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle))

    data = await request.json()
    update = Update.de_json(data, application.bot)
    if update:
        await application.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def root():
    return {"status": "Twin is LIVE!"}

# Local only
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)