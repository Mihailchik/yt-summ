import re
import time
import sys
import os
from typing import Dict, Any, Optional
from pathlib import Path
import datetime

# Добавляем путь для импорта существующих модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import log_mod
import transcribe_mod
import ai_chat
import notion_mod


def generate_run_id(video_id: str) -> int:
    """
    Генерирует уникальный run_id на основе video_id и текущего времени (минуты:секунды)
    
    Args:
        video_id: ID видео из YouTube URL
        
    Returns:
        Уникальный run_id как целое число
    """
    # Получаем текущее время
    now = datetime.datetime.now()
    
    # Извлекаем минуты и секунды
    minutes = now.minute
    seconds = now.second
    
    # Создаем строку из video_id и времени
    # Используем хеширование для получения числового значения
    time_component = minutes * 100 + seconds  # Простое представление времени как MMSS
    
    # Комбинируем video_id и время, затем хешируем
    combined = f"{video_id}_{minutes:02d}:{seconds:02d}"
    hash_value = hash(combined) & 0x7FFFFFFF  # Обеспечиваем положительное значение
    
    # Возвращаем хеш как run_id
    return hash_value


def validate_youtube_url(url: str) -> bool:
    """
    Валидирует YouTube URL используя существующую логику из input_mod.py
    
    Args:
        url: URL для проверки
        
    Returns:
        True если URL валидный YouTube адрес
    """
    if not url or not isinstance(url, str):
        return False
    
    # Паттерны YouTube URL
    youtube_patterns = [
        r'^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'^https?://(?:www\.)?youtu\.be/[\w-]+',
        r'^https?://(?:m\.)?youtube\.com/watch\?v=[\w-]+',
        r'^https?://(?:music\.)?youtube\.com/watch\?v=[\w-]+',
    ]
    
    for pattern in youtube_patterns:
        if re.match(pattern, url.strip()):
            return True
    
    return False


def extract_video_id(url: str) -> Optional[str]:
    """
    Извлекает video ID из YouTube URL
    
    Args:
        url: YouTube URL
        
    Returns:
        Video ID или None
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def process_youtube_url(url: str, config: Dict[str, Any], log_func=None) -> Dict[str, Any]:
    """
    Универсальная функция обработки YouTube URL
    Выполняет полный pipeline: транскрибация + AI обработка
    
    Args:
        url: YouTube URL для обработки
        config: конфигурация приложения
        log_func: функция логирования
        
    Returns:
        Dict с результатами обработки:
        {
            'success': bool,
            'error': str,  # если есть ошибка
            'url': str,
            'video_id': str,
            'run_id': int,
            'transcript': Dict,  # результат транскрибации
            'ai_results': Dict,  # результаты AI обработки
            'summaries': Dict,   # форматированные саммари для вывода
            'processing_time': Dict  # время обработки
        }
    """
    if log_func is None:
        log_func = lambda level, module, message, **kwargs: None

    start_time = time.time()
    processing_times = {}
    video_id = None  # Инициализируем video_id заранее
    
    try:
        # Валидация URL
        if not validate_youtube_url(url):
            return {
                'success': False,
                'error': 'Некорректный YouTube URL',
                'url': url,
                'video_id': None,
                'run_id': None,
                'transcript': None,
                'ai_results': None,
                'summaries': None,
                'processing_time': {'total': 0}
            }
        
        video_id = extract_video_id(url)
        log_func("INFO", "yt_processor", "Начинаем обработку", url=url, video_id=video_id)
        
        # Генерируем уникальный run_id
        run_id = generate_run_id(video_id) if video_id else 0
        
        # Инициализируем Notion если включен
        notion_client = None
        notion_page_id = None
        notion_config = config.get('notion', {})
        if notion_config.get('enabled', False):
            notion_client = notion_mod.init_client(config, log_func)
            if notion_client:
                notion_db_info = notion_mod.ensure_database(notion_client, config, log_func)
                if notion_db_info:
                    created_at_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    notion_page_id = notion_mod.upsert_page_for_run(
                        notion_client, notion_db_info['id'], run_id, url, None, created_at_iso, log_func
                    )
        
        # Шаг 1: Транскрибация
        log_func("INFO", "yt_processor", "Получаем транскрипт")
        transcript_start = time.time()
        
        try:
            transcript_result = transcribe_mod.fetch_transcript(url, config, log_func)
            processing_times['transcript'] = int((time.time() - transcript_start) * 1000)
            
            if not transcript_result or not transcript_result.get('content'):
                return {
                    'success': False,
                    'error': 'Ошибка в транскрибировании',
                    'url': url,
                    'video_id': video_id,
                    'run_id': None,
                    'transcript': None,
                    'ai_results': None,
                    'summaries': None,
                    'processing_time': processing_times
                }
                
        except Exception as e:
            log_func("ERROR", "yt_processor", "Ошибка транскрибации", error=str(e))
            return {
                'success': False,
                'error': 'Ошибка в транскрибировании',
                'url': url,
                'video_id': video_id,
                'run_id': None,
                'transcript': None,
                'ai_results': None,
                'summaries': None,
                'processing_time': processing_times
            }
        
        # Шаг 2: AI обработка
        log_func("INFO", "yt_processor", "Запускаем AI обработку")
        ai_start = time.time()
        
        try:
            ai_results = ai_chat.process_transcript_chat(transcript_result['content'], config, log_func)
            processing_times['ai'] = int((time.time() - ai_start) * 1000)
            
            if ai_results.get('error'):
                # AI обработка завершилась с ошибкой
                error_msg = ai_results['error'].get('detail', 'Неизвестная ошибка AI')
                log_func("ERROR", "yt_processor", "Ошибка AI обработки", error=error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'url': url,
                    'video_id': video_id,
                    'run_id': None,
                    'transcript': transcript_result,
                    'ai_results': ai_results,
                    'summaries': None,
                    'processing_time': processing_times
                }
        except Exception as e:
            log_func("ERROR", "yt_processor", "Исключение в AI обработке", error=str(e))
            return {
                'success': False,
                'error': f'Исключение в AI обработке: {str(e)}',
                'url': url,
                'video_id': video_id,
                'run_id': None,
                'transcript': transcript_result,
                'ai_results': None,
                'summaries': None,
                'processing_time': processing_times
            }
        
        # Форматируем результаты для вывода
        summaries = {
            'short': ai_results.get('short_summary', ''),
            'middle': ai_results.get('middle_summary', ''),
            'full': ai_results.get('full_summary', ''),
            'resources': '\n'.join(ai_results.get('resources', [])) if ai_results.get('resources') else ''
        }
        
        # Сохраняем в Notion если включено
        if notion_client and notion_page_id:
            try:
                # Получаем максимальную длину свойства из конфигурации
                prop_max_len = notion_config.get('prop_max_len', 1950)
                
                # Обновляем страницу с результатами, используя функцию с обработкой переполнения
                # Шорт саммари
                notion_mod.set_rich_text(notion_client, notion_page_id, "Шорт саммари", 
                                       summaries['short'], prop_max_len, log_func)
                
                # Мидл саммари
                notion_mod.set_rich_text(notion_client, notion_page_id, "Мидл саммари", 
                                       summaries['middle'], prop_max_len, log_func)
                
                # Фулл саммари с обработкой переполнения
                notion_mod.set_rich_text_with_overflow(notion_client, notion_page_id, 
                                                     "Фулл саммари", summaries['full'], 
                                                     prop_max_len, "Большое саммари 2", log_func)
                
                # Материалы
                notion_mod.set_rich_text(notion_client, notion_page_id, "Материалы", 
                                       summaries['resources'], prop_max_len, log_func)
                
                log_func("INFO", "yt_processor", "Результаты сохранены в Notion", page_id=notion_page_id)
            except Exception as e:
                error_msg = f"Ошибка сохранения в Notion: {str(e)}"
                log_func("ERROR", "yt_processor", error_msg, error=str(e))
                # Не прерываем основной процесс из-за ошибки Notion
        
        processing_times['total'] = int((time.time() - start_time) * 1000)
        
        return {
            'success': True,
            'error': None,
            'url': url,
            'video_id': video_id,
            'run_id': run_id,  # Возвращаем реальный run_id
            'transcript': transcript_result,
            'ai_results': ai_results,
            'summaries': summaries,
            'processing_time': processing_times
        }
        
    except Exception as e:
        log_func("ERROR", "yt_processor", "Неожиданная ошибка в обработке", error=str(e))
        return {
            'success': False,
            'error': f'Неожиданная ошибка: {str(e)}',
            'url': url,
            'video_id': video_id,  # video_id теперь всегда определен
            'run_id': None,
            'transcript': None,
            'ai_results': None,
            'summaries': None,
            'processing_time': {'total': int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0}
        }