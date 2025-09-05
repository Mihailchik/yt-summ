import requests
import json
from typing import Dict, Any, Optional, List


def send_telegram_message(config: Dict[str, Any], chat_id: int, text: str, log_func=None) -> bool:
    """
    Отправляет сообщение в Telegram
    
    Args:
        config: конфигурация с telegram.bot_token
        chat_id: ID чата для отправки
        text: текст сообщения
        log_func: функция для логирования
        
    Returns:
        True если отправлено успешно, False при ошибке
    """
    bot_token = config.get('telegram', {}).get('bot_token')
    if not bot_token:
        if log_func:
            log_func("ERROR", "telegram_output", "Отсутствует bot_token в конфигурации")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"  # поддержка HTML форматирования
    }
    
    try:
        if log_func:
            log_func("INFO", "telegram_output", "Отправляем сообщение", 
                    chat_id=chat_id, text_preview=text[:50])
        
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        
        if result.get("ok"):
            if log_func:
                log_func("INFO", "telegram_output", "Сообщение отправлено успешно", 
                        message_id=result.get("result", {}).get("message_id"))
            return True
        else:
            if log_func:
                log_func("ERROR", "telegram_output", "Ошибка отправки сообщения", 
                        error=result.get("description"))
            return False
            
    except Exception as e:
        if log_func:
            log_func("ERROR", "telegram_output", "Исключение при отправке", error=str(e))
        return False


def send_telegram_messages(config: Dict[str, Any], chat_id: int, texts: List[str], log_func=None) -> bool:
    """
    Отправляет несколько сообщений в Telegram
    
    Args:
        config: конфигурация с telegram.bot_token
        chat_id: ID чата для отправки
        texts: список текстов сообщений
        log_func: функция для логирования
        
    Returns:
        True если все сообщения отправлены успешно, False при ошибке
    """
    success = True
    for i, text in enumerate(texts):
        if not send_telegram_message(config, chat_id, text, log_func):
            success = False
            if log_func:
                log_func("ERROR", "telegram_output", f"Ошибка отправки сообщения {i+1}/{len(texts)}")
        # Небольшая задержка между сообщениями
        import time
        time.sleep(0.1)
    return success


def split_long_message(text: str, max_length: int = 4000) -> List[str]:
    """
    Разбивает длинное сообщение на части
    
    Args:
        text: текст для разбиения
        max_length: максимальная длина одной части
        
    Returns:
        Список частей сообщения
    """
    if len(text) <= max_length:
        return [text]
    
    # Разбиваем на части
    parts = []
    current_part = ""
    
    # Разбиваем по строкам для сохранения структуры
    lines = text.split('\n')
    
    for line in lines:
        # Если добавление строки превысит лимит, сохраняем текущую часть
        if len(current_part) + len(line) + 1 > max_length and current_part:
            parts.append(current_part.rstrip('\n'))  # Убираем лишний перевод строки в конце
            current_part = line
        else:
            if current_part:
                current_part += '\n' + line
            else:
                current_part = line
    
    # Добавляем последнюю часть
    if current_part:
        parts.append(current_part)
    
    # Если части все еще слишком длинные, разбиваем по символам
    final_parts = []
    for part in parts:
        if len(part) <= max_length:
            final_parts.append(part)
        else:
            # Разбиваем по символам
            for i in range(0, len(part), max_length):
                final_parts.append(part[i:i+max_length])
    
    return final_parts


def send_confirmation_message(config: Dict[str, Any], chat_id: int, original_text: str, log_func=None) -> bool:
    """
    Отправляет сообщение-подтверждение о начале обработки
    
    Args:
        config: конфигурация приложения
        chat_id: ID чата
        original_text: оригинальный текст сообщения
        log_func: функция для логирования
        
    Returns:
        True если отправлено успешно
    """
    confirmation_text = f"Обрабатываем - {original_text}"
    return send_telegram_message(config, chat_id, confirmation_text, log_func)


def send_result_message(config: Dict[str, Any], chat_id: int, original_text: str, log_func=None) -> bool:
    """
    Отправляет сообщение с результатом обработки
    
    Args:
        config: конфигурация приложения
        chat_id: ID чата
        original_text: оригинальный текст сообщения
        log_func: функция для логирования
        
    Returns:
        True если отправлено успешно
    """
    result_text = f"{original_text} обработан"
    return send_telegram_message(config, chat_id, result_text, log_func)


def send_formatted_message(config: Dict[str, Any], chat_id: int, title: str, content: str, log_func=None) -> bool:
    """
    Отправляет форматированное сообщение с заголовком
    
    Args:
        config: конфигурация приложения
        chat_id: ID чата
        title: заголовок сообщения
        content: содержимое сообщения
        log_func: функция для логирования
        
    Returns:
        True если отправлено успешно
    """
    # Telegram имеет лимит 4096 символов на сообщение
    max_length = 4000
    
    formatted_text = f"<b>{title}</b>\n\n{content}"
    
    # Если сообщение слишком длинное, разбиваем на части
    if len(formatted_text) > max_length:
        # Разбиваем содержимое на части
        content_parts = split_long_message(content, max_length - len(f"<b>{title}</b>\n\n") - 20)
        
        # Отправляем каждую часть как отдельное сообщение
        success = True
        for i, part in enumerate(content_parts):
            if len(content_parts) > 1:
                part_title = f"{title} (часть {i+1}/{len(content_parts)})"
            else:
                part_title = title
            
            formatted_part = f"<b>{part_title}</b>\n\n{part}"
            if not send_telegram_message(config, chat_id, formatted_part, log_func):
                success = False
        
        return success
    
    return send_telegram_message(config, chat_id, formatted_text, log_func)


def send_error_message(config: Dict[str, Any], chat_id: int, error_text: str, log_func=None) -> bool:
    """
    Отправляет сообщение об ошибке
    
    Args:
        config: конфигурация приложения
        chat_id: ID чата
        error_text: текст ошибки
        log_func: функция для логирования
        
    Returns:
        True если отправлено успешно
    """
    error_message = f"❌ Ошибка: {error_text}"
    return send_telegram_message(config, chat_id, error_message, log_func)