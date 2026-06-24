# 🏋 Фитнес-бот v2 — с базой данных и веб-дашбордом

## Структура проекта
```
fitness_bot_v2/
├── bot.py          — Telegram бот
├── dashboard.py    — Веб-дашборд
├── database.py     — Работа с PostgreSQL
├── requirements.txt
├── Procfile        — Запуск на Railway
└── README.md
```

## Деплой на Railway

### Шаг 1 — Загрузите файлы в GitHub репозиторий
Замените старые файлы новыми (bot.py, requirements.txt) и добавьте новые (dashboard.py, database.py, Procfile).

### Шаг 2 — Добавьте PostgreSQL базу данных
1. В Railway нажмите "+ Add" → "Database" → "PostgreSQL"
2. Railway автоматически добавит переменную DATABASE_URL

### Шаг 3 — Переменные окружения (Variables)
Добавьте в сервис fitnes-bot:
```
TELEGRAM_TOKEN = ваш_токен
ANTHROPIC_API_KEY = sk-ant-...
TELEGRAM_USER_ID = ваш_id_в_телеграме (узнайте у @userinfobot)
DASHBOARD_URL = URL вашего дашборда (появится после деплоя)
```

### Шаг 4 — После деплоя
Railway даст вам URL вида: https://fitnes-bot-xxx.railway.app
Это и есть ваш дашборд — открывайте с телефона в любой момент!

## Как пользоваться

**Telegram бот:**
- Фото еды → калории
- "Съел гречку 200г и курицу 150г" → БЖУ
- "Сделал 3 подхода приседаний" → тренировка
- /stats — итог дня
- /week — неделя

**Дашборд (сайт):**
- Обновляется каждые 30 секунд автоматически
- График калорий за неделю
- Список всех приёмов пищи с временем
- БЖУ за день
