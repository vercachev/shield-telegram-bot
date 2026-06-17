import os
import re
import io
import socket
import threading
import requests
import telebot
from telebot import types
from flask import Flask
from github import Github

# ========== НАСТРОЙКИ ИЗ ENV ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = int(os.getenv("CHAT_ID"))
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("REPO_NAME", "vercachev/iphone-shiled-from-adds")

bot    = telebot.TeleBot(TELEGRAM_TOKEN)
github = Github(GITHUB_TOKEN)
repo   = github.get_repo(REPO_NAME)
app    = Flask(__name__)

# ========== ГЛАВНОЕ МЕНЮ (КНОПКИ) ==========
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('📊 Статистика')
    btn2 = types.KeyboardButton('📋 Мой список')
    btn3 = types.KeyboardButton('📲 Скачать профиль')
    btn4 = types.KeyboardButton('🟢 Статус системы')
    btn5 = types.KeyboardButton('🕐 История')
    btn6 = types.KeyboardButton('🔄 Пересобрать всё')
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5, btn6)
    return markup

# ========== GITHUB-ХЕЛПЕРЫ ==========
def get_generate_py():
    file = repo.get_contents("generate.py")
    return file.decoded_content.decode("utf-8"), file.sha

def update_generate_py(new_content, sha):
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
    blocked_str = "\n".join(lines)
    if blocked_str:
        blocked_str = "\n" + blocked_str + "\n"
    else:
        blocked_str = "\n"
    pattern = r'(CUSTOM_BLOCKED\s*=\s*\[).*?(\n\s*\])'
    replacement = r'\1' + blocked_str + r'\2'
    return re.sub(pattern, replacement, content, flags=re.DOTALL)

def trigger_actions():
    try:
        workflow = repo.get_workflow("main.yml")
        workflow.create_dispatch("main")
        return True
    except:
        return False

# ========== СЕТЕВЫЕ УТИЛИТЫ ==========
def resolve_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except:
        return None

def http_ping(domain):
    try:
        r = requests.head(f"http://{domain}", timeout=5, allow_redirects=True)
        return r.status_code
    except Exception as e:
        return str(e)

def whois_rdap(domain):
    try:
        r = requests.get(f"https://rdap.org/domain/{domain}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            name = data.get("name", domain)
            status = ", ".join(data.get("status", []))
            events = data.get("events", [])
            created = next((e["eventDate"] for e in events if e.get("eventAction") == "registration"), "неизвестно")
            registrar = "неизвестно"
            for ent in data.get("entities", []):
                if "registrar" in ent.get("roles", []):
                    vcard = ent.get("vcardArray", [])
                    if len(vcard) > 1:
                        for item in vcard[1]:
                            if item[0] == "fn":
                                registrar = item[3]
                                break
                    break
            return f"Домен: {name}\nРегистратор: {registrar}\nСтатус: {status}\nСоздан: {created}"
        return "RDAP недоступен"
    except Exception as e:
        return f"Ошибка: {e}"

def domain_in_lists(domain):
    try:
        r = requests.get("https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts", timeout=15)
        found = domain in r.text or domain.replace("www.", "") in r.text
        return found, "StevenBlack" if found else "не найдено"
    except:
        return False, "ошибка загрузки"

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@bot.message_handler(commands=['start'])
def cmd_start(message):
    if message.chat.id != CHAT_ID: return
    bot.send_message(
        message.chat.id,
        "🛡️ *ZeroAds Shield — Пульт управления*\n\n"
        "Используй кнопки внизу для быстрой навигации.\n\n"
        "✍️ *Для блокировки:* просто напиши домен (например: `ads.com`)\n"
        "❌ *Для разблокировки:* `/unblock domain.com`\n\n"
        "*Дополнительные команды:*\n"
        "• `/test domain.com` — полный анализ\n"
        "• `/whois domain.com` — владелец домена\n"
        "• `/ip domain.com` — IP адрес\n"
        "• `/ping domain.com` — доступен ли сайт\n"
        "• `/search domain.com` — поиск в базах блокировки\n"
        "• `/backup` — скачать бэкап конфига",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# --- КНОПКИ ---
@bot.message_handler(func=lambda m: m.text == '📊 Статистика')
def btn_stats(message):
    if message.chat.id != CHAT_ID: return
    try:
        content, _ = get_generate_py()
        my_list = get_custom_blocked(content)
        bot.reply_to(message,
            f"📊 *Статистика щита*\n\n"
            f"Базовые списки: ~`50,000+` доменов\n"
            f"Твои личные блоки: `{len(my_list)}`",
            parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(func=lambda m: m.text == '📋 Мой список')
def btn_list(message):
    if message.chat.id != CHAT_ID: return
    try:
        content, _ = get_generate_py()
        domains = get_custom_blocked(content)
        if not domains:
            bot.reply_to(message, "📭 Твой список пуст.")
            return
        text = "📋 *Твои блокировки:*\n\n" + "\n".join([f"• `{d}`" for d in domains])
        if len(text) > 4000:
            text = text[:4000] + "\n\n...и еще."
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(func=lambda m: m.text == '📲 Скачать профиль')
def btn_link(message):
    if message.chat.id != CHAT_ID: return
    url = "https://vercachev.github.io/iphone-shiled-from-adds/shield.mobileconfig"
    bot.reply_to(message, f"📲 [Скачать профиль для iPhone]({url})", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '🟢 Статус системы')
def btn_status(message):
    if message.chat.id != CHAT_ID: return
    bot.reply_to(message, "🟢 Бот: *Онлайн*\n🛡️ Щит: *Активен*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '🕐 История')
def btn_history(message):
    if message.chat.id != CHAT_ID: return
    try:
        commits = list(repo.get_commits()[:7])
        if not commits:
            bot.reply_to(message, "История пуста.")
            return
        text = "🕐 *Последние изменения:*\n\n"
        for c in commits:
            msg = c.commit.message[:45]
            date = c.commit.author.date.strftime("%d.%m %H:%M")
            text += f"`{date}` — {msg}\n"
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(func=lambda m: m.text == '🔄 Пересобрать всё')
def btn_rebuild(message):
    if message.chat.id != CHAT_ID: return
    if trigger_actions():
        bot.reply_to(message,
            "🔄 *Пересборка запущена!*\n\n"
            "GitHub Actions сейчас скачает свежие списки и соберет новый профиль.\n"
            "Подожди 1-2 минуты, потом скачай по кнопке «Скачать профиль».")
    else:
        bot.reply_to(message, "⚠️ Не удалось запустить сборку. Попробуй позже.")

# --- УМНАЯ БЛОКИРОВКА: просто отправляешь домен ---
@bot.message_handler(func=lambda m: "." in m.text and not m.text.startswith("/") and not m.text.startswith("📊") and not m.text.startswith("📋") and not m.text.startswith("📲") and not m.text.startswith("🟢") and not m.text.startswith("🕐") and not m.text.startswith("🔄"))
def quick_block(message):
    if message.chat.id != CHAT_ID: return
    domain = message.text.lower().strip()
    try:
        content, sha = get_generate_py()
        domains = get_custom_blocked(content)
        if domain in domains:
            bot.reply_to(message, f"⚠️ `{domain}` уже есть в списке.")
            return
        domains.append(domain)
        new_content = set_custom_blocked(content, domains)
        update_generate_py(new_content, sha)
        bot.reply_to(message,
            f"✅ *Заблокировано:* `{domain}`\n\n"
            f"GitHub Actions начал пересборку профиля (~1 мин).",
            parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

# --- КОМАНДЫ ТЕКСТОВЫЕ ---
@bot.message_handler(commands=['unblock'])
def cmd_unblock(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Используй: `/unblock domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        content, sha = get_generate_py()
        domains = get_custom_blocked(content)
        if domain not in domains:
            bot.reply_to(message, f"⚠️ `{domain}` не найден в списке.")
            return
        domains.remove(domain)
        new_content = set_custom_blocked(content, domains)
        update_generate_py(new_content, sha)
        bot.reply_to(message, f"✅ *Разблокировано:* `{domain}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['test'])
def cmd_test(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ `/test domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        bot.reply_to(message, f"🔬 Анализирую `{domain}`...")
        ip = resolve_ip(domain)
        ping = http_ping(domain)
        found, source = domain_in_lists(domain)
        content, _ = get_generate_py()
        my_blocked = domain in get_custom_blocked(content)
        text = f"*📋 Отчет по {domain}:*\n\n"
        text += f"• IP: `{ip or 'не разрешен'}`\n"
        text += f"• HTTP статус: `{ping if isinstance(ping, int) else 'недоступен'}`\n"
        text += f"• В твоем списке: `{'ДА' if my_blocked else 'нет'}`\n"
        text += f"• В базах блокировки: `{'ДА ('+source+')' if found else 'нет'}`\n\n"
        text += ("🛡️ *Вывод:* Этот домен будет заблокирован." if (my_blocked or found) else "✅ *Вывод:* Домен открыт. Если нужно — `/block " + domain + "`")
        bot.reply_to(message, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['whois'])
def cmd_whois(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ `/whois domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        bot.reply_to(message, f"🔎 Ищу данные по `{domain}`...")
        info = whois_rdap(domain)
        bot.send_message(CHAT_ID, f"*WHOIS / RDAP:*\n```{info}```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['ip'])
def cmd_ip(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ `/ip domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        ip = resolve_ip(domain)
        bot.reply_to(message, f"🌐 *{domain}*\nIP: `{ip or 'не разрешен'}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ `/ping domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        bot.reply_to(message, f"📡 Пингуем `{domain}`...")
        status = http_ping(domain)
        ok = isinstance(status, int) and status < 400
        bot.reply_to(message, f"{'✅' if ok else '⚠️'} *{domain}*\nHTTP: `{status}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['search'])
def cmd_search(message):
    if message.chat.id != CHAT_ID: return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ `/search domain.com`", parse_mode="Markdown")
            return
        domain = args[1].lower().strip()
        bot.reply_to(message, f"🔍 Ищу `{domain}` в базах...")
        found, source = domain_in_lists(domain)
        if found:
            bot.reply_to(message, f"🚫 *Найдено в {source}!*\nТвой щит его заблокирует.")
        else:
            bot.reply_to(message, f"✅ *Не найдено.*\nЕсли это реклама — отправь просто `{domain}` или `/block {domain}`")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['backup'])
def cmd_backup(message):
    if message.chat.id != CHAT_ID: return
    try:
        content, _ = get_generate_py()
        file_obj = io.BytesIO(content.encode('utf-8'))
        bot.send_document(CHAT_ID, file_obj, visible_file_name="generate.py_backup.txt", caption="📦 Бэкап текущего конфига")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# --- ПО ЛЮБОЙ ДРУГОЙ КОМАНДЕ ---
@bot.message_handler(func=lambda m: True)
def fallback(message):
    if message.chat.id != CHAT_ID: return
    bot.reply_to(message, "Неизвестная команда. Напиши /start для списка возможностей.")

# ========== FLASK (НЕ ДАЕТ RENDER УБИТЬ БОТА) ==========
@app.route('/')
def health():
    return "🛡️ Shield Bot is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()