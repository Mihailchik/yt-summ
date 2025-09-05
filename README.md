# YT_Sum Telegram Bot - Production Version

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Production-ready версия YT_Sum Telegram бота для обработки YouTube видео.

## О проекте

YT_Sum - это Telegram бот, который автоматизирует процесс обработки видео с YouTube. Он получает ссылки на видео, извлекает транскрипты, анализирует контент с помощью ИИ и предоставляет структурированные саммари пользователю через Telegram, а также сохраняет результаты в Notion.

## Основные компоненты

1. **Telegram бот** - принимает YouTube ссылки от пользователей
2. **Очередь обработки** - управляет потоком задач
3. **Транскрибация** - получает субтитры видео через Supadata API
4. **AI анализ** - обрабатывает текст через Google Gemini
5. **Notion интеграция** - сохраняет результаты в Notion базу данных

## Функциональность

1. Отправка YouTube ссылки боту в Telegram
2. Автоматическая обработка видео:
   - Получение транскрипта
   - AI анализ (5 этапов)
   - Сохранение в Notion
3. Отправка результатов в Telegram:
   - Короткое саммари
   - Среднее саммари
   - Полное саммари
   - Ресурсы

## Требования

- Python 3.10+
- Доступ в интернет
- Настроенные API ключи

## Установка

### Вариант 1: Использование скриптов установки

Для Windows:
```powershell
.\install.ps1
```

Для Linux/macOS:
```bash
chmod +x install.sh
./install.sh
```

### Вариант 2: Ручная установка

1. Создайте виртуальное окружение:
   ```bash
   python -m venv venv
   ```

2. Активируйте виртуальное окружение:
   ```bash
   # Windows
   .\venv\Scripts\Activate.ps1
   
   # Linux/macOS
   source venv/bin/activate
   ```

3. Установите зависимости:
   ```bash
   pip install -r requirements_prod.txt
   ```

4. Настройте конфигурацию:
   ```bash
   cp config_prod/app.yaml.example config_prod/app.yaml
   ```
   
   Отредактируйте `config_prod/app.yaml`, заполнив необходимые API ключи.

## Запуск

```bash
python yt_sum_bot.py
```

## Docker

```bash
docker build -t yt-sum-bot .
docker run -d --name yt-sum-bot yt-sum-bot
```

## Конфигурация

Конфигурация находится в `config_prod/app.yaml`:

- Telegram токен бота
- API ключи Supadata
- API ключи Google Gemini
- Настройки Notion интеграции

## Логирование

- Консоль: только ошибки (уровень ERROR)
- Файлы: все логи сохраняются в `logs/app.log`

## Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для подробностей.

## Контакты

Для вопросов и поддержки создавайте issue в этом репозитории.