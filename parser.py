import feedparser
import psycopg2
from googletrans import Translator
import requests
import time
import os
import hashlib
from dotenv import load_dotenv

# Для локального тестирования (на GitHub Actions это не влияет, там работают Secrets)
load_dotenv()

feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

# === НАСТРОЙКИ ===
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID'))
DATABASE_URL = os.environ.get('DATABASE_URL') # Новая переменная для облачной базы

RSS_SOURCES = [
    "https://www.gematsu.com/feed",
    "https://www.eurogamer.net/feed",
    "https://www.pcgamer.com/rss/",
    "https://www.reddit.com/r/Games/top/.rss?t=day",
    "https://www.reddit.com/r/gamingleaksandrumours/top/.rss?t=day"
]

# НАСТРОЙКИ ФИЛЬТРАЦИИ И ЛИМИТОВ (твой оригинальный список)
KEYWORDS = ['gta', 'zelda', 'release', 'trailer', 'announcement', "leak", "rumor", "delay", "cancelled", "layoffs", "closure", "controversy", "backlash",
             "flop", "monetization", "live-service", "GaaS", "acquisition", "indie", "AAA", "sales", "Nintendo"]

# === РАБОТА С БАЗОЙ ДАННЫХ (PostgreSQL) ===
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            title_original TEXT,
            title_ru TEXT,
            link TEXT,
            source TEXT,
            published_at TEXT,
            is_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def is_article_exists(conn, article_id):
    cursor = conn.cursor()
    # В PostgreSQL используется %s вместо ?
    cursor.execute('SELECT id FROM articles WHERE id = %s', (article_id,))
    result = cursor.fetchone()
    cursor.close()
    return result is not None

def save_article(conn, article, title_ru):
    cursor = conn.cursor()
    # ON CONFLICT (id) DO NOTHING — аналог INSERT OR IGNORE в SQLite
    cursor.execute('''
        INSERT INTO articles (id, title_original, title_ru, link, source, published_at, is_sent)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        ON CONFLICT (id) DO NOTHING
    ''', (
        article['id'],
        article['title'],
        title_ru,
        article['link'],
        article['source'],
        article['published']
    ))
    conn.commit()
    cursor.close()

# === ПАРСИМ RSS ===
def parse_all_rss(sources):
    all_articles = []
    
    for url in sources:
        print(f"Парсим: {url}")
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            # Генерируем надежный уникальный ID из заголовка и ссылки
            unique_string = f"{entry.title.strip()}{entry.link.strip()}"
            article_id = hashlib.md5(unique_string.encode('utf-8')).hexdigest()
            
            article = {
                'id': article_id,
                'title': entry.title,
                'link': entry.link,
                'published': entry.get('published', ''),
                'source': feed.feed.get('title', 'Unknown')
            }
            all_articles.append(article)
            
        if 'reddit.com' in url:
            time.sleep(2)
            
    return all_articles

# === ПЕРЕВОДИМ ЗАГОЛОВОК ===
def translate_title(title):
    try:
        translator = Translator()
        result = translator.translate(title, src='auto', dest='ru')
        return result.text
    except Exception as e:
        print(f"⚠️ Ошибка перевода (пропускаем или оставляем оригинал): {e}")
        return title

# === ОТПРАВЛЯЕМ В TELEGRAM ===
def send_to_telegram(title_original, title_ru, link):
    message = f"""🎮 <b>{title_original}</b>

🇷🇺 <i>{title_ru}</i>

 <a href="{link}">Источник</a>
"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    print("Запуск парсера...")
    init_db()
    
    conn = get_db_connection()
    
    articles = parse_all_rss(RSS_SOURCES)
    print(f"Всего найдено новостей: {len(articles)}")
    
    if KEYWORDS:
        filtered_articles = []
        for article in articles:
            title_lower = article['title'].lower()
            if any(keyword.lower() in title_lower for keyword in KEYWORDS):
                filtered_articles.append(article)
        articles = filtered_articles
        print(f"После фильтра по ключевым словам осталось: {len(articles)}")
    
    print(f"Будет обработано и отправлено: {len(articles)}\n")
    
    for article in articles:
        # Проверяем, есть ли уже в базе (теперь по надежному хэшу!)
        if is_article_exists(conn, article['id']):
            print(f"Пропускаем (уже в базе): {article['title'][:40]}...")
            continue
        
        title_ru = translate_title(article['title'])
        print(f"Переведено: {article['title'][:30]}...")
        
        if send_to_telegram(article['title'], title_ru, article['link']):
            print(f"✅ Отправлено: {article['source']} | {article['title'][:30]}...")
            save_article(conn, article, title_ru)
        else:
            print(f"❌ Не отправлено: {article['title']}")
        
        time.sleep(2.0)
    
    conn.close()
    print("\nГотово!")

if __name__ == "__main__":
    main()
