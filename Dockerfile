FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY usla_bot.py .

# Том для хранения данных отзывов (чтобы они не терялись при перезапуске)
VOLUME ["/app/data"]

# Переменные окружения (значения передаются при запуске)
ENV BOT_TOKEN=""
ENV ADMIN_IDS=""
ENV FEEDBACK_FILE="/app/data/feedbacks.json"

CMD ["python", "usla_bot.py"]
