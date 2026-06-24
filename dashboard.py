import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")
USER_ID = os.getenv("TELEGRAM_USER_ID", "0")

GOAL_CAL = 1850
GOAL_PROT = 140


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def get_today_data():
    today = datetime.now().date()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name, calories, protein, fat, carbs,
                           to_char(created_at, 'HH24:MI') as time
                    FROM meals WHERE user_id=%s AND date=%s ORDER BY created_at
                """, (USER_ID, today))
                meals = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT description, to_char(created_at, 'HH24:MI') as time
                    FROM workouts WHERE user_id=%s AND date=%s ORDER BY created_at
                """, (USER_ID, today))
                workouts = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT COALESCE(SUM(calories),0) as cal,
                           COALESCE(SUM(protein),0) as prot,
                           COALESCE(SUM(fat),0) as fat,
                           COALESCE(SUM(carbs),0) as carbs
                    FROM meals WHERE user_id=%s AND date=%s
                """, (USER_ID, today))
                totals = dict(cur.fetchone())
        return {"meals": meals, "workouts": workouts, "totals": totals, "date": str(today)}
    except Exception as e:
        return {"meals": [], "workouts": [], "totals": {"cal":0,"prot":0,"fat":0,"carbs":0}, "date": str(today), "error": str(e)}


def get_week_data():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT date::text, COALESCE(SUM(calories),0) as cal
                    FROM meals WHERE user_id=%s AND date >= CURRENT_DATE - INTERVAL '6 days'
                    GROUP BY date ORDER BY date
                """, (USER_ID,))
                rows = [dict(r) for r in cur.fetchall()]
        return rows
    except:
        return []


HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Фитнес дашборд</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f5f5f7; color:#1d1d1f; }
.header { background:#fff; padding:16px 20px; border-bottom:1px solid #e5e5ea; display:flex; justify-content:space-between; align-items:center; position:sticky; top:0; z-index:10; }
.header h1 { font-size:18px; font-weight:600; }
.refresh-btn { background:#007aff; color:#fff; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:14px; }
.container { max-width:800px; margin:0 auto; padding:16px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px,1fr)); gap:12px; margin-bottom:16px; }
.card { background:#fff; border-radius:16px; padding:16px; }
.card-label { font-size:12px; color:#86868b; margin-bottom:4px; }
.card-value { font-size:28px; font-weight:600; }
.card-sub { font-size:12px; color:#86868b; margin-top:2px; }
.blue { color:#007aff; }
.green { color:#34c759; }
.orange { color:#ff9500; }
.red { color:#ff3b30; }
.progress-wrap { margin:4px 0 8px; }
.progress-bg { height:8px; background:#f5f5f7; border-radius:99px; overflow:hidden; }
.progress-fill { height:100%; border-radius:99px; transition:width 0.5s; }
.section-title { font-size:16px; font-weight:600; margin:16px 0 8px; }
.meal-item { background:#fff; border-radius:12px; padding:12px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.meal-name { font-size:14px; font-weight:500; }
.meal-time { font-size:12px; color:#86868b; margin-top:2px; }
.meal-cal { font-size:16px; font-weight:600; color:#007aff; }
.workout-item { background:#fff; border-radius:12px; padding:12px 16px; margin-bottom:8px; display:flex; gap:10px; align-items:center; }
.workout-icon { font-size:20px; }
.workout-text { font-size:14px; }
.workout-time { font-size:12px; color:#86868b; margin-top:2px; }
.chart-card { background:#fff; border-radius:16px; padding:16px; margin-bottom:16px; }
.empty { text-align:center; color:#86868b; padding:24px; font-size:14px; }
.macro-row { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:16px; }
.macro-card { background:#fff; border-radius:12px; padding:12px; text-align:center; }
.macro-val { font-size:20px; font-weight:600; }
.macro-label { font-size:11px; color:#86868b; margin-top:2px; }
.last-updated { text-align:center; font-size:12px; color:#86868b; padding:8px; }
</style>
</head>
<body>
<div class="header">
  <h1>💪 Фитнес дашборд</h1>
  <button class="refresh-btn" onclick="loadData()">Обновить</button>
</div>
<div class="container">
  <div id="content">Загрузка...</div>
</div>
<script>
const GOAL_CAL = 1850;
const GOAL_PROT = 140;
let weekChart = null;

function pct(val, goal) { return Math.min(100, Math.round(val/goal*100)); }

function barColor(p) {
  if(p >= 100) return '#ff3b30';
  if(p >= 85) return '#ff9500';
  return '#34c759';
}

function render(data) {
  const t = data.totals;
  const cal = parseInt(t.cal)||0;
  const prot = parseInt(t.prot)||0;
  const fat = parseInt(t.fat)||0;
  const carbs = parseInt(t.carbs)||0;
  const remaining = Math.max(0, GOAL_CAL - cal);
  const calPct = pct(cal, GOAL_CAL);
  const protPct = pct(prot, GOAL_PROT);

  let mealsHtml = data.meals.length ? data.meals.map(m => `
    <div class="meal-item">
      <div>
        <div class="meal-name">${m.name}</div>
        <div class="meal-time">${m.time} · Б:${m.protein}г Ж:${m.fat}г У:${m.carbs}г</div>
      </div>
      <div class="meal-cal">${m.calories}</div>
    </div>`).join('') : '<div class="empty">Ещё ничего не добавлено</div>';

  let workoutsHtml = data.workouts.length ? data.workouts.map(w => `
    <div class="workout-item">
      <div class="workout-icon">🏋</div>
      <div>
        <div class="workout-text">${w.description}</div>
        <div class="workout-time">${w.time}</div>
      </div>
    </div>`).join('') : '<div class="empty">Тренировок не было</div>';

  document.getElementById('content').innerHTML = `
    <div style="font-size:13px;color:#86868b;margin:8px 0 12px;">${data.date}</div>
    <div class="grid">
      <div class="card">
        <div class="card-label">Калории</div>
        <div class="card-value blue">${cal}</div>
        <div class="card-sub">из ${GOAL_CAL} ккал</div>
        <div class="progress-wrap">
          <div class="progress-bg"><div class="progress-fill" style="width:${calPct}%;background:${barColor(calPct)};"></div></div>
        </div>
        <div class="card-sub">${calPct}%</div>
      </div>
      <div class="card">
        <div class="card-label">Осталось</div>
        <div class="card-value ${remaining===0?'red':'green'}">${remaining}</div>
        <div class="card-sub">ккал до цели</div>
      </div>
      <div class="card">
        <div class="card-label">Белок</div>
        <div class="card-value orange">${prot}г</div>
        <div class="card-sub">из ${GOAL_PROT}г</div>
        <div class="progress-wrap">
          <div class="progress-bg"><div class="progress-fill" style="width:${protPct}%;background:#ff9500;"></div></div>
        </div>
      </div>
      <div class="card">
        <div class="card-label">Тренировки</div>
        <div class="card-value">${data.workouts.length}</div>
        <div class="card-sub">за сегодня</div>
      </div>
    </div>

    <div class="macro-row">
      <div class="macro-card"><div class="macro-val blue">${prot}г</div><div class="macro-label">Белки</div></div>
      <div class="macro-card"><div class="macro-val orange">${fat}г</div><div class="macro-label">Жиры</div></div>
      <div class="macro-card"><div class="macro-val green">${carbs}г</div><div class="macro-label">Углеводы</div></div>
    </div>

    <div class="chart-card">
      <div style="font-size:15px;font-weight:600;margin-bottom:12px;">📈 Калории за неделю</div>
      <canvas id="weekChart" height="160"></canvas>
    </div>

    <div class="section-title">🍽 Приёмы пищи</div>
    ${mealsHtml}

    <div class="section-title">💪 Тренировки</div>
    ${workoutsHtml}

    <div class="last-updated">Обновлено: ${new Date().toLocaleTimeString('ru')}</div>
  `;

  // Draw chart
  fetch('/api/week').then(r=>r.json()).then(week => {
    const labels = week.map(d => d.date.slice(5));
    const values = week.map(d => parseInt(d.cal)||0);
    const ctx = document.getElementById('weekChart').getContext('2d');
    if(weekChart) weekChart.destroy();
    weekChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: values.map(v => v > GOAL_CAL ? '#ff3b30' : '#007aff'),
          borderRadius: 6
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f0f0f0' } },
          x: { grid: { display: false } }
        }
      }
    });
  });
}

function loadData() {
  fetch('/api/today').then(r=>r.json()).then(render).catch(e => {
    document.getElementById('content').innerHTML = '<div class="empty">Ошибка загрузки данных</div>';
  });
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>"""


@app.route("/")
def dashboard():
    return render_template_string(HTML)


@app.route("/api/today")
def api_today():
    return jsonify(get_today_data())


@app.route("/api/week")
def api_week():
    return jsonify(get_week_data())


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
