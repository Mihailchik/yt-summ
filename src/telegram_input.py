import requests
import json
import time
from typing import Optional, Dict, Any


def get_telegram_updates(config: Dict[str, Any], offset: int = 0) -> Dict[str, Any]:
    """
    Получает обновления от Telegram Bot API

    Args:
        config: конфигурация с telegram.bot_token
        offset: offset для получения новых сообщений

    Returns:
        Dict с обновлениями или пустой dict при ошибке
    """
    bot_token = config.get('telegram', {}).get('bot_token')
    if not bot_token:
        return {"ok": False, "error": "No bot token configured"}

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {
        "offset": offset,
        "timeout": 30,
        "allowed_updates": ["message"]
    }

    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_last_message(config: Dict[str, Any], log_func=None) -> Optional[Dict[str, Any]]:
    """
    Получает последнее сообщение из Telegram

    Args:
        config: конфигурация приложения
        log_func: функция для логирования

    Returns:
        Dict с данными сообщения или None
        Формат: {
            'chat_id': int,
            'message_id': int,
            'text': str,
            'user_id': int,
            'username': str
        }
    """
    if log_func:
        log_func("INFO", "telegram_input", "Проверяем новые сообщения в Telegram")

    updates = get_telegram_updates(config)

    if not updates.get("ok"):
        if log_func:
            log_func("ERROR", "telegram_input", "Ошибка получения обновлений", error=updates.get("error"))
        return None

    result = updates.get("result", [])
    if not result:
        return None

    # Берем последнее сообщение
    last_update = result[-1]
    message = last_update.get("message", {})

    if not message.get("text"):
        return None

    chat_id = message.get("chat", {}).get("id")
    user = message.get("from", {})

    message_data = {
        "chat_id": chat_id,
        "message_id": message.get("message_id"),
        "text": message.get("text"),
        "user_id": user.get("id"),
        "username": user.get("username", "unknown")
    }

    if log_func:
        log_func("INFO", "telegram_input", "Получено сообщение",
                chat_id=chat_id, text=message_data["text"], username=message_data["username"])

    return message_data


def wait_for_message(config: Dict[str, Any], log_func=None, timeout: int = 60) -> Optional[Dict[str, Any]]:
    """
    Ждет новое сообщение в Telegram с таймаутом

    Args:
        config: конфигурация приложения
        log_func: функция для логирования
        timeout: максимальное время ожидания в секундах

    Returns:
        Dict с данными сообщения или None при таймауте
    """
    if log_func:
        log_func("INFO", "telegram_input", f"Ожидаем сообщение в Telegram (таймаут: {timeout}с)")

    start_time = time.time()
    last_update_id = 0

    while time.time() - start_time < timeout:
        updates = get_telegram_updates(config, offset=last_update_id + 1)

        if not updates.get("ok"):
            time.sleep(1)
            continue

        result = updates.get("result", [])

        for update in result:
            last_update_id = update.get("update_id", last_update_id)
            message = update.get("message", {})

            if message.get("text"):
                chat_id = message.get("chat", {}).get("id")
                user = message.get("from", {})

                message_data = {
                    "chat_id": chat_id,
                    "message_id": message.get("message_id"),
                    "text": message.get("text"),
                    "user_id": user.get("id"),
                    "username": user.get("username", "unknown")
                }

                if log_func:
                    log_func("INFO", "telegram_input", "Получено новое сообщение",
                            chat_id=chat_id, text=message_data["text"])

                return message_data

        time.sleep(1)

    if log_func:
        log_func("WARNING", "telegram_input", "Таймаут ожидания сообщения")

    return None
