import os
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters
from groq import Groq
from supabase import create_client
from dotenv import load_dotenv
from typing import Any

load_dotenv()

# === CONFIG ===
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
LEMON_LINK: str = os.getenv("LEMON_LINK", "https://google.com")  # temporary fallback

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def get_memory(user_id: int) -> str:
    try:
        res = supabase.table("memory").select("content").eq("user_id", user_id).execute()
        return res.data[0]["content"] if res.data else ""
    except:
        return ""

async def save_memory(user_id: int, content: str) -> None:
    supabase.table("memory").upsert({"user_id": user_id, "content": content[-12000:]}).execute()

async def is_paid(user_id: int) -> bool:
    try:
        res = supabase.table("users").select("paid").eq("user_id", user_id).execute()
        return bool(res.data and res.data[0]["paid"])
    except:
        return False

async def get_messages_used(user_id: int) -> int:
    try:
        res = supabase.table("users").select("messages_used").eq("user_id", user_id).execute()
        return res.data[0]["messages_used"] if res.data else 0
    except:
        return 0

async def increment_messages(user_id: int) -> None:
    current = await get_messages_used(user_id)
    supabase.table("users").upsert({
        "user_id": user_id,
        "messages_used": current + 1,
        "paid": False
    }).execute()

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text = update.message.text or update.message.caption or "voice note"

    # Initialize new user
    if not supabase.table("users").select("user_id").eq("user_id", user_id).execute().data:
        supabase.table("users").insert({"user_id": user_id, "paid": False, "messages_used": 0}).execute()

    paid = await is_paid(user_id)
    memory = await get_memory(user_id)

    # Gentle paywall
    if not paid:
        await increment_messages(user_id)
        messages_used = await get_messages_used(user_id)

        if messages_used == 30:
            await update.message.reply_text("Bhai 30 messages already! 🔥 Tu toh pro user ban gaya 😎")
            return
        if messages_used >= 60:
            keyboard = [[InlineKeyboardButton("₹99/week – 7 Days FREE Trial", url=LEMON_LINK)]]
            await update.message.reply_text(
                "Bas kar bhai! Roz 60+ baar baat kar raha hai 😭\n"
                "Unlimited + premium badge + voice replies chahiye?\n"
                "₹99/week (7 din bilkul free trial) → click kar de 🔥",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    # Twin AI Magic
    system_prompt = f"""
You are Twin — this user's 100% personality clone.
Talk EXACTLY like them: same Hinglish, emojis, gaali, tone, sarcasm.
Past chats: {memory[-3000:]}
Never say "as an AI". Be their real twin.
    """.strip()

    completion = client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.9,
        max_tokens=800
    )

    reply = completion.choices[0].message.content

    await save_memory(user_id, f"{memory}\nUser: {text}\nTwin: {reply}")
    await update.message.reply_text(reply)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Arre bhai! Main tera Twin hoon 😎\n"
        "Voice note bhej, Hinglish mein bakchodi kar — bilkul tere jaisa bolunga!\n"
        "Pehle 60 messages FREE → phir ₹99/week (7 din free trial) 🔥"
    )

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle))

@app.post("/")
async def webhook(request: Request) -> Response:
    json_data: dict[str, Any] = await request.json()
    update = Update.de_json(json_data, application.bot)
    if update:
        await application.process_update(update)
    return Response(status_code=200)

@app.get("/")
async def health():
    return {"status": "Twin is alive and ready to bakchodi"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))