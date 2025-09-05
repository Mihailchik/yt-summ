# Используем официальный образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем директорию для логов
RUN mkdir -p logs

# Открываем порт (если будет нужен для веб-интерфейса)
EXPOSE 8000

# Команда для запуска приложения
CMD ["python", "yt_sum_bot.py"]