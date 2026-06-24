import os
import json
import base64
import logging
import anthropic
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

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

DATA_FILE = "fitness_data.json"

SYSTEM_PROMPT = """Ты персональный фитнес-ассистент. Твоя задача — помогать пользователю вести здоровый образ жизни.

Пользователь: мужчина 35-45 лет, цель — похудеть, новичок, тренируется 4-5 дней в неделю.
Дневная норма калорий: ~1850 ккал (дефицит для похудения).
Норма белка: ~140г в день.

Когда пользователь пишет что ел — определи калории и БЖУ и ответь в формате:
🍽 [Название блюда]
Калории: X ккал
Белки: Xг | Жиры: Xг | Углеводы: Xг

Когда присылает фото еды — определи блюдо и дай те же данные.

Когда пишет о тренировке — подтверди, похвали, дай короткий совет.

В конце каждого ответа добавляй итог дня если знаешь что уже ел сегодня.

Отвечай по-русски, кратко и дружелюбно. Используй эмодзи умеренно."""


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_key():
    return datetime.now().strftime("%Y-%m-%d")


def get_user_data(user_id: str):
    data = load_data()
    uid = str(user_id)
    today = get_today_key()
    if uid not in data:
        data[uid] = {}
    if today not in data[uid]:
        data[uid][today] = {"calories": 0, "protein": 0, "meals": [], "workouts": []}
    return data, uid, today


def save_user_day(data, uid, today, day_data):
    data[uid][today] = day_data
    save_data(data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет, Алексей! Я твой фитнес-бот.\n\n"
        "📸 Отправь фото еды — посчитаю калории\n"
        "✍️ Напиши что ел — занесу в дневник\n"
        "💪 Расскажи о тренировке — отмечу прогресс\n\n"
        "Команды:\n"
        "/stats — статистика за сегодня\n"
        "/week — итог за неделю\n"
        "/reset — сбросить данные дня\n\n"
        "Твоя цель: 1850 ккал/день 🎯"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data, uid, today = get_user_data(user_id)
    day = data[uid][today]

    cal = day["calories"]
    prot = day["protein"]
    meals = day["meals"]
    workouts = day["workouts"]
    remaining = max(0, 1850 - cal)
    pct = min(100, int(cal / 1850 * 100))

    bar_filled = int(pct / 10)
    bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    meals_text = "\n".join(f"  • {m}" for m in meals) if meals else "  Пока ничего"
    workouts_text = "\n".join(f"  🏋 {w}" for w in workouts) if workouts else "  Тренировок не было"

    text = (
        f"📊 *Статистика за сегодня* ({today})\n\n"
        f"🔥 Калории: *{cal}* / 1850 ккал\n"
        f"{bar} {pct}%\n"
        f"Осталось: *{remaining}* ккал\n\n"
        f"🥩 Белок: *{prot}г* / 140г\n\n"
        f"🍽 Приёмы пищи:\n{meals_text}\n\n"
        f"💪 Тренировки:\n{workouts_text}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def week_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data()
    uid = str(user_id)

    if uid not in data:
        await update.message.reply_text("Пока нет данных за неделю.")
        return

    lines = ["📅 *Итог за неделю:*\n"]
    total_cal = 0
    days_count = 0

    for date_key in sorted(data[uid].keys())[-7:]:
        d = data[uid][date_key]
        cal = d.get("calories", 0)
        workouts = len(d.get("workouts", []))
        total_cal += cal
        days_count += 1
        w_icon = "💪" if workouts > 0 else "😴"
        lines.append(f"{date_key}: {cal} ккал {w_icon}")

    if days_count > 0:
        avg = int(total_cal / days_count)
        lines.append(f"\nСреднее: *{avg}* ккал/день")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def reset_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data, uid, today = get_user_data(user_id)
    data[uid][today] = {"calories": 0, "protein": 0, "meals": [], "workouts": []}
    save_data(data)
    await update.message.reply_text("✅ Данные за сегодня сброшены.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    data, uid, today = get_user_data(user_id)
    day = data[uid][today]

    history_text = ""
    if day["meals"]:
        history_text = f"\n\nУже съедено сегодня: {', '.join(day['meals'])}. Итого: {day['calories']} ккал, белок: {day['protein']}г."

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT + history_text,
        messages=[{"role": "user", "content": text}]
    )

    reply = response.content[0].text

    # Parse calories and protein from response
    cal_added = 0
    prot_added = 0
    is_workout = any(word in text.lower() for word in [
        "трениров", "подход", "приседан", "отжим", "бег", "кардио",
        "упражнен", "жим", "тяга", "планка", "прыжк"
    ])

    if not is_workout:
        import re
        cal_match = re.search(r'[Кк]алори[ийе][:\s]+(\d+)', reply)
        prot_match = re.search(r'[Бб]елк[иа][:\s]+(\d+)', reply)
        if cal_match:
            cal_added = int(cal_match.group(1))
        if prot_match:
            prot_added = int(prot_match.group(1))

        if cal_added > 0:
            day["calories"] += cal_added
            day["protein"] += prot_added
            short_name = text[:40] + ("..." if len(text) > 40 else "")
            day["meals"].append(f"{short_name} ({cal_added} ккал)")
    else:
        short_name = text[:50] + ("..." if len(text) > 50 else "")
        day["workouts"].append(short_name)

    save_user_day(data, uid, today, day)

    remaining = max(0, 1850 - day["calories"])
    if cal_added > 0:
        reply += f"\n\n📊 Итого сегодня: *{day['calories']}* ккал | Осталось: *{remaining}* ккал"

    await update.message.reply_text(reply, parse_mode="Markdown")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data, uid, today = get_user_data(user_id)
    day = data[uid][today]

    await update.message.reply_text("📸 Анализирую фото...")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    image_b64 = base64.standard_b64encode(file_bytes).decode("utf-8")

    caption = update.message.caption or ""
    history_text = ""
    if day["meals"]:
        history_text = f"\n\nУже съедено сегодня: {', '.join(day['meals'])}. Итого: {day['calories']} ккал."

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT + history_text,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64
                    }
                },
                {
                    "type": "text",
                    "text": f"Что на фото? Определи блюдо и посчитай калории. {caption}"
                }
            ]
        }]
    )

    reply = response.content[0].text

    import re
    cal_match = re.search(r'[Кк]алори[ийе][:\s]+(\d+)', reply)
    prot_match = re.search(r'[Бб]елк[иа][:\s]+(\d+)', reply)
    cal_added = int(cal_match.group(1)) if cal_match else 0
    prot_added = int(prot_match.group(1)) if prot_match else 0

    if cal_added > 0:
        day["calories"] += cal_added
        day["protein"] += prot_added
        day["meals"].append(f"📸 Фото ({cal_added} ккал)")
        save_user_day(data, uid, today, day)

        remaining = max(0, 1850 - day["calories"])
        reply += f"\n\n📊 Итого сегодня: *{day['calories']}* ккал | Осталось: *{remaining}* ккал"

    await update.message.reply_text(reply, parse_mode="Markdown")


def main():
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
