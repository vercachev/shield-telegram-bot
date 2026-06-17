import os
import re
import telebot
import threading
from flask import Flask
from github import Github

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = int(os.getenv("CHAT_ID"))
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("REPO_NAME", "vercachev/iphone-shiled-from-adds")

bot    = telebot.TeleBot(TELEGRAM_TOKEN)
github = Github(GITHUB_TOKEN)
repo   = github.get_repo(REPO_NAME)
app    = Flask(__name__)

# ========== GITHUB-ХЕЛПЕРЫ ==========
def get_generate_py():
    file = repo.get_contents("generate.py")
    return file.decoded_content.decode("utf-8"), file.sha

def update_generate_py(new_content, sha):
    """Коммит в main → GitHub Actions запустится САМ"""
    repo.update_file(
        path="generate.py",
        message="🛡️ Щит обновлен через Telegram",
        content=new_content,
        sha=sha
    )

def get_custom_blocked(content):
    pattern = r'CUSTOM_BLOCKED\s*=\s*\[(.*?)\]'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        raw = match.group(1)
        domains = [d.strip().strip('"').strip("'") for d in raw.split(",") if d.strip()]
        return [d for d in domains if not d.startswith("#") and d]
    return []

def set_custom_blocked(content, domains):
    lines = [f'    "{d}",' for d in domains]
    blocked_str = "\n" + "\n".join(lines) + "\n"
    if not domains:
        blocked_str = "\n"
    pattern = r'(CUSTOM_BLOCKED\s*=\s*\[).*?(\n\s*\])'
    replacement = r'\1' + blocked_str + r'    \2'
    return re.sub(pattern, replacement, content, flags=re.DOTALL)

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def cmd_start(message):
    if message.chat.id != CHAT_ID: return
    bot.reply_to(message,
        "🛡️ *ZeroAds Shield — Управление*\n\n"
        "• `/block domain.com` — заблокировать\n"
        "• `/unblock domain.com` — разблокировать\n"
        "• `/list` — твой список\n"
        "• `/link` — ссылка на профиль для iPhone\n"
        "• `/status` — статус щита",
        parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    if message.chat.id != CHAT_ID: return
    bot.reply_to(message, "🟢 *Щит активен.* Бот онлайн.", parse_mode="Markdown")

@bot.message_handler(commands=['list'])
def cmd_list(message):
    if message.chat.id != CHAT_ID: return
    try:
        content, _ = get_generate_py()
        domains = get_custom_blocked(content)
        if not domains:
            bot.reply_to(message, "📭 Список пуст.")
            return
        text = "📋 *Твои блокировки:*\n\n" + "\n".join([f"• `{d}`" for d in domains])
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['block'])
def cmd_block(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Укажи домен:\n`/block example.com`", parse_mode="Markdown"); return
        domain = args[1].lower().strip()
        
        content, sha = get_generate_py()
        domains = get_custom_blocked(content)
        
        if domain in domains:
            bot.reply_to(message, f"⚠️ `{domain}` уже есть.", parse_mode="Markdown"); return
        
        domains.append(domain)
        new_content = set_custom_blocked(content, domains)
        update_generate_py(new_content, sha)
        
        bot.reply_to(message,
            f"✅ *Заблокировано:* `{domain}`\n\n"
            f"Actions пересоберет профиль (~1 мин).\n"
            f"Потом скачай новый профиль по команде `/link`",
            parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['unblock'])
def cmd_unblock(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Укажи домен:\n`/unblock example.com`", parse_mode="Markdown"); return
        domain = args[1].lower().strip()
        
        content, sha = get_generate_py()
        domains = get_custom_blocked(content)
        
        if domain not in domains:
            bot.reply_to(message, f"⚠️ `{domain}` и так не заблокирован.", parse_mode="Markdown"); return
        
        domains.remove(domain)
        new_content = set_custom_blocked(content, domains)
        update_generate_py(new_content, sha)
        
        bot.reply_to(message, f"✅ *Разблокировано:* `{domain}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['link'])
def cmd_link(message):
    if message.chat.id != CHAT_ID: return
    url = "https://vercachev.github.io/iphone-shiled-from-adds/shield.mobileconfig"
    bot.reply_to(message, f"📲 [Скачать профиль]({url})\n\nУстанови на iPhone → Настройки → Профиль загружен.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def fallback(message):
    if message.chat.id != CHAT_ID: return
    bot.reply_to(message, "Неизвестная команда. Напиши /start")

# ========== FLASK (НЕ ДАЕТ RENDER УБИТЬ БОТА) ==========
@app.route('/')
def health():
    return "🛡️ Shield Bot is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()