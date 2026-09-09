import os
import json
import logging
from datetime import date

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", "3"))
ADMIN_ID = os.environ.get("ADMIN_ID")  # your own Telegram user id, for /stats and manual premium grants

# Use a SEPARATE/throwaway Instagram account here, not your personal one.
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")

USAGE_FILE = "usage.json"
PREMIUM_FILE = "premium.json"


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_count(user_id):
    usage = load_json(USAGE_FILE)
    today = str(date.today())
    user_data = usage.get(str(user_id), {})
    if user_data.get("date") != today:
        return 0
    return user_data.get("count", 0)


def increment_usage(user_id):
    usage = load_json(USAGE_FILE)
    today = str(date.today())
    uid = str(user_id)
    user_data = usage.get(uid, {})
    if user_data.get("date") != today:
        user_data = {"date": today, "count": 0}
    user_data["count"] += 1
    usage[uid] = user_data
    save_json(USAGE_FILE, usage)


def is_premium(user_id):
    premium = load_json(PREMIUM_FILE)
    return str(user_id) in premium


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n\n"
        "لینک ویدیوی اینستاگرام، یوتیوب یا تیک‌تاک رو برام بفرست تا برات دانلودش کنم.\n\n"
        f"هر روز {FREE_DAILY_LIMIT} دانلود رایگان داری.\n"
        "برای دانلود نامحدود، دستور /premium رو بزن."
    )


async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "برای عضویت نامحدود (بدون محدودیت روزانه) با ادمین ربات در تماس باش:\n"
        "@m_h_moradian"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and str(update.effective_user.id) != str(ADMIN_ID):
        return
    usage = load_json(USAGE_FILE)
    premium = load_json(PREMIUM_FILE)
    today = str(date.today())
    active_today = sum(1 for u in usage.values() if u.get("date") == today)
    await update.message.reply_text(
        f"📊 آمار:\n"
        f"کاربران فعال امروز: {active_today}\n"
        f"کل کاربران ثبت‌شده: {len(usage)}\n"
        f"کاربران پرمیوم: {len(premium)}"
    )


async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: /addpremium <user_id>"""
    if ADMIN_ID and str(update.effective_user.id) != str(ADMIN_ID):
        return
    if not context.args:
        await update.message.reply_text("استفاده: /addpremium USER_ID")
        return
    target_id = context.args[0]
    premium = load_json(PREMIUM_FILE)
    premium[target_id] = {"added": str(date.today())}
    save_json(PREMIUM_FILE, premium)
    await update.message.reply_text(f"کاربر {target_id} پرمیوم شد ✅")


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text.startswith("http"):
        await update.message.reply_text("لطفاً یک لینک معتبر بفرست.")
        return

    if not is_premium(user_id):
        used = get_today_count(user_id)
        if used >= FREE_DAILY_LIMIT:
            await update.message.reply_text(
                f"سقف رایگان امروزت ({FREE_DAILY_LIMIT} دانلود) تموم شده.\n"
                "برای نامحدود /premium رو بزن، یا فردا دوباره سر بزن."
            )
            return

    status_msg = await update.message.reply_text("⏳ در حال دانلود...")

    filename = f"downloads/{user_id}_{int(date.today().strftime('%Y%m%d'))}_%(id)s.%(ext)s"
    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "format": "best[filesize<50M]/best",
        "outtmpl": filename,
        "quiet": True,
        "no_warnings": True,
    }

    if "instagram.com" in text and IG_USERNAME and IG_PASSWORD:
        ydl_opts["username"] = IG_USERNAME
        ydl_opts["password"] = IG_PASSWORD

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=True)
            filepath = ydl.prepare_filename(info)

        if not is_premium(user_id):
            increment_usage(user_id)

        await status_msg.edit_text("✅ دانلود شد، در حال ارسال...")

        with open(filepath, "rb") as f:
            await update.message.reply_video(f, caption="🎬 دانلود شد!")

        os.remove(filepath)

    except Exception as e:
        logger.error(f"Error downloading {text}: {e}")
        await status_msg.edit_text(
            "❌ نشد دانلودش کنم. ممکنه لینک خصوصی، خیلی بزرگ یا اشتباه باشه."
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("premium", premium_info))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("addpremium", add_premium))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
