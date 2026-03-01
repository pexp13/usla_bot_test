import logging
import asyncio
import os
import json
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ID администраторов (можно задать через переменную окружения)
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Состояния ConversationHandler
WAITING_SEARCH = 1
WAITING_FEEDBACK = 2

# Файл для хранения отзывов
FEEDBACK_FILE = "feedbacks.json"

# Категории документов
DOCUMENT_CATEGORIES = {
    'zayavleniya': {'name': '📝 Образцы заявлений', 'icon': '📝'},
    'spravki': {'name': '📄 Справки и формы', 'icon': '📄'},
    'grafiki': {'name': '📅 Графики и расписания', 'icon': '📅'},
    'instruktsii': {'name': '📋 Инструкции', 'icon': '📋'}
}

# Документы с прямыми ссылками и ключевыми словами для поиска
DOCUMENTS = {
    'zayavleniya': [
        {
            'name': 'Заявление на отпуск',
            'url': 'https://www.usla.ru/upload/main/f46/f4614c19fe04a24ec367ea54639eed94.pdf',
            'description': 'Образец заявления на отпуск',
            'keywords': ['отпуск', 'заявление', 'ежегодный', 'оплачиваемый', 'отдых', 'vacation']
        },
        {
            'name': 'Образец заявления на отпуск',
            'url': 'https://www.usla.ru/upload/main/6ce/6ce9f60d05ed22aa08e2e91a3219509e.pdf',
            'description': 'Заполненный образец заявления на отпуск',
            'keywords': ['отпуск', 'заявление', 'образец', 'пример', 'заполненный']
        },
        {
            'name': 'Образец представления к поощрению',
            'url': 'https://www.usla.ru/upload/main/2b4/2b446ce2a330b738054dc3f8d981d934.pdf',
            'description': 'Образец представления к поощрению сотрудника',
            'keywords': ['поощрение', 'представление', 'награда', 'премия', 'благодарность']
        },
        {
            'name': 'Заявка на подбор',
            'url': 'https://www.usla.ru/upload/main/ce9/ce919943a93e27c4b2e2ef699ab8044e.docx',
            'description': 'Образец заявки на подбор персонала',
            'keywords': ['подбор', 'персонал', 'вакансия', 'найм', 'трудоустройство', 'сотрудник', 'заявка']
        }
    ],
    'spravki': [
        {
            'name': 'Справка с места работы',
            'url': 'https://www.usla.ru/upload/main/example5.pdf',
            'description': 'Справка, подтверждающая трудовые отношения',
            'keywords': ['справка', 'место работы', 'трудовые', 'отношения', 'подтверждение', 'работа']
        },
        {
            'name': 'Справка о доходах',
            'url': 'https://www.usla.ru/upload/main/example6.pdf',
            'description': 'Справка о доходах для предоставления по месту требования',
            'keywords': ['справка', 'доход', 'зарплата', '2-ндфл', 'доходы', 'заработная плата', 'налог']
        }
    ],
    'grafiki': [
        {
            'name': 'График отпусков 2025',
            'url': 'https://www.usla.ru/upload/main/example7.pdf',
            'description': 'График отпусков на 2025 год',
            'keywords': ['график', 'отпуск', '2025', 'расписание', 'план']
        },
        {
            'name': 'График отпусков 2026',
            'url': 'https://www.usla.ru/upload/main/example8.pdf',
            'description': 'График отпусков на 2026 год',
            'keywords': ['график', 'отпуск', '2026', 'расписание', 'план']
        }
    ],
    'instruktsii': [
        {
            'name': 'Инструкция по оформлению документов',
            'url': 'https://www.usla.ru/upload/main/example9.pdf',
            'description': 'Порядок оформления кадровых документов',
            'keywords': ['инструкция', 'оформление', 'документы', 'порядок', 'кадровые', 'регламент']
        }
    ]
}

# ─────────────────────────────────────────
# РАБОТА С ОТЗЫВАМИ
# ─────────────────────────────────────────

def load_feedbacks() -> list:
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_feedback(feedback: dict):
    feedbacks = load_feedbacks()
    feedbacks.append(feedback)
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────
# СЕНТИМЕНТ-АНАЛИЗ (без внешних API)
# ─────────────────────────────────────────

POSITIVE_WORDS = [
    'отлично', 'хорошо', 'прекрасно', 'замечательно', 'удобно', 'помог', 'помогло',
    'спасибо', 'благодарю', 'доволен', 'довольна', 'нравится', 'понравилось',
    'быстро', 'легко', 'просто', 'удобный', 'полезно', 'полезный', 'супер',
    'классно', 'класс', 'круто', 'молодец', 'браво', 'рекомендую', 'советую',
    'работает', 'всё работает', 'нашёл', 'нашел', 'нашла', 'нашлось'
]

NEGATIVE_WORDS = [
    'плохо', 'ужасно', 'неудобно', 'не работает', 'не нашёл', 'не нашел',
    'не нашла', 'непонятно', 'сложно', 'неудобный', 'ошибка', 'проблема',
    'не помогло', 'бесполезно', 'не работает', 'глючит', 'зависает', 'медленно',
    'долго', 'неправильно', 'неверно', 'непонятный', 'отстой', 'плохой',
    'не могу', 'не получается', 'непонятна', 'разочарован', 'разочарована'
]

def analyze_sentiment(text: str) -> dict:
    """Простой словарный сентимент-анализ на русском языке"""
    text_lower = text.lower()
    
    pos_score = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg_score = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    
    # Учитываем отрицания
    negations = ['не ', 'нет ', 'никак', 'ни разу']
    negation_found = any(neg in text_lower for neg in negations)
    if negation_found:
        pos_score, neg_score = neg_score, pos_score + 1  # инвертируем при отрицании
    
    total = pos_score + neg_score
    if total == 0:
        label = 'нейтральный'
        emoji = '😐'
        confidence = 'низкая'
    elif pos_score > neg_score:
        ratio = pos_score / total
        label = 'положительный'
        emoji = '😊'
        confidence = 'высокая' if ratio > 0.7 else 'средняя'
    elif neg_score > pos_score:
        ratio = neg_score / total
        label = 'отрицательный'
        emoji = '😔'
        confidence = 'высокая' if ratio > 0.7 else 'средняя'
    else:
        label = 'смешанный'
        emoji = '😶'
        confidence = 'низкая'
    
    return {
        'label': label,
        'emoji': emoji,
        'confidence': confidence,
        'pos_score': pos_score,
        'neg_score': neg_score
    }

# ─────────────────────────────────────────
# ПОИСК ДОКУМЕНТОВ
# ─────────────────────────────────────────

def search_documents(query: str) -> list:
    """Поиск документов по свободному тексту"""
    query_lower = query.lower().strip()
    query_words = set(re.split(r'\s+', query_lower))
    
    results = []
    for category, docs in DOCUMENTS.items():
        cat_info = DOCUMENT_CATEGORIES.get(category, {})
        for idx, doc in enumerate(docs):
            score = 0
            doc_text = (doc['name'] + ' ' + doc['description']).lower()
            keywords = [kw.lower() for kw in doc.get('keywords', [])]
            
            # Прямое совпадение в названии/описании
            if query_lower in doc_text:
                score += 10
            
            # Совпадение отдельных слов запроса
            for word in query_words:
                if len(word) < 2:
                    continue
                if word in doc_text:
                    score += 3
                for kw in keywords:
                    if word in kw or kw in word:
                        score += 2
            
            # Совпадение ключевых слов
            for kw in keywords:
                if kw in query_lower:
                    score += 4
            
            if score > 0:
                results.append({
                    'doc': doc,
                    'category': category,
                    'cat_info': cat_info,
                    'index': idx,
                    'score': score
                })
    
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:7]  # максимум 7 результатов

# ─────────────────────────────────────────
# ОБРАБОТЧИКИ КОМАНД
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 Образцы заявлений", callback_data='cat_zayavleniya')],
        [InlineKeyboardButton("📄 Справки и формы", callback_data='cat_spravki')],
        [InlineKeyboardButton("📅 Графики и расписания", callback_data='cat_grafiki')],
        [InlineKeyboardButton("📋 Инструкции", callback_data='cat_instruktsii')],
        [InlineKeyboardButton("🔍 Поиск документов", callback_data='search_start')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info'),
         InlineKeyboardButton("📞 Контакты", callback_data='contacts')],
        [InlineKeyboardButton("✍️ Оставить отзыв", callback_data='feedback_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот Управления кадров и делопроизводства УрГЮУ имени В.Ф. Яковлева. "
        f"Помогу получить необходимые документы и образцы.\n\n"
        f"Выберите нужную категорию или воспользуйтесь 🔍 поиском:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Справка по использованию бота*\n\n"
        "*Доступные команды:*\n"
        "/start — Запустить бота и открыть главное меню\n"
        "/search — Поиск документов по ключевым словам\n"
        "/feedback — Оставить отзыв о работе бота\n"
        "/reviews — Просмотр отзывов _(только для администраторов)_\n"
        "/help — Показать эту справку\n\n"
        "*Как пользоваться поиском:*\n"
        "Нажмите 🔍 Поиск или введите /search, затем напишите что ищете.\n"
        "Например: _«справка о доходах»_, _«заявление на отпуск»_, _«график 2026»_",
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# ПОИСК — ConversationHandler
# ─────────────────────────────────────────

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Поиск документов*\n\n"
        "Введите ключевые слова для поиска.\n"
        "Например: _«заявление на отпуск»_, _«справка доход»_, _«график 2026»_\n\n"
        "Или нажмите /cancel для отмены.",
        parse_mode='Markdown'
    )
    return WAITING_SEARCH

async def search_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 *Поиск документов*\n\n"
        "Введите ключевые слова для поиска.\n"
        "Например: _«заявление на отпуск»_, _«справка доход»_, _«график 2026»_\n\n"
        "Или нажмите /cancel для отмены.",
        parse_mode='Markdown'
    )
    return WAITING_SEARCH

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    if not query_text:
        await update.message.reply_text("Пожалуйста, введите текст для поиска.")
        return WAITING_SEARCH

    results = search_documents(query_text)

    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main_msg')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if not results:
        await update.message.reply_text(
            f"🔍 По запросу *«{query_text}»* ничего не найдено.\n\n"
            "Попробуйте другие ключевые слова или выберите категорию вручную.\n\n"
            "/start — открыть главное меню",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        lines = [f"🔍 Результаты поиска по запросу *«{query_text}»*:\n"]
        for i, r in enumerate(results, 1):
            doc = r['doc']
            cat_icon = r['cat_info'].get('icon', '📄')
            lines.append(
                f"{i}. {cat_icon} [{doc['name']}]({doc['url']})\n"
                f"   _{doc['description']}_\n"
            )
        lines.append("\nНажмите на название документа, чтобы открыть его.")
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=reply_markup
        )

    return ConversationHandler.END

# ─────────────────────────────────────────
# ОТЗЫВЫ — ConversationHandler
# ─────────────────────────────────────────

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✍️ *Оставить отзыв*\n\n"
        "Напишите ваш отзыв о работе бота. Это поможет нам стать лучше!\n\n"
        "Или нажмите /cancel для отмены.",
        parse_mode='Markdown'
    )
    return WAITING_FEEDBACK

async def feedback_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✍️ *Оставить отзыв*\n\n"
        "Напишите ваш отзыв о работе бота. Это поможет нам стать лучше!\n\n"
        "Или нажмите /cancel для отмены.",
        parse_mode='Markdown'
    )
    return WAITING_FEEDBACK

async def receive_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user

    sentiment = analyze_sentiment(text)
    feedback_entry = {
        'id': len(load_feedbacks()) + 1,
        'user_id': user.id,
        'username': user.username or '',
        'first_name': user.first_name or '',
        'text': text,
        'sentiment': sentiment,
        'date': datetime.now().isoformat()
    }
    save_feedback(feedback_entry)

    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main_msg')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ Спасибо за ваш отзыв! Мы обязательно его учтём.\n\n"
        "/start — вернуться в главное меню",
        reply_markup=reply_markup
    )

    # Уведомление администраторам
    if ADMIN_IDS:
        admin_text = (
            f"📬 *Новый отзыв #{feedback_entry['id']}*\n\n"
            f"👤 Пользователь: {user.first_name} (@{user.username or 'нет'})\n"
            f"🕐 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"💬 Текст:\n_{text}_\n\n"
            f"📊 Сентимент: {sentiment['emoji']} *{sentiment['label']}*\n"
            f"Уверенность: {sentiment['confidence']}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, admin_text, parse_mode='Markdown')
            except Exception as e:
                logger.warning(f"Не удалось уведомить администратора {admin_id}: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Действие отменено.\n/start — открыть главное меню"
    )
    return ConversationHandler.END

# ─────────────────────────────────────────
# КОМАНДА ПРОСМОТРА ОТЗЫВОВ (только для админов)
# ─────────────────────────────────────────

async def reviews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    feedbacks = load_feedbacks()
    if not feedbacks:
        await update.message.reply_text("📭 Отзывов пока нет.")
        return

    # Статистика
    total = len(feedbacks)
    sentiments = [f['sentiment']['label'] for f in feedbacks]
    pos = sentiments.count('положительный')
    neg = sentiments.count('отрицательный')
    neu = sentiments.count('нейтральный')
    mix = sentiments.count('смешанный')

    stats = (
        f"📊 *Статистика отзывов*\n\n"
        f"Всего отзывов: *{total}*\n"
        f"😊 Положительных: *{pos}* ({round(pos/total*100)}%)\n"
        f"😔 Отрицательных: *{neg}* ({round(neg/total*100)}%)\n"
        f"😐 Нейтральных: *{neu}* ({round(neu/total*100)}%)\n"
        f"😶 Смешанных: *{mix}* ({round(mix/total*100)}%)\n"
        f"\n*Последние 5 отзывов:*\n"
    )

    recent = feedbacks[-5:][::-1]
    review_lines = []
    for fb in recent:
        s = fb['sentiment']
        date_str = fb['date'][:10]
        review_lines.append(
            f"\n#{fb['id']} | {date_str} | {s['emoji']} {s['label']}\n"
            f"👤 {fb['first_name']}: _{fb['text'][:120]}{'...' if len(fb['text']) > 120 else ''}_"
        )

    await update.message.reply_text(
        stats + "\n".join(review_lines),
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# INLINE КНОПКИ
# ─────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('cat_'):
        category = query.data.replace('cat_', '')
        await show_category_documents(query, category)
    elif query.data.startswith('doc_'):
        parts = query.data.split('_', 2)
        category = parts[1]
        doc_index = int(parts[2])
        await send_document(query, category, doc_index)
    elif query.data == 'search_start':
        return await search_start_callback(update, context)
    elif query.data == 'feedback_start':
        return await feedback_start_callback(update, context)
    elif query.data == 'info':
        await show_info(query)
    elif query.data == 'contacts':
        await show_contacts(query)
    elif query.data == 'back_to_main':
        await show_main_menu(query)
    elif query.data == 'back_to_main_msg':
        keyboard = [
            [InlineKeyboardButton("📝 Образцы заявлений", callback_data='cat_zayavleniya')],
            [InlineKeyboardButton("📄 Справки и формы", callback_data='cat_spravki')],
            [InlineKeyboardButton("📅 Графики и расписания", callback_data='cat_grafiki')],
            [InlineKeyboardButton("📋 Инструкции", callback_data='cat_instruktsii')],
            [InlineKeyboardButton("🔍 Поиск документов", callback_data='search_start')],
            [InlineKeyboardButton("ℹ️ Информация", callback_data='info'),
             InlineKeyboardButton("📞 Контакты", callback_data='contacts')],
            [InlineKeyboardButton("✍️ Оставить отзыв", callback_data='feedback_start')]
        ]
        await query.message.reply_text(
            "🏛️ *Главное меню*\n\nВыберите нужную категорию документов:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    elif query.data.startswith('back_to_cat_'):
        category = query.data.replace('back_to_cat_', '')
        await show_category_documents(query, category)

async def show_category_documents(query, category):
    if category not in DOCUMENTS:
        await query.edit_message_text("❌ Категория не найдена")
        return
    category_info = DOCUMENT_CATEGORIES.get(category, {})
    documents = DOCUMENTS[category]
    keyboard = []
    for idx, doc in enumerate(documents):
        keyboard.append([InlineKeyboardButton(
            f"📎 {doc['name']}",
            callback_data=f'doc_{category}_{idx}'
        )])
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')])
    await query.edit_message_text(
        f"{category_info.get('icon', '📄')} {category_info.get('name', 'Документы')}\n\nВыберите нужный документ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_document(query, category, doc_index):
    if category not in DOCUMENTS or doc_index >= len(DOCUMENTS[category]):
        await query.edit_message_text("❌ Документ не найден")
        return
    doc = DOCUMENTS[category][doc_index]
    keyboard = [[InlineKeyboardButton("◀️ Назад к списку", callback_data=f'back_to_cat_{category}')]]
    message_text = (
        f"📄 *{doc['name']}*\n\n"
        f"📝 {doc['description']}\n\n"
        f"🔗 [Открыть документ]({doc['url']})\n\n"
        f"_Нажмите на ссылку выше, чтобы открыть или скачать документ_"
    )
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown',
        disable_web_page_preview=False
    )

async def show_info(query):
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]]
    await query.edit_message_text(
        "ℹ️ *Информация о боте*\n\n"
        "Этот бот предоставляет доступ к кадровым документам:\n\n"
        "📝 Образцы заявлений для сотрудников\n"
        "📄 Справки и формы\n"
        "📅 Графики работы и расписания\n"
        "📋 Инструкции и регламенты\n\n"
        "🔍 Поиск по ключевым словам\n"
        "✍️ Возможность оставить отзыв\n\n"
        "Все документы актуальны и соответствуют требованиям вуза.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_contacts(query):
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]]
    await query.edit_message_text(
        "📞 *Контакты отдела кадров*\n\n"
        "📧 Email: uk@usla.ru\n"
        "☎️ Телефон: +7 (343) 374-42-51\n"
        "🏢 Кабинет: 117, Главный учебный корпус (Комсомольская, 21)\n"
        "⏰ Часы работы: Пн-Пт 9:00–11:00; 14:00–17:00\n\n"
        "По всем вопросам обращайтесь в отдел кадров.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_main_menu(query):
    keyboard = [
        [InlineKeyboardButton("📝 Образцы заявлений", callback_data='cat_zayavleniya')],
        [InlineKeyboardButton("📄 Справки и формы", callback_data='cat_spravki')],
        [InlineKeyboardButton("📅 Графики и расписания", callback_data='cat_grafiki')],
        [InlineKeyboardButton("📋 Инструкции", callback_data='cat_instruktsii')],
        [InlineKeyboardButton("🔍 Поиск документов", callback_data='search_start')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info'),
         InlineKeyboardButton("📞 Контакты", callback_data='contacts')],
        [InlineKeyboardButton("✍️ Оставить отзыв", callback_data='feedback_start')]
    ]
    await query.edit_message_text(
        "🏛️ *Главное меню*\n\nВыберите нужную категорию документов:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────

async def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

    application = Application.builder().token(TOKEN).build()

    # ConversationHandler для поиска
    search_conv = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_command),
            CallbackQueryHandler(search_start_callback, pattern='^search_start$')
        ],
        states={
            WAITING_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    # ConversationHandler для отзывов
    feedback_conv = ConversationHandler(
        entry_points=[
            CommandHandler("feedback", feedback_command),
            CallbackQueryHandler(feedback_start_callback, pattern='^feedback_start$')
        ],
        states={
            WAITING_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_feedback)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    application.add_handler(search_conv)
    application.add_handler(feedback_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reviews", reviews_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Бот отдела кадров запущен...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
