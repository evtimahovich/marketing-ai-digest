#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, datetime, urllib.request, urllib.parse
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MODE = os.environ.get("MODE", "digest").strip().lower()
LANG = os.environ.get("DIGEST_LANGUAGE", "ru").strip().lower()
MODEL = os.environ.get("DIGEST_MODEL", "gemini-3.1-pro-preview").strip()
TOPIC_HINT = os.environ.get("TOPIC_HINT", "").strip()
PRIORITY_SOURCES = [s.strip() for s in os.environ.get("PRIORITY_SOURCES", "").split(",") if s.strip()]

LANG_NAME = "русском" if LANG == "ru" else "украинском" if LANG == "uk" else "русском"
NO_ALERT_TOKEN = "NO_ALERT"

def build_system_prompt():
    topic = f"Тема выпуска: {TOPIC_HINT}.\n" if TOPIC_HINT else ""
    sources = "Приоритетные источники: " + ", ".join(PRIORITY_SOURCES) + ".\n" if PRIORITY_SOURCES else ""
    return f"""Ты — шеф-редактор. Пиши на {LANG_NAME} языке, живым медиастилем (без мусора).

{topic}{sources}Правила:
- Телеграм-формат: короткие абзацы, пустая строка между блоками, жирный только <b>.
- Никаких блоков/фраз «Зачем это вам/нам» и никакой мотивационной воды.
- «Пруфы:» — только URL, каждый на новой строке, без подписей.

Структура: 🤖 <b>AI-ролики</b> → 🔥 <b>Залетело</b> (по регионам, если есть) → 🧠 <b>Кейс дня</b> → 🧯 <b>Инструменты</b> → 💡 <b>На пробу</b>.
"""

def build_user_prompt():
    today = datetime.date.today().strftime("%d.%m.%Y")
    if MODE == "alert":
        focus = TOPIC_HINT or "маркетинг и AI-контент"
        return f"""Сегодня {today}. Проверь последние ~12 часов по теме: {focus}.
Если ничего важного — верни {NO_ALERT_TOKEN}."""
    focus = TOPIC_HINT or "маркетинг, AI-реклама и автоматизации в бизнесе"
    sources_hint = ""
    if PRIORITY_SOURCES:
        sites = " OR ".join(f"site:{d}" for d in PRIORITY_SOURCES)
        sources_hint = f"\nСделай отдельные запросы по приоритетным источникам (например: {sites})."
    return f"""Сегодня {today}. Собери дайджест по структуре. Сначала веб-поиск, потом текст.
Фокус: {focus}.{sources_hint}"""

def generate_digest():
    client = genai.Client(api_key=GEMINI_API_KEY)
    tools = [types.Tool(google_search=types.GoogleSearch()), types.Tool(url_context=types.UrlContext())]
    config = types.GenerateContentConfig(system_instruction=build_system_prompt(), tools=tools)
    resp = client.models.generate_content(model=MODEL, contents=build_user_prompt(), config=config)
    return (resp.text or "").strip()

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "true", "parse_mode": "HTML"}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    urllib.request.urlopen(req, timeout=30).read()

def main():
    missing = [k for k in ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(k)]
    if missing:
        print("Missing env: " + ", ".join(missing), file=sys.stderr)
        return 1

    digest = generate_digest()
    if MODE == "alert" and (not digest or NO_ALERT_TOKEN in digest):
        print("No alert.")
        return 0
    if not digest:
        print("Empty digest.", file=sys.stderr)
        return 1

    send_to_telegram(digest)
    print("Sent.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
