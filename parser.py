import feedparser
import sqlite3
from googletrans import Translator
import requests
import time

feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

# === НАСТРОЙКИ ===
BOT_TOKEN = "8863031090:AAH2n1qPBlz3JUuWSH-pmcFg19QBtCOANXI"
CHAT_ID = -5196561423
RSS_SOURCES = [
    "https://www.gematsu.com/feed",
    "https://www.eurogamer.net/feed",
    "https://www.pcgamer.com/rss/",
    "https://www.reddit.com/r/Games/top/.rss?t=day",
    "https://www.reddit.com/r/gamingleaksandrumours/top/.rss?t=day"
]

# НАСТРОЙКИ ФИЛЬТРАЦИИ И ЛИМИТОВ:
KEYWORDS = ['gta', 'zelda', 'release', 'trailer', 'announcement', "leak", "rumor", "delay", "cancelled", "layoffs", "closure", "controversy", "backlash",\
             "flop", "monetization", "live-service", "GaaS", "acquisition", "indie", "AAA", "sales", "Nintendo"]

# === СОЗДАЕМ БАЗУ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('news.db')
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
    conn.close()

# === ПАРСИМ RSS ===
def parse_all_rss(sources):
    all_articles = []
    
    for url in sources:
        print(f"Парсим: {url}")
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            article = {
                'id': entry.get('id', entry.get('link')),
                'title': entry.title,
                'link': entry.link,
                'published': entry.get('published', ''),
                'source': feed.feed.get('title', 'Unknown')
            }
            all_articles.append(article)
            
        if 'reddit.com' in url:
            time.sleep(2)
            
    return all_articles

# === ПРОВЕРЯЕМ, ЕСТЬ ЛИ НОВОСТЬ В БАЗЕ ===
def is_article_exists(article_id):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM articles WHERE id = ?', (article_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

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

# === СОХРАНЯЕМ В БАЗУ ===
def save_article(article, title_ru):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO articles 
        (id, title_original, title_ru, link, source, published_at, is_sent)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (
        article['id'],
        article['title'],
        title_ru,
        article['link'],
        article['source'],
        article['published']
    ))
    conn.commit()
    conn.close()

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    print("Запуск парсера...")
    init_db()
    
    # 1. Парсим новости
    articles = parse_all_rss(RSS_SOURCES)
    print(f"Всего найдено новостей: {len(articles)}")
    
    # 2. ФИЛЬТР по ключевым словам (если список не пустой)
    if KEYWORDS:
        filtered_articles = []
        for article in articles:
            title_lower = article['title'].lower()
            # Проверяем, есть ли хоть одно ключевое слово в заголовке
            if any(keyword.lower() in title_lower for keyword in KEYWORDS):
                filtered_articles.append(article)
        articles = filtered_articles
        print(f"После фильтра по ключевым словам осталось: {len(articles)}")
    
    # 3. ЛИМИТ на количество обрабатываемых новостей
    print(f"Будет обработано и отправлено (лимит): {len(articles)}\n")
    
    # 4. Обрабатываем каждую
    for article in articles:
        # Проверяем, есть ли уже в базе
        if is_article_exists(article['id']):
            print(f"Пропускаем (уже в базе): {article['title'][:40]}...")
            continue
        
        # Переводим
        title_ru = translate_title(article['title'])
        print(f"Переведено: {article['title'][:30]}...")
        
        # Отправляем в Telegram
        if send_to_telegram(article['title'], title_ru, article['link']):
            print(f"✅ Отправлено: {article['source']} | {article['title'][:30]}...")
            save_article(article, title_ru)
        else:
            print(f"❌ Не отправлено: {article['title']}")
        
        time.sleep(2.0)
    
    print("\nГотово!")

if __name__ == "__main__":
    main()