import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


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
            cur.execute("""
                INSERT INTO workouts (user_id, description)
                VALUES (%s, %s)
            """, (user_id, description))
        conn.commit()


def get_today(user_id):
    today = datetime.now().date()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, calories, protein, fat, carbs, created_at
                FROM meals WHERE user_id=%s AND date=%s
                ORDER BY created_at
            """, (user_id, today))
            meals = cur.fetchall()

            cur.execute("""
                SELECT description, created_at
                FROM workouts WHERE user_id=%s AND date=%s
                ORDER BY created_at
            """, (user_id, today))
            workouts = cur.fetchall()

            cur.execute("""
                SELECT COALESCE(SUM(calories),0) as total_cal,
                       COALESCE(SUM(protein),0) as total_prot
                FROM meals WHERE user_id=%s AND date=%s
            """, (user_id, today))
            totals = cur.fetchone()

    return {
        "meals": [dict(m) for m in meals],
        "workouts": [dict(w) for w in workouts],
        "total_calories": int(totals["total_cal"]),
        "total_protein": int(totals["total_prot"]),
        "date": str(today)
    }


def get_week(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date,
                       COALESCE(SUM(calories),0) as total_cal,
                       COALESCE(SUM(protein),0) as total_prot
                FROM meals
                WHERE user_id=%s AND date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY date ORDER BY date
            """, (user_id,))
            days = cur.fetchall()

            cur.execute("""
                SELECT date, COUNT(*) as count
                FROM workouts
                WHERE user_id=%s AND date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY date
            """, (user_id,))
            workout_days = {str(r["date"]): r["count"] for r in cur.fetchall()}

    return {
        "days": [dict(d) for d in days],
        "workout_days": workout_days
    }


def reset_today(user_id):
    today = datetime.now().date()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM meals WHERE user_id=%s AND date=%s", (user_id, today))
            cur.execute("DELETE FROM workouts WHERE user_id=%s AND date=%s", (user_id, today))
        conn.commit()
