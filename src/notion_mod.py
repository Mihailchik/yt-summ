#!/usr/bin/env python3
"""
Модуль интеграции с Notion API для YT_Sum v1.2.0

Особенности:
- Только свойства страниц (без блоков)
- Ограничение текста в 1950 символов
- Транскрипты НЕ сохраняются в Notion
- Обработка ошибок без падения основной программы
"""

import time
from typing import Optional, List, Dict, Any

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

def init_client(config, log) -> Optional[Client]:
    """Инициализирует клиент Notion API"""
    if not NOTION_AVAILABLE:
        log("ERROR", "notion_mod", "Notion SDK не установлен. Установите: pip install notion-client")
        return None
    
    notion_config = config.get('notion', {})
    token = notion_config.get('token')
    
    if not token:
        log("ERROR", "notion_mod", "Notion token не настроен")
        return None
    
    try:
        client = Client(auth=token)
        log("INFO", "notion_mod", "Notion клиент инициализирован успешно")
        return client
    except Exception as e:
        log("ERROR", "notion_mod", "Ошибка инициализации Notion клиента", error=str(e))
        return None

def ensure_database(client: Client, config, log) -> Optional[Dict[str, Any]]:
    """
    Гарантирует существование базы данных YT_SUM_QO с нужными свойствами.
    Если есть несколько баз с таким именем - выбирает самую новую.
    Возвращает информацию о базе данных или None при ошибке.
    """
    if not client:
        return None
    
    notion_config = config.get('notion', {})
    database_id = notion_config.get('database_id', '')
    
    # Определяем нужные свойства (русские названия)
    required_properties = {
        "Видео": {
            "title": {}
        },
        "Номер": {
            "number": {
                "format": "number"
            }
        },
        "Ссылка": {
            "url": {}
        },
        "Дата добавления": {
            "date": {}
        },
        "Шорт саммари": {
            "rich_text": {}
        },
        "Мидл саммари": {
            "rich_text": {}
        },
        "Фулл саммари": {
            "rich_text": {}
        },
        "Большое саммари 2": {
            "rich_text": {}
        },
        "Материалы": {
            "rich_text": {}
        }
    }
    
    try:
        # Если database_id указан, проверяем существующую базу
        if database_id:
            try:
                db_info = client.databases.retrieve(database_id=database_id)
                log("INFO", "notion_mod", "Использую существующую базу данных", database_id=database_id)
                return db_info
            except Exception as e:
                log("WARNING", "notion_mod", "Не удалось получить базу по ID, ищу по имени", error=str(e))
        
        # Ищем базы данных с именем YT_SUM_QO
        log("INFO", "notion_mod", "Ищу базы данных с именем YT_SUM_QO")
        
        # Получаем список всех баз данных
        search_result = client.search(
            filter={
                "value": "database",
                "property": "object"
            }
        )
        
        # Фильтруем по имени YT_SUM_QO
        matching_databases = []
        for result in search_result.get('results', []):
            if result.get('object') == 'database':
                title_parts = result.get('title', [])
                if title_parts and len(title_parts) > 0:
                    title_text = title_parts[0].get('text', {}).get('content', '')
                    if title_text == 'YT_SUM_QO':
                        matching_databases.append(result)
        
        if matching_databases:
            # Сортируем по дате создания (самая новая первой)
            matching_databases.sort(key=lambda x: x.get('created_time', ''), reverse=True)
            latest_db = matching_databases[0]
            
            db_id = latest_db['id']
            created_time = latest_db.get('created_time', '')
            
            if len(matching_databases) > 1:
                log("INFO", "notion_mod", f"Найдено {len(matching_databases)} баз с именем YT_SUM_QO, выбрана самая новая", 
                    database_id=db_id, created_time=created_time)
            else:
                log("INFO", "notion_mod", "Найдена база YT_SUM_QO", database_id=db_id, created_time=created_time)
            
            return latest_db
        
        # Нет баз с таким именем - создаем новую
        log("INFO", "notion_mod", "База YT_SUM_QO не найдена, создаю новую")
        
        parent_page_url = notion_config.get('parent_page_url', '')
        if not parent_page_url:
            log("ERROR", "notion_mod", "parent_page_url не настроен для создания базы")
            return None
        
        # Извлекаем ID страницы из URL
        if 'notion.so/' in parent_page_url:
            page_id = parent_page_url.split('/')[-1].split('?')[0]
            if '-' in page_id:
                page_id = page_id.replace('-', '')
        else:
            log("ERROR", "notion_mod", "Неверный формат parent_page_url")
            return None
        
        # Создаем базу данных
        new_db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "YT_SUM_QO"}}],
            properties=required_properties
        )
        
        new_db_id = new_db['id']
        log("INFO", "notion_mod", "Создана новая база данных YT_SUM_QO", database_id=new_db_id)
        
        return new_db
        
    except Exception as e:
        log("ERROR", "notion_mod", "Ошибка при работе с базой данных", error=str(e))
        return None

def upsert_page_for_run(client: Client, db_id: str, run_id: int, url: str, 
                       video_title: Optional[str], created_at_iso: str, log) -> Optional[str]:
    """
    Создает или обновляет страницу для run_id.
    Возвращает page_id или None при ошибке.
    """
    if not client or not db_id:
        return None
    
    try:
        # Ищем существующую страницу с таким Номер
        query_result = client.databases.query(
            database_id=db_id,
            filter={
                "property": "Номер",
                "number": {"equals": run_id}
            }
        )
        
        # Определяем заголовок страницы
        page_title = video_title if video_title else url
        if len(page_title) > 100:  # Ограничиваем заголовок
            page_title = page_title[:97] + "..."
        
        if query_result['results']:
            # Страница существует, возвращаем её ID
            page_id = query_result['results'][0]['id']
            log("INFO", "notion_mod", "Найдена существующая страница", page_id=page_id, run_id=run_id)
            return page_id
        else:
            # Создаем новую страницу
            new_page = client.pages.create(
                parent={"database_id": db_id},
                properties={
                    "Видео": {"title": [{"text": {"content": page_title}}]},
                    "Номер": {"number": run_id},
                    "Ссылка": {"url": url},
                    "Дата добавления": {"date": {"start": created_at_iso[:10]}}  # Только дата без времени
                }
            )
            
            page_id = new_page['id']
            log("INFO", "notion_mod", "Создана новая страница", page_id=page_id, run_id=run_id)
            return page_id
            
    except Exception as e:
        log("ERROR", "notion_mod", "Ошибка при создании/поиске страницы", error=str(e), run_id=run_id)
        return None

def set_rich_text(client: Client, page_id: str, property_name: str, text: str, max_len: int, log) -> bool:
    """
    Обновляет свойство rich_text с ограничением длины.
    Возвращает True при успехе, False при ошибке.
    """
    if not client or not page_id:
        return False
    
    try:
        # Обрезаем текст до max_len
        truncated_text = (text or "")[:max_len]
        
        client.pages.update(
            page_id=page_id,
            properties={
                property_name: {
                    "rich_text": [{"text": {"content": truncated_text}}]
                }
            }
        )
        
        char_info = f"{len(truncated_text)}/{max_len}"
        log("INFO", "notion_mod", f"Обновлено свойство {property_name}", 
            page_id=page_id, chars=char_info)
        return True
        
    except Exception as e:
        log("ERROR", "notion_mod", f"Ошибка обновления свойства {property_name}", 
            page_id=page_id, error=str(e))
        return False

def ensure_property_exists(client: Client, database_id: str, property_name: str, property_type: str, log) -> bool:
    """
    Проверяет существование свойства в базе данных и добавляет его при необходимости.
    
    Args:
        client: Notion клиент
        database_id: ID базы данных
        property_name: Название свойства
        property_type: Тип свойства ("rich_text", "title", "number", "url", "date")
        log: Функция логирования
        
    Returns:
        True если свойство существует или было успешно добавлено
    """
    try:
        # Получаем информацию о базе данных
        db_info = client.databases.retrieve(database_id=database_id)
        
        # Проверяем, существует ли свойство
        if property_name in db_info.get('properties', {}):
            log("INFO", "notion_mod", f"Свойство {property_name} уже существует")
            return True
        
        # Свойство не существует, добавляем его
        property_definition = {}
        if property_type == "rich_text":
            property_definition = {
                "type": "rich_text",
                "rich_text": {}
            }
        elif property_type == "title":
            property_definition = {
                "type": "title",
                "title": {}
            }
        elif property_type == "number":
            property_definition = {
                "type": "number",
                "number": {
                    "format": "number"
                }
            }
        elif property_type == "url":
            property_definition = {
                "type": "url",
                "url": {}
            }
        elif property_type == "date":
            property_definition = {
                "type": "date",
                "date": {}
            }
        else:
            log("ERROR", "notion_mod", f"Неизвестный тип свойства: {property_type}")
            return False
        
        # Обновляем схему базы данных
        client.databases.update(
            database_id=database_id,
            properties={
                property_name: property_definition
            }
        )
        
        log("INFO", "notion_mod", f"Свойство {property_name} успешно добавлено в базу данных")
        return True
        
    except Exception as e:
        log("ERROR", "notion_mod", f"Ошибка при добавлении свойства {property_name}", error=str(e))
        return False

def set_rich_text_with_overflow(client: Client, page_id: str, property_name: str, 
                               text: str, max_len: int, overflow_property_name: str, log) -> bool:
    """
    Обновляет свойство rich_text с ограничением длины и сохраняет остаток в другом свойстве.
    Возвращает True при успехе, False при ошибке.
    """
    if not client or not page_id:
        return False
    
    try:
        # Если текст короче лимита, сохраняем полностью
        if len(text) <= max_len:
            return set_rich_text(client, page_id, property_name, text, max_len, log)
        
        # Если текст длиннее лимита, сохраняем первую часть в основном свойстве
        main_text = text[:max_len]
        overflow_text = text[max_len:]
        
        # Сохраняем основную часть
        success1 = set_rich_text(client, page_id, property_name, main_text, max_len, log)
        
        # Проверяем существование дополнительного свойства и добавляем его при необходимости
        if success1:
            # Получаем database_id из страницы
            try:
                page_info = client.pages.retrieve(page_id=page_id)
                database_id = page_info['parent']['database_id']
                # Проверяем и добавляем свойство при необходимости
                ensure_property_exists(client, database_id, overflow_property_name, "rich_text", log)
            except Exception as e:
                log("WARNING", "notion_mod", "Не удалось получить database_id для проверки свойства", error=str(e))
        
        # Сохраняем остаток в дополнительном свойстве
        success2 = set_rich_text(client, page_id, overflow_property_name, overflow_text, max_len, log)
        
        return success1 and success2
        
    except Exception as e:
        log("ERROR", "notion_mod", f"Ошибка обновления свойства {property_name} с переполнением", 
            page_id=page_id, error=str(e))
        return False

def set_materials(client: Client, page_id: str, lines: List[str], max_len: int, log) -> bool:
    """
    Обновляет свойство 'Материалы' объединяя строки через \n.
    Возвращает True при успехе, False при ошибке.
    """
    if not lines:
        lines = []
    
    body = "\n".join(lines)
    return set_rich_text(client, page_id, "Материалы", body, max_len, log)

def handle_api_error(error: Exception, operation: str, log) -> bool:
    """
    Обрабатывает ошибки Notion API.
    Возвращает True если нужно прекратить дальнейшие попытки, False если можно повторить.
    """
    error_str = str(error)
    
    # Ошибки авторизации - прекращаем работу с Notion
    if "401" in error_str or "403" in error_str or "unauthorized" in error_str.lower():
        log("ERROR", "notion_mod", f"Ошибка авторизации при {operation}, отключаю Notion", error=error_str)
        return True
    
    # Rate limiting - можно повторить
    if "429" in error_str or "rate_limit" in error_str.lower():
        log("WARNING", "notion_mod", f"Rate limit при {operation}, повторю позже", error=error_str)
        return False
    
    # Серверные ошибки - можно повторить
    if any(code in error_str for code in ["500", "502", "503", "504"]):
        log("WARNING", "notion_mod", f"Серверная ошибка при {operation}, повторю позже", error=error_str)
        return False
    
    # Другие ошибки - логируем но не прекращаем
    log("ERROR", "notion_mod", f"Неизвестная ошибка при {operation}", error=error_str)
    return False

def retry_with_backoff(func, backoff_ms: List[int], operation: str, log, *args, **kwargs):
    """
    Выполняет функцию с повторами по backoff.
    Возвращает результат функции или None при неудаче.
    """
    last_error = None
    
    for i, delay_ms in enumerate([0] + backoff_ms):  # Первый вызов без задержки
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
            log("INFO", "notion_mod", f"Повтор {i}/{len(backoff_ms)} для {operation} через {delay_ms}мс")
        
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            should_stop = handle_api_error(e, operation, log)
            if should_stop:
                break
    
    log("ERROR", "notion_mod", f"Все попытки {operation} исчерпаны", error=str(last_error))
    return None