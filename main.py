import logging
import aiohttp
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Категории документов
DOCUMENT_CATEGORIES = {
    'zayavleniya': {
        'name': '📝 Образцы заявлений',
        'icon': '📝'
    },
    'spravki': {
        'name': '📄 Справки и формы',
        'icon': '📄'
    },
    'grafiki': {
        'name': '📅 Графики и расписания',
        'icon': '📅'
    },
    'instruktsii': {
        'name': '📋 Инструкции',
        'icon': '📋'
    }
}

# Документы с прямыми ссылками на сайт
DOCUMENTS = {
    'zayavleniya': [
        {
            'name': 'Заявление на отпуск',
            'url': 'https://www.usla.ru/upload/main/f46/f4614c19fe04a24ec367ea54639eed94.pdf',
            'description': 'Образец заявления на отпуск'
        },
        {
            'name': 'Образец заявления на отпуск',
            'url': 'https://www.usla.ru/upload/main/6ce/6ce9f60d05ed22aa08e2e91a3219509e.pdf',
            'description': 'Заполненный образец заявления на отпуск'
        },
        {
            'name': 'Образец представления к поощрению',
            'url': 'https://www.usla.ru/upload/main/2b4/2b446ce2a330b738054dc3f8d981d934.pdf',
            'description': 'Образец заявления об увольнении по собственному желанию'
        },
        {
            'name': 'Заявка на подбор',
            'url': 'https://www.usla.ru/upload/main/ce9/ce919943a93e27c4b2e2ef699ab8044e.docx',
            'description': 'Образец заявки на подбор'
        }
    ],
    'spravki': [
        {
            'name': 'Справка с места работы',
            'url': 'https://www.usla.ru/upload/main/example5.pdf',
            'description': 'Справка, подтверждающая трудовые отношения'
        },
        {
            'name': 'Справка о доходах',
            'url': 'https://www.usla.ru/upload/main/example6.pdf',
            'description': 'Справка о доходах для предоставления по месту требования'
        }
    ],
    'grafiki': [
        {
            'name': 'График отпусков 2025',
            'url': 'https://www.usla.ru/upload/main/example7.pdf',
            'description': 'График отпусков на 2025 год'
        },
        {
            'name': 'График отпусков 2026',
            'url': 'https://www.usla.ru/upload/main/example8.pdf',
            'description': 'График отпусков на 2026 год'
        }
    ],
    'instruktsii': [
        {
            'name': 'Инструкция по оформлению документов',
            'url': 'https://www.usla.ru/upload/main/example9.pdf',
            'description': 'Порядок оформления кадровых документов'
        }
    ]
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие и главное меню"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📝 Образцы заявлений", callback_data='cat_zayavleniya')],
        [InlineKeyboardButton("📄 Справки и формы", callback_data='cat_spravki')],
        [InlineKeyboardButton("📅 Графики и расписания", callback_data='cat_grafiki')],
        [InlineKeyboardButton("📋 Инструкции", callback_data='cat_instruktsii')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info'),
         InlineKeyboardButton("📞 Контакты", callback_data='contacts')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот Управления кадров и делопроизводства УрГЮУ имени В.Ф. Яковлева. Помогу получить необходимые документы и образцы.\n\n"
        f"Выберите нужную категорию:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
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
    elif query.data == 'info':
        await show_info(query)
    elif query.data == 'contacts':
        await show_contacts(query)
    elif query.data == 'back_to_main':
        await show_main_menu(query)
    elif query.data.startswith('back_to_cat_'):
        category = query.data.replace('back_to_cat_', '')
        await show_category_documents(query, category)

async def show_category_documents(query, category):
    """Показать документы выбранной категории"""
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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"{category_info.get('icon', '📄')} {category_info.get('name', 'Документы')}\n\n"
        f"Выберите нужный документ:",
        reply_markup=reply_markup
    )

async def send_document(query, category, doc_index):
    """Отправить документ пользователю"""
    if category not in DOCUMENTS or doc_index >= len(DOCUMENTS[category]):
        await query.edit_message_text("❌ Документ не найден")
        return
    
    doc = DOCUMENTS[category][doc_index]
    
    # Отправляем сообщение с информацией и ссылкой
    keyboard = [[InlineKeyboardButton("◀️ Назад к списку", callback_data=f'back_to_cat_{category}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        f"📄 **{doc['name']}**\n\n"
        f"📝 {doc['description']}\n\n"
        f"🔗 [Открыть документ]({doc['url']})\n\n"
        f"_Нажмите на ссылку выше, чтобы открыть или скачать документ_"
    )
    
    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=False
    )
    
    # Опционально: скачать и отправить файл напрямую
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(doc['url']) as response:
                if response.status == 200:
                    file_data = await response.read()
                    filename = doc['name'].replace(' ', '_') + '.pdf'
                    await query.message.reply_document(
                        document=file_data,
                        filename=filename,
                        caption=f"📄 {doc['name']}\n{doc['description']}"
                    )
    except Exception as e:
        logger.error(f"Ошибка при скачивании документа: {e}")
    """

async def show_info(query):
    """Показать информацию"""
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "ℹ️ **Информация о боте**\n\n"
        "Этот бот предоставляет доступ к кадровым документам:\n\n"
        "📝 Образцы заявлений для сотрудников\n"
        "📄 Справки и формы\n"
        "📅 Графики работы и расписания\n"
        "📋 Инструкции и регламенты\n\n"
        "Все документы актуальны и соответствуют требованиям вуза.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_contacts(query):
    """Показать контакты"""
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📞 **Контакты отдела кадров**\n\n"
        "📧 Email: uk@usla.ru\n"
        "☎️ Телефон: +7 (343) 374-42-51\n"
        "🏢 Кабинет: 117, Главный учебный корпус (Комсомольская, 21)\n"
        "⏰ Часы работы: Пн-Пт 9:00-11:00; 14:00-17:00\n\n"
        "По всем вопросам обращайтесь в отдел кадров.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_main_menu(query):
    """Вернуться в главное меню"""
    keyboard = [
        [InlineKeyboardButton("📝 Образцы заявлений", callback_data='cat_zayavleniya')],
        [InlineKeyboardButton("📄 Справки и формы", callback_data='cat_spravki')],
        [InlineKeyboardButton("📅 Графики и расписания", callback_data='cat_grafiki')],
        [InlineKeyboardButton("📋 Инструкции", callback_data='cat_instruktsii')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info'),
         InlineKeyboardButton("📞 Контакты", callback_data='contacts')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🏛️ **Главное меню**\n\nВыбери нужную категорию документов:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "🤖 **Справка по использованию бота**\n\n"
        "**Доступные команды:**\n"
        "/start - Запустить бота и открыть главное меню\n"
        "/help - Показать эту справку\n\n"
        "**Как пользоваться:**\n"
        "1. Выберите категорию документов\n"
        "2. Выберите нужный документ из списка\n"
        "3. Нажмите на ссылку для открытия документа\n\n"
        "Все документы доступны онлайн на официальном сайте вуза.",
        parse_mode='Markdown'
    )

def main():
    """Запуск бота"""

    # Токен берётся из переменной окружения (Render → Environment Variables)
    TOKEN = os.environ.get("BOT_TOKEN")

    if not TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запускаем бота (polling подходит для Render)
    logger.info("Бот отдела кадров запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
