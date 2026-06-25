import re
import sqlite3
import logging
import os
import random
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# --- Загрузка переменных окружения ---
load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
PASSWORD = os.getenv('ADMIN_PASSWORD', 'мойсекретныйпароль123')
ADMIN_ID = int(os.getenv('ADMIN_ID', '1364254252'))

# --- Проверка наличия токена ---
if not TOKEN:
    raise ValueError("❌ Токен бота не найден! Добавь BOT_TOKEN в файл .env")

# --- Инициализация ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
VERIFICATION_TIMEOUT = 60  # Секунд на проверку
MAX_ATTEMPTS = 3  # Максимум попыток
AUTO_DELETE_DELAY = 60  # Через сколько секунд удалять сообщения бота

WELCOME_TEXT = """
🌟 <b>Добро пожаловать в Вейп-Барахолку Краснодара</b>, {user_mention}! 🎉

📋 <b>Правила чата:</b>
🚫 <b>Запрещено:</b>
• ❌ Не вейп-тематика
• ❌ Оскорбления и флуд
• ❌ Спам и реклама

⚠️ <b>Внимание!</b>
При скаме: @callumom 
Администрация не отвечает за сделки.

🏪 <b>Лучшие вейп-шопы:</b>
• 🔥 Mix Vape: https://t.me/mixvape1

💫 <b>Приятного общения!</b>
"""

# --- Работа с базой данных ---
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    
    # Таблица запрещенных слов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Таблица верифицированных пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для отслеживания приветствий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS greeted_users (
            user_id INTEGER PRIMARY KEY,
            greeted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица старых пользователей (были в чате до запуска бота)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS old_users (
            user_id INTEGER PRIMARY KEY,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    
    # Заполняем начальными словами, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM words")
    count = cursor.fetchone()[0]
    
    if count == 0:
        initial_words = [
            "подработка", "заработок", "заработать", "заработнаяплата", "удаленнаяработа",
            "удаленка", "работавинтернете", "работаонлайн", "вакансия", "дополнительныйдоход",
            "свободныйграфик", "легкиеденьги", "доходбезвложений", "пассивныйдоход", "работанадому",
            "заработокбезопыта", "ищулюдей", "ищусотрудника", "ищучеловека", "ищуработника",
            "ищукандидата", "ищудевушку", "ищупарня", "ищупомощника", "ищуассистента",
            "требуютсясотрудники", "требуетсясотрудник", "набираемсотрудников", "наборсотрудников",
            "открытавакансия", "приглашаювкоманду", "ищемлюдей", "ищемсотрудников", "ищемработников",
            "вакансияоткрыта", "заработнаяплатавысокая", "отдатьбесплатно", "отдамбесплатно",
            "отдатьбесплатнозарефку", "реф", "рефка", "альфа", "дельце", "трудоустройство",
            "кешвышеобычного", "обучениенаместе", "ищутолковыхребят", "пкклуб", "пацаныотлет",
            "пацаныотл", "оплатасразу", "работанесложная", "новичковберём", "выплатимчестно",
            "требуетсяпомощь", "естьтемазароботка", "еслиинтерестнопиши", "зарефкуальфы",
            "прибыльнаяшабашка", "можносовмещатьсучебой", "скупаюголду", "хорошемукурсу",
            "беруваренду", "дамподработку", "бросаюкурить", "плачуот", "вкомпьютерныйклуб",
            "быстрыеденьги", "легкийкуш", "арендасим", "куплюакк", "арендааккаунта", "арбитраж",
            "биржа", "быстрыйвыхлоп", "доходность", "крипта", "пассивныйзаработок", "ищемпарней",
            "ищемчеловека", "винтернетмагазин", "ищемребят", "возьмуваренду", "скуплюпушкинскиекарты",
            "баллыпушкинскойкарты"
        ]
        for w in initial_words:
            try:
                cursor.execute("INSERT INTO words (word) VALUES (?)", (w.lower(),))
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    
    conn.close()
    logger.info("✅ База данных инициализирована")

# --- Функции для работы с БД ---
def get_all_words():
    """Получить все запрещенные слова"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("SELECT word FROM words ORDER BY word")
    words = [row[0] for row in cursor.fetchall()]
    conn.close()
    return words

def add_word_to_db(word):
    """Добавить слово в БД"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO words (word) VALUES (?)", (word.lower(),))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_word_from_db(word):
    """Удалить слово из БД"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM words WHERE word = ?", (word.lower(),))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def is_user_verified(user_id: int) -> bool:
    """Проверить, верифицирован ли пользователь"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM verified_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_verified_user(user_id: int, username: str = None):
    """Добавить пользователя в верифицированные"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO verified_users (user_id, username) VALUES (?, ?)",
        (user_id, username or str(user_id))
    )
    conn.commit()
    conn.close()
    logger.info(f"✅ Пользователь {user_id} верифицирован")

def is_user_greeted(user_id: int) -> bool:
    """Проверить, приветствовали ли пользователя"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM greeted_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_greeted_user(user_id: int):
    """Отметить пользователя как приветствованного"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO greeted_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def is_old_user(user_id: int) -> bool:
    """Проверить, является ли пользователь 'старым' (был в чате до запуска бота)"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM old_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_as_old_user(user_id: int):
    """Отметить пользователя как 'старого'"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO old_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    """Получить статистику"""
    conn = sqlite3.connect('banned_words.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM words")
    words_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM verified_users")
    verified_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM old_users")
    old_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM greeted_users")
    greeted_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        'words': words_count,
        'verified': verified_count,
        'old_users': old_count,
        'greeted': greeted_count
    }

def clean_text(text):
    """Очистка текста: убираем все, кроме букв и цифр"""
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', text.lower())
    return cleaned

# --- Хранилище активных верификаций ---
verifications = {}

# --- Система авторизации в ЛС ---
user_sessions = {}

def check_auth(message: Message) -> bool:
    """Проверка авторизации пользователя"""
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        return True
    return user_sessions.get(user_id, False)

# --- Функция для автоматического удаления сообщений бота ---
async def delete_message_later(chat_id: int, message_id: int, delay: int = AUTO_DELETE_DELAY):
    """Удаляет сообщение через указанное время"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
        logger.debug(f"🗑 Удалено сообщение {message_id} в чате {chat_id}")
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение {message_id}: {e}")

# --- Генерация математического примера ---
def generate_math_question():
    """Генерирует пример и возвращает (вопрос, правильный_ответ, варианты)"""
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    correct = a * b
    
    # Генерируем 2 неправильных варианта
    wrong_options = []
    attempts = 0
    while len(wrong_options) < 2 and attempts < 50:
        wrong = correct + random.randint(-5, 5)
        if wrong != correct and wrong > 0 and wrong not in wrong_options:
            wrong_options.append(wrong)
        attempts += 1
    
    # Если не удалось найти 2 неправильных варианта
    while len(wrong_options) < 2:
        wrong = correct + random.randint(1, 3)
        if wrong != correct and wrong > 0 and wrong not in wrong_options:
            wrong_options.append(wrong)
    
    options = wrong_options + [correct]
    random.shuffle(options)
    
    return f"{a} × {b} = ?", correct, options

# --- Функция создания клавиатуры для верификации ---
def create_verification_keyboard(options):
    """Создает клавиатуру с вариантами ответов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=str(options[0]), callback_data=f"verify_{options[0]}"),
            InlineKeyboardButton(text=str(options[1]), callback_data=f"verify_{options[1]}")
        ],
        [
            InlineKeyboardButton(text=str(options[2]), callback_data=f"verify_{options[2]}")
        ]
    ])
    return keyboard

# --- Таймаут верификации ---
async def verification_timeout(user_id: int, chat_id: int):
    """Обработка таймаута верификации"""
    await asyncio.sleep(VERIFICATION_TIMEOUT)
    
    if user_id in verifications:
        logger.info(f"⏰ Таймаут верификации для пользователя {user_id}")
        # Удаляем из активных верификаций
        del verifications[user_id]

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---

# --- Обработчик новых участников ---
@dp.message()
async def handle_new_member(message: Message):
    """Обрабатывает новых участников группы"""
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    if not message.new_chat_members:
        return
    
    # Проверяем права бота
    try:
        bot_member = await message.chat.get_member(bot.id)
        if not bot_member.can_restrict_members:
            logger.warning("⚠️ Бот не имеет прав на ограничение пользователей")
            return
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке прав бота: {e}")
        return
    
    for new_member in message.new_chat_members:
        # Пропускаем ботов
        if new_member.is_bot:
            continue
        
        user_id = new_member.id
        
        # Проверяем, не старый ли пользователь
        if is_old_user(user_id):
            logger.info(f"👤 Старый пользователь {user_id} зашел в группу (пропускаем верификацию)")
            continue
        
        # Проверяем, не верифицирован ли уже пользователь
        if is_user_verified(user_id):
            logger.info(f"✅ Уже верифицированный пользователь {user_id} зашел в группу")
            continue
        
        # Проверяем, не приветствовали ли его уже
        if is_user_greeted(user_id):
            logger.info(f"👤 Пользователь {user_id} уже приветствовался ранее")
            continue
        
        # Ограничиваем пользователя (запрещаем писать)
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            logger.info(f"🔒 Пользователь {user_id} ограничен (верификация)")
        except Exception as e:
            logger.error(f"❌ Не удалось ограничить пользователя {user_id}: {e}")
            continue
        
        # Генерируем вопрос
        question, correct_answer, options = generate_math_question()
        
        # Создаем клавиатуру
        keyboard = create_verification_keyboard(options)
        
        # Отправляем приветствие с вопросом
        mention = new_member.mention_html()
        welcome_msg = WELCOME_TEXT.format(user_mention=mention)
        
        verification_text = (
            f"{welcome_msg}\n\n"
            f"🔐 <b>Верификация:</b>\n"
            f"Реши пример, чтобы получить доступ к чату:\n"
            f"<b>{question}</b>\n\n"
            f"⏱ У тебя {VERIFICATION_TIMEOUT} секунд и {MAX_ATTEMPTS} попытки."
        )
        
        try:
            sent_msg = await message.reply(
                verification_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
            # Сохраняем данные верификации
            verifications[user_id] = {
                'attempts': 0,
                'answer': correct_answer,
                'message_id': sent_msg.message_id,
                'chat_id': message.chat.id,
                'user_id': user_id
            }
            
            # Добавляем в greeted_users (чтобы больше не приветствовать)
            add_greeted_user(user_id)
            
            # Удаляем сообщение через минуту
            asyncio.create_task(delete_message_later(message.chat.id, sent_msg.message_id))
            
            # Таймаут для автоматического провала
            asyncio.create_task(verification_timeout(user_id, message.chat.id))
            
            logger.info(f"📨 Отправлена верификация для пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке верификации: {e}")

# --- Обработчик нажатия кнопок верификации ---
@dp.callback_query(lambda c: c.data and c.data.startswith('verify_'))
async def process_verification(callback_query: types.CallbackQuery):
    """Обрабатывает нажатие кнопок верификации"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    # Проверяем, есть ли пользователь в процессе верификации
    if user_id not in verifications:
        await callback_query.answer("⏰ Время верификации истекло!", show_alert=True)
        try:
            await callback_query.message.delete()
        except:
            pass
        return
    
    # Проверяем, что это тот же пользователь
    if verifications[user_id]['user_id'] != user_id:
        await callback_query.answer("❌ Это не твоя верификация!", show_alert=True)
        return
    
    # Получаем ответ пользователя
    try:
        selected_value = int(callback_query.data.split('_')[1])
    except ValueError:
        await callback_query.answer("❌ Ошибка!", show_alert=True)
        return
    
    correct_answer = verifications[user_id]['answer']
    
    # Проверяем ответ
    if selected_value == correct_answer:
        # Успешная верификация!
        await callback_query.answer("✅ Правильно! Ты прошел верификацию!", show_alert=True)
        
        # Даем права на отправку сообщений
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=True)
            )
            
            # Добавляем в базу верифицированных
            username = callback_query.from_user.username or str(user_id)
            add_verified_user(user_id, username)
            
            # Отправляем сообщение об успехе
            success_msg = await callback_query.message.reply(
                f"✅ {callback_query.from_user.mention_html()}, ты прошел верификацию!\n"
                f"Теперь ты можешь писать в чат. Добро пожаловать! 🎉",
                parse_mode=ParseMode.HTML
            )
            
            # Удаляем сообщение с вопросом
            try:
                await callback_query.message.delete()
            except:
                pass
            
            # Удаляем сообщение об успехе через минуту
            asyncio.create_task(delete_message_later(chat_id, success_msg.message_id))
            
            logger.info(f"✅ Пользователь {user_id} успешно прошел верификацию")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при верификации пользователя {user_id}: {e}")
            await callback_query.message.reply(f"❌ Ошибка: {e}")
        
        # Удаляем из активных верификаций
        del verifications[user_id]
        
    else:
        # Неправильный ответ
        verifications[user_id]['attempts'] += 1
        attempts_left = MAX_ATTEMPTS - verifications[user_id]['attempts']
        
        if attempts_left <= 0:
            # Исчерпаны попытки
            await callback_query.answer("❌ Попытки исчерпаны! Доступ запрещен.", show_alert=True)
            
            try:
                await callback_query.message.delete()
            except:
                pass
            
            logger.info(f"❌ Пользователь {user_id} не прошел верификацию (3 ошибки)")
            
            # Оставляем пользователя с ограничениями
            del verifications[user_id]
        else:
            # Генерируем новый вопрос
            question, correct_answer, options = generate_math_question()
            verifications[user_id]['answer'] = correct_answer
            
            keyboard = create_verification_keyboard(options)
            
            # Получаем текст без вопроса
            text_parts = callback_query.message.text.split('🔐')
            welcome_part = text_parts[0] if len(text_parts) > 0 else ""
            
            # Обновляем сообщение
            try:
                await callback_query.message.edit_text(
                    f"{welcome_part}"
                    f"🔐 <b>Верификация:</b>\n"
                    f"❌ Неправильно! Осталось попыток: {attempts_left}\n"
                    f"Реши новый пример:\n"
                    f"<b>{question}</b>\n\n"
                    f"⏱ У тебя {VERIFICATION_TIMEOUT} секунд.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении сообщения: {e}")
            
            await callback_query.answer(f"❌ Неправильно! Осталось {attempts_left} попыток", show_alert=True)

# --- КОМАНДЫ УПРАВЛЕНИЯ В ЛИЧНЫХ СООБЩЕНИЯХ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие в ЛС"""
    if message.chat.type != 'private':
        return
    
    is_admin = message.from_user.id == ADMIN_ID
    
    welcome_text = (
        "🤖 <b>Бот для модерации групп</b>\n\n"
        "🔐 <b>Доступ к командам управления:</b>\n"
    )
    
    if is_admin:
        welcome_text += "✅ Ты распознан как главный администратор. Доступ открыт!\n\n"
    else:
        welcome_text += f"Введи пароль: <code>/login {PASSWORD}</code>\n\n"
    
    welcome_text += (
        "📋 <b>Доступные команды:</b>\n"
        "/addword &lt;слово&gt; - добавить слово в черный список\n"
        "/delword &lt;слово&gt; - удалить слово из черного списка\n"
        "/listwords - показать все запрещенные слова\n"
        "/stats - статистика\n"
        "/logout - выйти из системы\n\n"
        "⚠️ <b>Команды работают ТОЛЬКО в личных сообщениях!</b>"
    )
    
    await message.reply(welcome_text, parse_mode=ParseMode.HTML)

@dp.message(Command("login"))
async def cmd_login(message: Message):
    """Авторизация по паролю"""
    if message.chat.type != 'private':
        return
    
    if message.from_user.id == ADMIN_ID:
        await message.reply("✅ Ты главный администратор, доступ уже открыт!")
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❌ Введи пароль: <code>/login пароль</code>", parse_mode=ParseMode.HTML)
        return
    
    entered_password = args[1].strip()
    
    if entered_password == PASSWORD:
        user_sessions[message.from_user.id] = True
        await message.reply("✅ Авторизация успешна! Теперь ты можешь управлять списком слов.")
        logger.info(f"🔑 Пользователь {message.from_user.id} авторизовался")
    else:
        await message.reply("❌ Неверный пароль! Доступ запрещен.")

@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    """Выход из системы"""
    if message.chat.type != 'private':
        return
    
    if message.from_user.id == ADMIN_ID:
        await message.reply("ℹ️ Ты главный администратор, выход не требуется.")
        return
    
    if message.from_user.id in user_sessions:
        del user_sessions[message.from_user.id]
        await message.reply("✅ Вы вышли из системы. Для доступа снова используй /login")
        logger.info(f"🔓 Пользователь {message.from_user.id} вышел из системы")
    else:
        await message.reply("ℹ️ Вы и так не авторизованы.")

@dp.message(Command("addword"))
async def add_word_command(message: Message):
    """Добавление слова"""
    if message.chat.type != 'private':
        return
    
    if not check_auth(message):
        await message.reply("🔐 Доступ запрещен! Используй <code>/login пароль</code>", parse_mode=ParseMode.HTML)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("ℹ️ Использование: <code>/addword слово</code>\nПример: <code>/addword мошенник</code>", parse_mode=ParseMode.HTML)
        return
    
    new_word = args[1].strip().lower()
    cleaned_new_word = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', new_word)
    
    if len(cleaned_new_word) < 2:
        await message.reply("❌ Слишком короткое слово. Должно быть минимум 2 символа.")
        return

    if add_word_to_db(cleaned_new_word):
        await message.reply(f"✅ Слово <b>{cleaned_new_word}</b> добавлено в список запрещенных.", parse_mode=ParseMode.HTML)
        logger.info(f"📝 Добавлено слово: {cleaned_new_word}")
    else:
        await message.reply(f"⚠️ Слово <b>{cleaned_new_word}</b> уже есть в списке.", parse_mode=ParseMode.HTML)

@dp.message(Command("delword"))
async def del_word_command(message: Message):
    """Удаление слова"""
    if message.chat.type != 'private':
        return
    
    if not check_auth(message):
        await message.reply("🔐 Доступ запрещен! Используй <code>/login пароль</code>", parse_mode=ParseMode.HTML)
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("ℹ️ Использование: <code>/delword слово</code>\nПример: <code>/delword мошенник</code>", parse_mode=ParseMode.HTML)
        return

    word_to_del = args[1].strip().lower()
    cleaned_word = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', word_to_del)

    if remove_word_from_db(cleaned_word):
        await message.reply(f"✅ Слово <b>{cleaned_word}</b> удалено из списка.", parse_mode=ParseMode.HTML)
        logger.info(f"🗑 Удалено слово: {cleaned_word}")
    else:
        await message.reply(f"⚠️ Слово <b>{cleaned_word}</b> не найдено в списке.", parse_mode=ParseMode.HTML)

@dp.message(Command("listwords"))
async def list_words_command(message: Message):
    """Просмотр списка слов"""
    if message.chat.type != 'private':
        return
    
    if not check_auth(message):
        await message.reply("🔐 Доступ запрещен! Используй <code>/login пароль</code>", parse_mode=ParseMode.HTML)
        return

    words = get_all_words()
    if not words:
        await message.reply("📭 Список запрещенных слов пуст.")
        return

    # Разбиваем на страницы по 50 слов
    page_size = 50
    total_pages = (len(words) + page_size - 1) // page_size
    
    # Показываем первую страницу
    page = 0
    start = page * page_size
    end = min(start + page_size, len(words))
    
    word_list = "\n".join([f"• {w}" for w in words[start:end]])
    
    await message.reply(
        f"📋 <b>Список запрещенных слов</b> ({len(words)} шт.):\n\n{word_list}",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("stats"))
async def stats_command(message: Message):
    """Статистика"""
    if message.chat.type != 'private':
        return
    
    if not check_auth(message):
        await message.reply("🔐 Доступ запрещен! Используй <code>/login пароль</code>", parse_mode=ParseMode.HTML)
        return
    
    stats = get_stats()
    
    await message.reply(
        f"📊 <b>Статистика:</b>\n\n"
        f"📝 Запрещенных слов: {stats['words']}\n"
        f"✅ Верифицированных пользователей: {stats['verified']}\n"
        f"👤 Старых пользователей (были до бота): {stats['old_users']}\n"
        f"👋 Приветствованных: {stats['greeted']}\n"
        f"🔄 Активных верификаций: {len(verifications)}\n"
        f"👥 Активных сессий: {len(user_sessions)}\n"
        f"🔑 Админ ID: {ADMIN_ID}",
        parse_mode=ParseMode.HTML
    )

# --- Функция для проверки бана по словам ---
async def check_and_ban(message: Message):
    """Проверяет сообщение на наличие запрещенных слов и банит"""
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    if not message.text:
        return
    
    user_id = message.from_user.id
    
    # Помечаем пользователя как "старого", если он еще не отмечен
    # Это гарантирует, что старые пользователи не будут проходить верификацию
    if not is_old_user(user_id):
        mark_as_old_user(user_id)
        logger.debug(f"👤 Пользователь {user_id} отмечен как старый")
    
    # Проверяем, верифицирован ли пользователь
    # Если не верифицирован - пропускаем (он уже не может писать)
    if not is_user_verified(user_id):
        return

    banned_words = get_all_words()
    if not banned_words:
        return

    cleaned_msg = clean_text(message.text)
    
    if len(cleaned_msg) < 3:
        return

    found_word = None
    for word in banned_words:
        if word in cleaned_msg:
            found_word = word
            break

    if found_word:
        # Проверяем права бота
        try:
            bot_member = await message.chat.get_member(bot.id)
            if not bot_member.can_restrict_members:
                await message.reply("❌ У меня нет прав ограничивать пользователей! Дай мне права администратора.")
                return
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке прав бота: {e}")
            return

        try:
            # Ограничиваем пользователя (запрещаем писать)
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            
            mention = message.from_user.mention_html()
            ban_msg = await message.reply(
                f"🚫 Пользователь {mention} был ограничен.\n"
                f"Причина: сообщение содержало запрещенное слово/фразу: <b>{found_word}</b>",
                parse_mode=ParseMode.HTML
            )
            
            # Удаляем сообщение бана через минуту
            asyncio.create_task(delete_message_later(message.chat.id, ban_msg.message_id))
            
            # Удаляем сообщение нарушителя
            try:
                await message.delete()
            except:
                pass
            
            logger.info(f"🚫 Пользователь {user_id} ограничен за слово: {found_word}")
                
        except Exception as e:
            logger.error(f"❌ Не удалось ограничить пользователя {user_id}: {e}")
            await message.reply(f"❌ Не удалось ограничить пользователя. Ошибка: {e}")

# --- ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
@dp.message()
async def handle_all_messages(message: Message):
    """Главный обработчик всех сообщений"""
    if message.chat.type in ['group', 'supergroup']:
        # Проверяем новых участников
        if message.new_chat_members:
            await handle_new_member(message)
        
        # Проверяем на бан по словам
        await check_and_ban(message)

# --- ЗАПУСК БОТА ---
async def main():
    """Главная функция запуска"""
    try:
        # Инициализируем базу данных
        init_db()
        
        logger.info("🤖 Бот запущен и готов к работе!")
        logger.info(f"👤 Админ ID: {ADMIN_ID}")
        logger.info(f"📝 Команды работают ТОЛЬКО в личных сообщениях")
        logger.info(f"✅ Верификация новых пользователей включена")
        
        # Запускаем поллинг
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
