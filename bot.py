import os
import base64
import logging
import re
import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Database ──────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS meals (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    date DATE NOT NULL DEFAULT CURRENT_DATE,
                    name TEXT NOT NULL,
                    calories INT DEFAULT 0,
                    protein INT DEFAULT 0,
                    fat INT DEFAULT 0,
                    carbs INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS workouts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    date DATE NOT NULL DEFAULT CURRENT_DATE,
                    description TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()

def add_meal(user_id, name, calories, protein=0, fat=0, carbs=0):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO meals (user_id, name, calories, protein, fat, carbs)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, name, calories, protein, fat, carbs))
        conn.commit()

def add_workout(user_id, description):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO workouts (user_id, description) VALUES (%s, %s)", (user_id, description))
        conn.commit()

def get_today(user_id):
    today = datetime.now().date()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, calories, protein, fat, carbs,
                       to_char(created_at, 'HH24:MI') as time
                FROM meals WHERE user_id=%s AND date=%s ORDER BY created_at
            """, (user_id, today))
            meals = [dict(m) for m in cur.fetchall()]
            cur.execute("""
                SELECT description, to_char(created_at, 'HH24:MI') as time
                FROM workouts WHERE user_id=%s AND date=%s ORDER BY created_at
            """, (user_id, today))
            workouts = [dict(w) for w in cur.fetchall()]
            cur.execute("""
                SELECT COALESCE(SUM(calories),0) as total_cal,
                       COALESCE(SUM(protein),0) as total_prot
                FROM meals WHERE user_id=%s AND date=%s
            """, (user_id, today))
            totals = cur.fetchone()
    return {
        "meals": meals,
        "workouts": workouts,
        "total_calories": int(totals["total_cal"]),
        "total_protein": int(totals["total_prot"]),
        "date": str(today)
    }

def get_week(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date::text, COALESCE(SUM(calories),0) as cal,
                       COUNT(*) as meals_count
                FROM meals
                WHERE user_id=%s AND date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY date ORDER BY date
            """, (user_id,))
            days = [dict(d) for d in cur.fetchall()]
            cur.execute("""
                SELECT date::text, COUNT(*) as count
                FROM workouts
                WHERE user_id=%s AND date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY date
            """, (user_id,))
            workout_days = {r["date"]: r["count"] for r in cur.fetchall()}
    return {"days": days, "workout_days": workout_days}

def reset_today(user_id):
    today = datetime.now().date()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM meals WHERE user_id=%s AND date=%s", (user_id, today))
            cur.execute("DELETE FROM workouts WHERE user_id=%s AND date=%s", (user_id, today))
        conn.commit()

# ── Claude ────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты персональный фитнес-ассистент. Помогаешь пользователю вести здоровый образ жизни.

Пользователь: мужчина 35-45 лет (Алексей), цель — похудеть, новичок, тренируется 4-5 дней в неделю.
Дневная норма калорий: ~1850 ккал. Норма белка: ~140г в день.

Когда пользователь пишет что ел или присылает фото еды — ОБЯЗАТЕЛЬНО отвечай СТРОГО в таком формате:
🍽 [Название блюда]
Калории: X ккал
Белки: Xг | Жиры: Xг | Углеводы: Xг
[короткий комментарий]

Когда пишет о тренировке — подтверди и похвали кратко.
Отвечай по-русски, дружелюбно и кратко."""

def parse_nutrition(text):
    cal = prot = fat = carbs = 0
    cal_m = re.search(r'[Кк]алори[ийе][:\s]+(\d+)', text)
    pro_m = re.search(r'[Бб]елк[иа][:\s]+(\d+)', text)
    fat_m = re.search(r'[Жж]ир[ыа][:\s]+(\d+)', text)
    crb_m = re.search(r'[Уу]глевод[ыа][:\s]+(\d+)', text)
    if cal_m: cal = int(cal_m.group(1))
    if pro_m: prot = int(pro_m.group(1))
    if fat_m: fat = int(fat_m.group(1))
    if crb_m: carbs = int(crb_m.group(1))
    return cal, prot, fat, carbs

def is_workout(text):
    keywords = ["трениров", "подход", "приседан", "отжим", "бег", "кардио",
                "упражнен", "жим", "тяга", "планка", "прыжк", "выпад",
                "скакалк", "растяжк", "пресс", "турник"]
    return any(w in text.lower() for w in keywords)

# ── Handlers ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dashboard = f"\n🌐 Дашборд: {DASHBOARD_URL}" if DASHBOARD_URL else ""
    await update.message.reply_text(
        f"👋 Привет, Алексей! Я твой фитнес-бот.\n\n"
        f"📸 Фото еды → посчитаю калории\n"
        f"✍️ Текст что ел → занесу в дневник\n"
        f"💪 Тренировка → отмечу прогресс\n"
        f"{dashboard}\n\n"
        f"Команды:\n"
        f"/stats — статистика за сегодня\n"
        f"/week — итог за неделю\n"
        f"/reset — сбросить данные дня\n\n"
        f"Твоя цель: 1850 ккал/день 🎯"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    day = get_today(user_id)
    cal = day["total_calories"]
    prot = day["total_protein"]
    remaining = max(0, 1850 - cal)
    pct = min(100, int(cal / 1850 * 100))
    bar = "🟩" * int(pct / 10) + "⬜" * (10 - int(pct / 10))
    meals_text = "\n".join(f"  • {m['name']} — {m['calories']} ккал" for m in day["meals"]) if day["meals"] else "  Пока ничего"
    workouts_text = "\n".join(f"  💪 {w['description'][:50]}" for w in day["workouts"]) if day["workouts"] else "  Тренировок не было"
    dashboard = f"\n\n🌐 {DASHBOARD_URL}" if DASHBOARD_URL else ""
    await update.message.reply_text(
        f"📊 *Статистика за {day['date']}*\n\n"
        f"🔥 Калории: *{cal}* / 1850 ккал\n"
        f"{bar} {pct}%\n"
        f"Осталось: *{remaining}* ккал\n\n"
        f"🥩 Белок: *{prot}г* / 140г\n\n"
        f"🍽 Приёмы пищи:\n{meals_text}\n\n"
        f"🏋 Тренировки:\n{workouts_text}{dashboard}",
        parse_mode="Markdown"
    )

async def week_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_week(user_id)
    lines = ["📅 *Итог за 7 дней:*\n"]
    total_cal = 0
    for d in data["days"]:
        date_str = str(d["date"])
        cal = int(d["cal"])
        total_cal += cal
        w_icon = "💪" if date_str in data["workout_days"] else "😴"
        lines.append(f"{date_str}: {cal} ккал {w_icon}")
    if data["days"]:
        lines.append(f"\nСреднее: *{int(total_cal/len(data['days']))}* ккал/день")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def reset_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_today(update.effective_user.id)
    await update.message.reply_text("✅ Данные за сегодня сброшены.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    day = get_today(user_id)
    history = ""
    if day["meals"]:
        eaten = ", ".join(f"{m['name']} ({m['calories']} ккал)" for m in day["meals"])
        history = f"\n\nУже съедено сегодня: {eaten}. Итого: {day['total_calories']} ккал."
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT + history,
        messages=[{"role": "user", "content": text}]
    )
    reply = response.content[0].text
    if is_workout(text):
        add_workout(user_id, text[:200])
    else:
        cal, prot, fat, carbs = parse_nutrition(reply)
        if cal > 0:
            add_meal(user_id, text[:80], cal, prot, fat, carbs)
            day = get_today(user_id)
            remaining = max(0, 1850 - day["total_calories"])
            reply += f"\n\n📊 Итого сегодня: *{day['total_calories']}* ккал | Осталось: *{remaining}* ккал"
    await update.message.reply_text(reply, parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("📸 Анализирую фото...")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    caption = update.message.caption or "Что на фото? Определи блюдо и посчитай калории."
    day = get_today(user_id)
    history = ""
    if day["meals"]:
        eaten = ", ".join(f"{m['name']} ({m['calories']} ккал)" for m in day["meals"])
        history = f"\n\nУже съедено сегодня: {eaten}. Итого: {day['total_calories']} ккал."
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT + history,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": caption}
        ]}]
    )
    reply = response.content[0].text
    cal, prot, fat, carbs = parse_nutrition(reply)
    if cal > 0:
        add_meal(user_id, "📸 Фото", cal, prot, fat, carbs)
        day = get_today(user_id)
        remaining = max(0, 1850 - day["total_calories"])
        reply += f"\n\n📊 Итого сегодня: *{day['total_calories']}* ккал | Осталось: *{remaining}* ккал"
    await update.message.reply_text(reply, parse_mode="Markdown")

def main():
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("week", week_stats))
    app.add_handler(CommandHandler("reset", reset_day))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
