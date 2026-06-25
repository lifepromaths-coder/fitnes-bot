import os
from datetime import datetime
from flask import Flask, jsonify, render_template_string
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
                           to_char(created_at AT TIME ZONE 'Asia/Almaty', 'HH24:MI') as time
                    FROM meals WHERE user_id=%s AND date=%s ORDER BY created_at
                """, (USER_ID, today))
                meals = [dict(r) for r in cur.fetchall()]
                cur.execute("""
                    SELECT description,
                           to_char(created_at AT TIME ZONE 'Asia/Almaty', 'HH24:MI') as time
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
                return [dict(r) for r in cur.fetchall()]
    except:
        return []

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>💪 Фитнес дашборд</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#f5f5f7; color:#1d1d1f; }
.header { background:#fff; padding:16px 20px; border-bottom:1px solid #e5e5ea; display:flex; justify-content:space-between; align-items:center; position:sticky; top:0; z-index:10; box-shadow:0 1px 3px rgba(0,0,0,0.08); }
.header h1 { font-size:18px; font-weight:600; }
.refresh-btn { background:#007aff; color:#fff; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:14px; font-weight:500; }
.container { max-width:800px; margin:0 auto; padding:16px; }
.date-label { font-size:13px; color:#86868b; margin:8px 0 14px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
.card { background:#fff; border-radius:16px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.card-label { font-size:12px; color:#86868b; margin-bottom:4px; }
.card-value { font-size:26px; font-weight:600; line-height:1; }
.card-sub { font-size:11px; color:#86868b; margin-top:3px; }
.blue { color:#007aff; } .green { color:#34c759; } .orange { color:#ff9500; } .red { color:#ff3b30; }
.prog-bg { height:6px; background:#f0f0f0; border-radius:99px; overflow:hidden; margin:8px 0 4px; }
.prog-fill { height:100%; border-radius:99px; transition:width .5s; }
.macro-row { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:14px; }
.macro-card { background:#fff; border-radius:12px; padding:12px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.macro-val { font-size:20px; font-weight:600; }
.macro-label { font-size:11px; color:#86868b; margin-top:2px; }
.chart-card { background:#fff; border-radius:16px; padding:16px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.section-title { font-size:15px; font-weight:600; margin:14px 0 8px; }
.meal-item { background:#fff; border-radius:12px; padding:12px 14px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.meal-name { font-size:14px; font-weight:500; }
.meal-meta { font-size:11px; color:#86868b; margin-top:2px; }
.meal-cal { font-size:17px; font-weight:600; color:#007aff; }
.workout-item { background:#fff; border-radius:12px; padding:12px 14px; margin-bottom:6px; display:flex; gap:10px; align-items:center; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.workout-text { font-size:14px; }
.workout-time { font-size:11px; color:#86868b; margin-top:2px; }
.empty { text-align:center; color:#86868b; padding:20px; font-size:14px; background:#fff; border-radius:12px; }
.last-upd { text-align:center; font-size:11px; color:#86868b; padding:16px 0 8px; }
.auto-badge { display:inline-block; background:#e8f5e9; color:#2e7d32; font-size:11px; padding:2px 8px; border-radius:99px; margin-left:8px; }
</style>
</head>
<body>
<div class="header">
  <h1>💪 Фитнес дашборд <span class="auto-badge">● Live</span></h1>
  <button class="refresh-btn" onclick="loadData()">↻ Обновить</button>
</div>
<div class="container">
  <div id="content"><div class="empty">Загрузка...</div></div>
</div>
<script>
const GOAL_CAL = 1850, GOAL_PROT = 140;
let weekChart = null;

function pct(v, g) { return Math.min(100, Math.round(v/g*100)); }
function barColor(p) { return p>=100?'#ff3b30':p>=85?'#ff9500':'#34c759'; }

function render(data) {
  const t = data.totals;
  const cal=parseInt(t.cal)||0, prot=parseInt(t.prot)||0;
  const fat=parseInt(t.fat)||0, carbs=parseInt(t.carbs)||0;
  const rem = Math.max(0, GOAL_CAL-cal);
  const cp = pct(cal,GOAL_CAL), pp = pct(prot,GOAL_PROT);

  const mealsHtml = data.meals.length ? data.meals.map(m=>`
    <div class="meal-item">
      <div>
        <div class="meal-name">${m.name}</div>
        <div class="meal-meta">${m.time} · Б:${m.protein}г Ж:${m.fat}г У:${m.carbs}г</div>
      </div>
      <div class="meal-cal">${m.calories}</div>
    </div>`).join('') : '<div class="empty">Ещё ничего не добавлено</div>';

  const workoutsHtml = data.workouts.length ? data.workouts.map(w=>`
    <div class="workout-item">
      <div style="font-size:20px">🏋</div>
      <div>
        <div class="workout-text">${w.description}</div>
        <div class="workout-time">${w.time}</div>
      </div>
    </div>`).join('') : '<div class="empty">Тренировок не было</div>';

  document.getElementById('content').innerHTML = `
    <div class="date-label">📅 ${data.date}</div>
    <div class="grid">
      <div class="card">
        <div class="card-label">Калории</div>
        <div class="card-value blue">${cal}</div>
        <div class="card-sub">из ${GOAL_CAL} ккал</div>
        <div class="prog-bg"><div class="prog-fill" style="width:${cp}%;background:${barColor(cp)}"></div></div>
        <div class="card-sub">${cp}% от цели</div>
      </div>
      <div class="card">
        <div class="card-label">Осталось</div>
        <div class="card-value ${rem===0?'red':'green'}">${rem}</div>
        <div class="card-sub">ккал до цели</div>
      </div>
      <div class="card">
        <div class="card-label">Белок</div>
        <div class="card-value orange">${prot}г</div>
        <div class="card-sub">из ${GOAL_PROT}г</div>
        <div class="prog-bg"><div class="prog-fill" style="width:${pp}%;background:#ff9500"></div></div>
        <div class="card-sub">${pp}% от нормы</div>
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
      <canvas id="weekChart" height="150"></canvas>
    </div>
    <div class="section-title">🍽 Приёмы пищи</div>
    ${mealsHtml}
    <div class="section-title">💪 Тренировки</div>
    ${workoutsHtml}
    <div class="last-upd">Обновлено: ${new Date().toLocaleTimeString('ru')}</div>
  `;

  fetch('/api/week').then(r=>r.json()).then(week=>{
    const labels = week.map(d=>d.date.slice(5));
    const values = week.map(d=>parseInt(d.cal)||0);
    const ctx = document.getElementById('weekChart').getContext('2d');
    if(weekChart) weekChart.destroy();
    weekChart = new Chart(ctx,{
      type:'bar',
      data:{labels,datasets:[{data:values,backgroundColor:values.map(v=>v>GOAL_CAL?'#ff3b30':'#007aff'),borderRadius:6}]},
      options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#f0f0f0'}},x:{grid:{display:false}}}}
    });
  });
}

function loadData() {
  fetch('/api/today').then(r=>r.json()).then(render)
    .catch(()=>{ document.getElementById('content').innerHTML='<div class="empty">Ошибка загрузки</div>'; });
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
