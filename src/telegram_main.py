import time
import sys
import os
from typing import Dict, Any, Optional

# Добавляем путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import telegram_input
import telegram_output
import url_queue
import yt_processor
import log_mod

def load_config():
    """Загружаем конфигурацию"""
    import yaml
    from pathlib import Path
    
    config_path = Path(__file__).parent.parent / "config_prod" / "app.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def send_telegram_summaries(config: Dict[str, Any], chat_id: int, summaries: Dict[str, str], 
                           run_id: int, log_func=None) -> bool:
    """
    Отправляет 4 саммари в Telegram с задержкой
    
    Args:
        config: конфигурация приложения
        chat_id: ID чата для отправки
        summaries: словарь с саммари (short, middle, full, resources)
        run_id: номер записи
        log_func: функция логирования
        
    Returns:
        True если все сообщения отправлены успешно
    """
    success = True
    
    # Отправляем короткое саммари
    short_summary = summaries.get('short', '')
    if short_summary:
        short_msg = f"<b>Краткое саммари:</b>\n\n{short_summary}"
        if not telegram_output.send_telegram_message(config, chat_id, short_msg, log_func):
            success = False
    
    # Отправляем среднее саммари
    middle_summary = summaries.get('middle', '')
    if middle_summary:
        # Разбиваем на части если нужно
        middle_parts = telegram_output.split_long_message(middle_summary, max_length=4000)
        for i, part in enumerate(middle_parts):
            if len(middle_parts) > 1:
                middle_msg = f"<b>Среднее саммари (часть {i+1}/{len(middle_parts)}):</b>\n\n{part}"
            else:
                middle_msg = f"<b>Среднее саммари:</b>\n\n{part}"
            if not telegram_output.send_telegram_message(config, chat_id, middle_msg, log_func):
                success = False
    
    # Отправляем полное саммари
    full_summary = summaries.get('full', '')
    if full_summary:
        # Разбиваем на части если нужно
        full_parts = telegram_output.split_long_message(full_summary, max_length=4000)
        for i, part in enumerate(full_parts):
            if len(full_parts) > 1:
                full_msg = f"<b>Полное саммари (часть {i+1}/{len(full_parts)}):</b>\n\n{part}"
            else:
                full_msg = f"<b>Полное саммари:</b>\n\n{part}"
            if not telegram_output.send_telegram_message(config, chat_id, full_msg, log_func):
                success = False
    
    # Отправляем ресурсы
    resources = summaries.get('resources', '')
    if resources:
        resources_msg = f"<b>Ресурсы:</b>\n\n{resources}"
        if not telegram_output.send_telegram_message(config, chat_id, resources_msg, log_func):
            success = False
    
    # Отправляем сообщение о завершении
    final_msg = f"✅ Все саммари отправлены!"
    telegram_output.send_telegram_message(config, chat_id, final_msg, log_func)
    
    if log_func:
        if success:
            log_func("INFO", "telegram_main", "Все саммари отправлены успешно")
        else:
            log_func("ERROR", "telegram_main", "Ошибка отправки некоторых саммари")
    
    return success

def process_single_url(config: Dict[str, Any], log_func=None) -> bool:
    """
    Обрабатывает одну ссылку из очереди
    
    Args:
        config: конфигурация приложения
        log_func: функция логирования
        
    Returns:
        True если есть что обрабатывать и обработка запущена
    """
    # Получаем следующую задачу из очереди
    task = url_queue.url_queue.get_next_url()
    
    if not task:
        return False  # Очередь пуста
    
    if log_func:
        log_func("INFO", "telegram_main", "Начинаем обработку задачи", 
                task_id=task.task_id, url=task.url, source=task.source)
    
    try:
        # Обрабатываем URL через универсальный процессор
        result = yt_processor.process_youtube_url(task.url, config, log_func)
        
        # Отправляем результаты обработки
        if result['success']:
            # Отправляем подтверждение завершения
            final_msg = f"✅ Обработка завершена! Данные сохранены в Notion"
            telegram_output.send_telegram_message(config, task.source, final_msg, log_func)
            
            # Отправляем саммари в Telegram
            summaries = result.get('summaries', {})
            if summaries:
                send_telegram_summaries(config, task.source, summaries, 0, log_func)
        else:
            # Отправляем сообщение об ошибке
            error_msg = f"❌ Ошибка обработки: {result.get('error', 'Неизвестная ошибка')}"
            telegram_output.send_telegram_message(config, task.source, error_msg, log_func)
        
        # Отмечаем задачу как завершенную
        url_queue.url_queue.mark_completed(task.task_id)
        
        if log_func:
            if result['success']:
                log_func("INFO", "telegram_main", "Задача обработана успешно", 
                        task_id=task.task_id, run_id=result.get('run_id'))
            else:
                log_func("ERROR", "telegram_main", "Ошибка обработки задачи", 
                        task_id=task.task_id, error=result.get('error'))
        
        return True
        
    except Exception as e:
        # Отмечаем задачу как завершенную даже при ошибке
        url_queue.url_queue.mark_completed(task.task_id)
        
        # Отправляем сообщение об ошибке
        error_msg = f"❌ Ошибка обработки: {str(e)}"
        telegram_output.send_telegram_message(config, task.source, error_msg, log_func)
        
        if log_func:
            log_func("ERROR", "telegram_main", "Исключение при обработке задачи", 
                    task_id=task.task_id, error=str(e))
        
        return True

def telegram_worker_loop(config: Dict[str, Any], log_func=None):
    """
    Основной цикл обработки сообщений из Telegram
    
    Args:
        config: конфигурация приложения
        log_func: функция логирования
    """
    if log_func:
        log_func("INFO", "telegram_main", "Запуск Telegram worker loop")
    
    # Получаем имя бота из конфигурации или используем значение по умолчанию
    bot_username = config.get('telegram', {}).get('bot_username', '@YTDigest2Bot')
    
    print("🤖 YT_Sum Telegram Bot запущен!")
    print(f"📱 Бот: {bot_username}")
    print("📋 Отправьте YouTube ссылку для обработки")
    print("📊 Максимум в очереди: 5 ссылок")
    print()
    
    last_update_id = 0
    
    while True:
        try:
            # Проверяем новые сообщения
            updates = telegram_input.get_telegram_updates(config, offset=last_update_id + 1)
            
            if not updates.get("ok"):
                time.sleep(1)
                continue
            
            # Обрабатываем каждое обновление
            for update in updates.get("result", []):
                update_id = update.get("update_id", 0)
                
                # Убедимся, что мы не обрабатываем одно и то же обновление дважды
                if update_id <= last_update_id:
                    continue
                
                last_update_id = update_id
                
                message = update.get("message", {})
                if not message.get("text"):
                    continue
                
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text").strip()
                user = message.get("from", {})
                username = user.get("username", "unknown")
                
                if log_func:
                    log_func("INFO", "telegram_main", "Получено сообщение", 
                            chat_id=chat_id, text=text, username=username)
                
                # Валидируем YouTube URL
                if not yt_processor.validate_youtube_url(text):
                    error_msg = "❌ Введите корректную YouTube ссылку\n\nПример: https://www.youtube.com/watch?v=..."
                    telegram_output.send_telegram_message(config, chat_id, error_msg, log_func)
                    continue
                
                # Добавляем URL в очередь
                queue_result = url_queue.url_queue.add_url(text, source=chat_id)
                
                if queue_result['success']:
                    # URL добавлен в очередь успешно - отправляем одно сообщение с подтверждением
                    video_id = yt_processor.extract_video_id(text)
                    confirm_msg = f"📥 Принята ссылка: {text}\n🆔 Видео: {video_id}\n📍 Позиция в очереди: {queue_result['position']}\n\n⏳ Обработка начнется в ближайшее время..."
                    
                    telegram_output.send_telegram_message(config, chat_id, confirm_msg, log_func)
                    
                    if log_func:
                        log_func("INFO", "telegram_main", "URL добавлен в очередь", 
                                task_id=queue_result['task_id'], position=queue_result['position'])
                else:
                    # Очередь переполнена
                    error_msg = f"🚫 {queue_result['message']}\n⏳ Попробуйте позже"
                    telegram_output.send_telegram_message(config, chat_id, error_msg, log_func)
            
            # Обрабатываем задачи из очереди (только одну задачу за итерацию)
            # Проверяем, есть ли задачи в очереди, и если есть, обрабатываем одну
            queue_status = url_queue.url_queue.get_queue_status()
            if queue_status['queue_size'] > 0:
                if log_func:
                    log_func("INFO", "telegram_main", "Обрабатываем задачу из очереди")
                
                # Обрабатываем задачу
                process_single_url(config, log_func)
            
            # Небольшая пауза перед следующей итерацией
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            if log_func:
                log_func("INFO", "telegram_main", "Получен сигнал завершения")
            break
        except Exception as e:
            if log_func:
                log_func("ERROR", "telegram_main", "Ошибка в основном цикле", error=str(e))
            time.sleep(1)  # Пауза при ошибке