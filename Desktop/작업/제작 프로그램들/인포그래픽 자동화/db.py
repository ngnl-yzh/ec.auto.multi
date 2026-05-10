import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            name TEXT NOT NULL,
            layout_type TEXT NOT NULL,
            section_structure JSONB NOT NULL,
            color_theme TEXT NOT NULL DEFAULT 'blue',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS infographic_history (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            template_id INTEGER REFERENCES templates(id),
            input_text TEXT,
            data_json JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def save_template(name: str, layout_type: str, section_structure: dict, color_theme: str, user_id: str = "default") -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO templates (user_id, name, layout_type, section_structure, color_theme) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, name, layout_type, json.dumps(section_structure, ensure_ascii=False), color_theme)
    )
    template_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return template_id


def load_templates(user_id: str = "default") -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM templates WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def save_history(input_text: str, data_json: dict, template_id: int = None, user_id: str = "default"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO infographic_history (user_id, template_id, input_text, data_json) VALUES (%s, %s, %s, %s)",
        (user_id, template_id, input_text, json.dumps(data_json, ensure_ascii=False))
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_template(template_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM templates WHERE id = %s", (template_id,))
    conn.commit()
    cur.close()
    conn.close()
