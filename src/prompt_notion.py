#!/usr/bin/env python3
"""
Модуль управления промтами в Notion для YT_Sum

Функции:
- Создание таблицы промтов в Notion
- Деление длинных промтов на части
- Синхронизация промтов из файла в Notion
- Получение промтов из Notion для использования в AI запросах
"""

import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None


def split_long_text(text: str, max_length: int = 1950) -> List[str]:
    """
    Разделяет длинный текст на части, не превышающие max_length символов.
    Старается сохранять целостность предложений и абзацев.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина одной части (по умолчанию 1950 для Notion)
    
    Returns:
        Список частей текста
    """
    if len(text) <= max_length:
        return [text]
    
    parts = []
    remaining_text = text
    
    while len(remaining_text) > max_length:
        # Находим оптимальное место разреза
        cut_position = max_length
        
        # Ищем последний перенос строки в пределах лимита
        last_newline = remaining_text.rfind('\n', 0, max_length)
        if last_newline > max_length * 0.7:  # Если перенос не слишком близко к началу
            cut_position = last_newline
        else:
            # Ищем последнюю точку с пробелом
            last_sentence = remaining_text.rfind('. ', 0, max_length)
            if last_sentence > max_length * 0.7:
                cut_position = last_sentence + 1
            else:
                # Ищем последний пробел
                last_space = remaining_text.rfind(' ', 0, max_length)
                if last_space > max_length * 0.7:
                    cut_position = last_space
        
        # Извлекаем часть текста
        part = remaining_text[:cut_position].strip()
        if part:
            parts.append(part)
        
        # Оставляем оставшийся текст
        remaining_text = remaining_text[cut_position:].strip()
    
    # Добавляем последнюю часть
    if remaining_text:
        parts.append(remaining_text)
    
    return parts


def parse_prompts_file(file_path: str) -> Dict[str, str]:
    """
    Парсит файл промтов и возвращает словарь {имя_промта: текст_промта}
    
    Args:
        file_path: Путь к файлу с промтами
    
    Returns:
        Словарь промтов
    """
    prompts = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Разделяем по секциям ### N NAME
        sections = re.split(r'### (\d+) ([A-Z0-9_]+)', content)
        
        # sections = [пустое, '1', 'P1_CLEAN', контент_1, '2', 'P2_FULL', контент_2, ...]
        i = 1
        while i + 2 < len(sections):
            section_num = sections[i].strip()
            section_name = sections[i + 1].strip() 
            section_content = sections[i + 2].strip()
            
            # Убираем разделители и лишние переносы
            section_content = re.sub(r'\n---+\n', '\n', section_content)
            section_content = section_content.strip()
            
            prompts[section_name] = section_content
            print(f"Найден промт: {section_name} ({len(section_content)} символов)")
            
            i += 3
    
    except Exception as e:
        print(f"Ошибка при чтении файла промтов {file_path}: {e}")
    
    return prompts


def ensure_prompts_database(client: Client, config, log) -> Optional[str]:
    """
    Создает или находит базу данных для промтов в Notion.
    
    Args:
        client: Notion клиент
        config: Конфигурация приложения
        log: Функция логирования
    
    Returns:
        ID базы данных промтов или None при ошибке
    """
    if not client:
        return None
    
    database_name = "YT_PROMPTS"
    
    # Определяем структуру базы данных для промтов
    required_properties = {
        "Имя промта": {
            "title": {}  # Название промта (P1_CLEAN, P2_FULL и т.д.)
        },
        "Промт": {
            "rich_text": {}  # Основной текст промта
        },
        "Разделен": {
            "checkbox": {}  # Флаг - промт разделен на части
        },
        "Промт 2": {
            "rich_text": {}  # Вторая часть промта (если разделен)
        },
        "Промт 3": {
            "rich_text": {}  # Третья часть промта (если разделен)
        },
        "Длина": {
            "number": {
                "format": "number"
            }  # Общая длина промта в символах
        },
        "Обновлен": {
            "date": {}  # Дата последнего обновления
        }
    }
    
    try:
        # Ищем существующую базу данных с промтами
        log("INFO", "prompt_notion", f"Ищу базу данных {database_name}")
        
        search_result = client.search(
            filter={
                "value": "database",
                "property": "object"
            }
        )
        
        # Ищем базу с нужным именем
        for result in search_result.get('results', []):
            if result.get('object') == 'database':
                title_parts = result.get('title', [])
                if title_parts and len(title_parts) > 0:
                    title_text = title_parts[0].get('text', {}).get('content', '')
                    if title_text == database_name:
                        db_id = result['id']
                        log("INFO", "prompt_notion", f"Найдена существующая база {database_name}", database_id=db_id)
                        return db_id
        
        # База не найдена - создаем новую
        log("INFO", "prompt_notion", f"База {database_name} не найдена, создаю новую")
        
        notion_config = config.get('notion', {})
        parent_page_url = notion_config.get('parent_page_url', '')
        
        if not parent_page_url:
            log("ERROR", "prompt_notion", "parent_page_url не настроен для создания базы")
            return None
        
        # Извлекаем ID страницы из URL
        if 'notion.so/' in parent_page_url:
            page_id = parent_page_url.split('/')[-1].split('?')[0]
            if '-' in page_id:
                page_id = page_id.replace('-', '')
        else:
            log("ERROR", "prompt_notion", "Неверный формат parent_page_url")
            return None
        
        # Создаем базу данных
        new_db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": database_name}}],
            properties=required_properties
        )
        
        db_id = new_db['id']
        log("INFO", "prompt_notion", f"Создана новая база данных {database_name}", database_id=db_id)
        
        return db_id
        
    except Exception as e:
        log("ERROR", "prompt_notion", "Ошибка при работе с базой данных промтов", error=str(e))
        return None


def sync_prompts_to_notion(client: Client, db_id: str, prompts_file_path: str, log) -> bool:
    """
    Синхронизирует промты из файла в базу данных Notion.
    
    Args:
        client: Notion клиент
        db_id: ID базы данных промтов
        prompts_file_path: Путь к файлу с промтами
        log: Функция логирования
    
    Returns:
        True при успехе, False при ошибке
    """
    if not client or not db_id:
        return False
    
    try:
        # Читаем промты из файла
        prompts = parse_prompts_file(prompts_file_path)
        
        if not prompts:
            log("WARNING", "prompt_notion", "Промты не найдены в файле", file_path=prompts_file_path)
            return False
        
        log("INFO", "prompt_notion", f"Найдено {len(prompts)} промтов для синхронизации")
        
        import datetime
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Обрабатываем каждый промт
        for prompt_name, prompt_text in prompts.items():
            log("INFO", "prompt_notion", f"Обрабатываю промт {prompt_name}")
            
            # Разделяем промт на части если нужно
            prompt_parts = split_long_text(prompt_text, max_length=1950)
            is_split = len(prompt_parts) > 1
            
            # Ищем существующую страницу для этого промта
            query_result = client.databases.query(
                database_id=db_id,
                filter={
                    "property": "Имя промта",
                    "title": {"equals": prompt_name}
                }
            )
            
            # Подготавливаем данные для страницы
            page_properties = {
                "Имя промта": {"title": [{"text": {"content": prompt_name}}]},
                "Промт": {"rich_text": [{"text": {"content": prompt_parts[0]}}]},
                "Разделен": {"checkbox": is_split},
                "Длина": {"number": len(prompt_text)},
                "Обновлен": {"date": {"start": current_date}}
            }
            
            # Добавляем дополнительные части если есть
            if len(prompt_parts) > 1:
                page_properties["Промт 2"] = {"rich_text": [{"text": {"content": prompt_parts[1]}}]}
            
            if len(prompt_parts) > 2:
                page_properties["Промт 3"] = {"rich_text": [{"text": {"content": prompt_parts[2]}}]}
            
            if query_result['results']:
                # Обновляем существующую страницу
                page_id = query_result['results'][0]['id']
                client.pages.update(
                    page_id=page_id,
                    properties=page_properties
                )
                log("INFO", "prompt_notion", f"Обновлен промт {prompt_name}", page_id=page_id, 
                    is_split=is_split, parts=len(prompt_parts))
            else:
                # Создаем новую страницу
                new_page = client.pages.create(
                    parent={"database_id": db_id},
                    properties=page_properties
                )
                page_id = new_page['id']
                log("INFO", "prompt_notion", f"Создан новый промт {prompt_name}", page_id=page_id,
                    is_split=is_split, parts=len(prompt_parts))
        
        log("INFO", "prompt_notion", "Синхронизация промтов завершена успешно")
        return True
        
    except Exception as e:
        log("ERROR", "prompt_notion", "Ошибка синхронизации промтов", error=str(e))
        return False


def get_prompt_from_notion(client: Client, db_id: str, prompt_name: str, log) -> Optional[str]:
    """
    Получает промт из базы данных Notion, собирая все части если промт разделен.
    
    Args:
        client: Notion клиент
        db_id: ID базы данных промтов
        prompt_name: Имя промта (например, P1_CLEAN)
        log: Функция логирования
    
    Returns:
        Полный текст промта или None при ошибке
    """
    if not client or not db_id:
        return None
    
    try:
        # Ищем промт по имени
        query_result = client.databases.query(
            database_id=db_id,
            filter={
                "property": "Имя промта",
                "title": {"equals": prompt_name}
            }
        )
        
        if not query_result['results']:
            log("WARNING", "prompt_notion", f"Промт {prompt_name} не найден в Notion")
            return None
        
        page = query_result['results'][0]
        properties = page['properties']
        
        # Получаем основную часть промта
        prompt_text = ""
        if 'Промт' in properties and properties['Промт']['rich_text']:
            prompt_text = properties['Промт']['rich_text'][0]['text']['content']
        
        # Проверяем, разделен ли промт
        is_split = False
        if 'Разделен' in properties:
            is_split = properties['Разделен']['checkbox']
        
        # Если промт разделен, собираем все части
        if is_split:
            if 'Промт 2' in properties and properties['Промт 2']['rich_text']:
                prompt_text += "\n" + properties['Промт 2']['rich_text'][0]['text']['content']
            
            if 'Промт 3' in properties and properties['Промт 3']['rich_text']:
                prompt_text += "\n" + properties['Промт 3']['rich_text'][0]['text']['content']
        
        log("INFO", "prompt_notion", f"Получен промт {prompt_name}", 
            length=len(prompt_text), is_split=is_split)
        
        return prompt_text.strip()
        
    except Exception as e:
        log("ERROR", "prompt_notion", f"Ошибка получения промта {prompt_name}", error=str(e))
        return None


def get_all_prompts_from_notion(client: Client, db_id: str, log) -> Dict[str, str]:
    """
    Получает все промты из базы данных Notion.
    
    Args:
        client: Notion клиент
        db_id: ID базы данных промтов
        log: Функция логирования
    
    Returns:
        Словарь {имя_промта: текст_промта}
    """
    if not client or not db_id:
        return {}
    
    try:
        # Получаем все страницы из базы данных
        query_result = client.databases.query(database_id=db_id)
        
        prompts = {}
        
        for page in query_result['results']:
            properties = page['properties']
            
            # Получаем имя промта
            prompt_name = ""
            if 'Имя промта' in properties and properties['Имя промта']['title']:
                prompt_name = properties['Имя промта']['title'][0]['text']['content']
            
            if not prompt_name:
                continue
            
            # Получаем текст промта (со всеми частями)
            prompt_text = get_prompt_from_notion(client, db_id, prompt_name, log)
            
            if prompt_text:
                prompts[prompt_name] = prompt_text
        
        log("INFO", "prompt_notion", f"Получено {len(prompts)} промтов из Notion")
        return prompts
        
    except Exception as e:
        log("ERROR", "prompt_notion", "Ошибка получения всех промтов", error=str(e))
        return {}