#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Маркетинговый AI-дайджест → Telegram.

Что делает:
  1. Сам ходит в интернет (через граундинг Google Search в Gemini),
     ищет залёты рекламы и AI-роликов по регионам + новости инструментов.
  2. Пишет дайджест живым редакторским голосом (а не сухим списком).
  3. Кидает готовый текст тебе в Telegram.

Два режима (env-переменная MODE):
  - "digest"  — ежедневный выпуск (полный).
  - "alert"   — проверка горящих новостей; шлёт сообщение ТОЛЬКО если
                реально вышло что-то важное, иначе молчит.

Запускается по расписанию (GitHub Actions / cron).
"""

import os
import sys
import datetime
import urllib.request
import urllib.parse
import json

# ----------------------------------------------------------------------------
# Конфиг из переменных окружения (ключи задаются один раз)
# ----------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MODE = os.environ.get("MODE", "digest").strip().lower()          # digest | alert
LANG = os.environ.get("DIGEST_LANGUAGE", "ru").strip().lower()   # ru | uk
MODEL = os.environ.get("DIGEST_MODEL", "gemini-3.1-pro-preview")

# Сентинел: если в режиме alert ничего важного нет — модель вернёт это слово,
# и мы просто не отправляем сообщение.
NO_ALERT_TOKEN = "NO_ALERT"

LANG_NAME = {"ru": "русском", "uk": "украинском"}.get(LANG, "русском")

# Приоритетные источники: агент проверяет их в первую очередь (запросами site:domain),
# но НЕ ограничивается только ими — мир/регионы тянет и из остальной сети.
# Дописывай новые домены сюда или через переменную окружения PRIORITY_SOURCES
# (через запятую). Без https:// и без www — просто домен.
_default_sources = "mmr.ua"
PRIORITY_SOURCES = [
    s.strip().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    for s in os.environ.get("PRIORITY_SOURCES", _default_sources).split(",")
    if s.strip()
]


# ----------------------------------------------------------------------------
# Редакторский бриф — это «душа» дайджеста. Меняешь тут — меняется тон.
# ----------------------------------------------------------------------------
def build_system_prompt() -> str:
    sources_line = ", ".join(PRIORITY_SOURCES) if PRIORITY_SOURCES else "(не заданы)"
    return f"""Ты — шеф-редактор ежедневного маркетингового дайджеста для креативного
агентства, которое делает контент через AI (SMM, сайты, рекламные ролики) и
растёт в сторону полноценного маркетингового агентства.

РЫНКИ, которые важны команде: СНГ и Украина (ядро), Азия и Европа (растут),
плюс мировые тренды. Профильный приоритет — AI-ролики и AI-реклама.

ГОЛОС И СТИЛЬ (это критично):
- Пиши как сильное профильное медиа о рекламе (в духе Marketing Media Review):
  с характером, мнением, лёгкой дерзостью. Это НОВОСТЬ, которую хочется
  переслать в рабочий чат, а не отчёт.
- Веди через историю и хук, а не через «пункт раз, пункт два».
- Никакого корпоративного и сухого тона. Никакой воды и «AI slop».
- Каждый блок заканчивай короткой мыслью «зачем это вам» — что украсть,
  что попробовать, чего не делать.
- Пиши на {LANG_NAME} языке.

ЖЁСТКИЕ ПРАВИЛА ДОСТОВЕРНОСТИ:
- Бери только реальные, проверяемые факты из свежих результатов поиска
  (за последние ~24–48 часов для ежедневного выпуска). Ничего не выдумывай.
- Если по какому-то блоку за сегодня нет ничего стоящего — ПРОСТО ОПУСТИ блок,
  не придумывай наполнение ради галочки. Лучше короче, но по делу.
- В конце добавь 2–4 ссылки-пруфа на источники (раздел «Пруфы:»).

ПРИОРИТЕТНЫЕ ИСТОЧНИКИ:
- В ПЕРВУЮ очередь проверь эти сайты адресными запросами вида «site:домен»
  и при прочих равных отдавай предпочтение их материалам: {sources_line}.
- Это не ограничение: мировые и региональные залёты тяни и из остальной сети,
  если там есть что-то ярче и свежее.

СТРУКТУРА ВЫПУСКА (используй эмодзи как заголовки, выделяй заголовки тегом <b>):
🤖 <b>AI-ролики</b> — хедлайнер. Самое яркое в AI-рекламе/роликах за сутки:
   что залетело ИЛИ что громко провалилось, и почему. Это идёт первым.
🔥 <b>Залетело</b> — по регионам, 1–2 ярких залёта на регион (если есть):
   🌍 Мир · 🇺🇦 Украина-СНГ · 🌏 Азия · 🇪🇺 Европа.
🧠 <b>Кейс дня</b> — один разбор кампании с конкретным выводом.
🛠 <b>Инструменты</b> — ТОЛЬКО если реально что-то вышло или подешевело
   (новая модель, цена, фича). Часто этот блок можно опустить.
💡 <b>На пробу сегодня</b> — одна микро-задача команде, выросшая из выпуска.

ФОРМАТ ПОД TELEGRAM:
- Только теги <b>...</b> для жирного. Никаких других HTML-тегов.
- Не используй символы <, >, & вне тегов <b>.
- Объём — компактный, чтобы читалось за минуту-две.
"""


def build_user_prompt() -> str:
    today = datetime.date.today().strftime("%d.%m.%Y")
    if MODE == "alert":
        return f"""Сегодня {today}. Проверь горящие новости за последние ~12 часов
по маркетингу, AI-рекламе и инструментам генерации видео.

ПОРОГ ВАЖНОСТИ (шли алерт только если выполнено одно из):
- вышла новая флагманская модель генерации видео/изображений или резко упала цена;
- платформа/сервис, важный для AI-видео, меняется или закрывается;
- крупный бренд/агентство выпустил(о) громкую AI-рекламу (залёт или скандал).

Если ничего на этот порог не тянет — верни РОВНО одно слово: {NO_ALERT_TOKEN}
(без кавычек, без пояснений).

Если есть что-то важное — напиши КОРОТКИЙ алерт (2–4 предложения) тем же
живым голосом, с пометкой «зачем это нам» и одной ссылкой-пруфом."""
    # обычный режим
    sources_hint = ""
    if PRIORITY_SOURCES:
        sites = " OR ".join(f"site:{d}" for d in PRIORITY_SOURCES)
        sources_hint = (f"\nОбязательно сделай отдельный поиск по приоритетным "
                        f"источникам (например: {sites}) и учти их свежие материалы.")
    return f"""Сегодня {today}. Собери сегодняшний выпуск дайджеста по брифу.
Сначала поищи свежие материалы (AI-ролики и AI-реклама в приоритете, затем
залёты рекламы по регионам: мир, Украина-СНГ, Азия, Европа; затем — новости
инструментов генерации видео).{sources_hint} Потом напиши выпуск по заданной структуре."""


# ----------------------------------------------------------------------------
# Сбор дайджеста через Gemini 3.1 + граундинг Google Search
# ----------------------------------------------------------------------------
def generate_digest() -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Встроенные инструменты Gemini:
    #  - google_search: модель сама ищет в вебе и проставляет источники;
    #  - url_context:   умеет открывать конкретные страницы (в т.ч. t.me/s/<канал>).
    tools = [
        types.Tool(google_search=types.GoogleSearch()),
        types.Tool(url_context=types.UrlContext()),
    ]

    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=tools,
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=build_user_prompt(),
        config=config,
    )

    return (response.text or "").strip()


# ----------------------------------------------------------------------------
# Отправка в Telegram (без внешних зависимостей, через urllib)
# ----------------------------------------------------------------------------
def _post_telegram(text: str, use_html: bool) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }
    if use_html:
        payload["parse_mode"] = "HTML"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] ошибка отправки: {e}", file=sys.stderr)
        return False


def send_to_telegram(text: str) -> None:
    # Telegram ограничивает сообщение ~4096 символами — режем по абзацам.
    limit = 3800
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > limit:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = (current + "\n\n" + paragraph) if current else paragraph
    if current:
        chunks.append(current)

    for chunk in chunks:
        ok = _post_telegram(chunk, use_html=True)
        if not ok:
            # запасной вариант: вдруг сломалась HTML-разметка — шлём как текст
            _post_telegram(chunk, use_html=False)


# ----------------------------------------------------------------------------
def main() -> int:
    missing = [k for k in ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
               if not os.environ.get(k)]
    if missing:
        print(f"Не заданы переменные окружения: {', '.join(missing)}", file=sys.stderr)
        return 1

    digest = generate_digest()

    if MODE == "alert" and (not digest or NO_ALERT_TOKEN in digest):
        print("Горящих новостей нет — алерт не отправлен.")
        return 0

    if not digest:
        print("Пустой результат — нечего отправлять.", file=sys.stderr)
        return 1

    send_to_telegram(digest)
    print("Отправлено в Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
