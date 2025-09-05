import time
import json
import re
from typing import Optional, Dict, Any, List

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

# Импортируем модуль для работы с промтами из Notion
import prompt_notion
import notion_mod

def init_chat_client(config, log) -> Optional[Any]:
    """Инициализирует клиент google-genai"""
    if not GENAI_AVAILABLE:
        log("ERROR", "ai_chat", "google-genai не установлен. Установите: pip install google-genai")
        return None
    
    ai_config = config.get('ai', {})
    api_keys = ai_config.get('api_keys', [])
    
    if not api_keys:
        log("ERROR", "ai_chat", "API ключи не настроены")
        return None
    
    # Пробуем первый доступный ключ
    for key_index, api_key in enumerate(api_keys):
        try:
            # Настраиваем API ключ через environment или конфигурацию
            # Примечание: google-genai может требовать настройки через переменные окружения
            import os
            os.environ['GOOGLE_API_KEY'] = api_key
            
            client = genai.Client()
            log("INFO", "ai_chat", "Google GenAI клиент инициализирован", key_index=key_index)
            return client
        except Exception as e:
            log("WARNING", "ai_chat", f"Ошибка с API ключом {key_index}", error=str(e))
            continue
    
    log("ERROR", "ai_chat", "Все API ключи исчерпаны")
    return None

def load_prompts_from_notion(config, log) -> Dict[str, str]:
    """
    Загружает промты из Notion базы данных
    
    Returns:
        Словарь {prompt_name: prompt_text}
    """
    try:
        # Инициализируем Notion клиент
        notion_client = notion_mod.init_client(config, log)
        if not notion_client:
            log("ERROR", "ai_chat", "Не удалось инициализировать Notion клиент")
            return {}
        
        # Находим базу промтов
        prompts_db_id = prompt_notion.ensure_prompts_database(notion_client, config, log)
        if not prompts_db_id:
            log("ERROR", "ai_chat", "Не удалось найти базу промтов")
            return {}
        
        # Получаем все промты
        prompts = prompt_notion.get_all_prompts_from_notion(notion_client, prompts_db_id, log)
        
        log("INFO", "ai_chat", f"Загружено {len(prompts)} промтов из Notion", 
            prompts=list(prompts.keys()))
        
        return prompts
        
    except Exception as e:
        log("ERROR", "ai_chat", "Ошибка загрузки промтов из Notion", error=str(e))
        return {}

def is_503_error(error: Exception) -> bool:
    """Проверяет, является ли ошибка 503 UNAVAILABLE"""
    error_str = str(error).lower()
    return "503" in error_str and ("unavailable" in error_str or "overloaded" in error_str or "try again later" in error_str)

def retry_on_503(func, max_retries: int = 3, backoff_ms: List[int] = [1000, 2000, 4000], log=None):
    """
    Выполняет функцию с повторами при ошибке 503 UNAVAILABLE
    
    Args:
        func: функция для выполнения
        max_retries: максимальное количество повторов
        backoff_ms: задержки между повторами в миллисекундах
        log: функция логирования
        
    Returns:
        Результат выполнения функции или None при исчерпании попыток
    """
    last_error = None
    
    # Первый вызов без задержки
    try:
        return func()
    except Exception as e:
        last_error = e
        if not is_503_error(e):
            # Если это не 503 ошибка, пробрасываем её дальше
            raise e
    
    # Повторы с задержкой
    for i, delay_ms in enumerate(backoff_ms[:max_retries]):
        if log:
            log("WARNING", "ai_chat", f"Ошибка 503 UNAVAILABLE, повтор {i+1}/{max_retries} через {delay_ms}мс")
        
        time.sleep(delay_ms / 1000.0)
        
        try:
            return func()
        except Exception as e:
            last_error = e
            if not is_503_error(e):
                # Если это не 503 ошибка, пробрасываем её дальше
                raise e
    
    # Исчерпаны все попытки
    if log:
        log("ERROR", "ai_chat", f"Все попытки повтора исчерпаны из-за ошибки 503 UNAVAILABLE")
    
    raise last_error

def process_transcript_chat(transcript_text: str, config, log) -> Dict[str, Any]:
    """
    Обрабатывает транскрипт через отдельные независимые AI запросы
    Промты берутся из Notion базы данных
    
    Поток:
    1. Очистка от рекламы/воды + исходный транскрипт
    2. Полное саммари + очищенный текст  
    3. Среднее саммари + очищенный текст
    4. Короткое саммари + очищенный текст
    5. Ресурсы + очищенный текст
    
    Возвращает: {
        "clean_text": str,
        "links": List[str], 
        "full_summary": str,
        "middle_summary": str,
        "short_summary": str,
        "resources": List[str],
        "error": None|dict,
        "performance": dict  # для измерения производительности
    }
    """
    start_time = time.time()
    log("INFO", "ai_chat", "Начинаем независимую AI обработку с промтами из Notion", input_len=len(transcript_text))
    
    # Инициализируем клиент
    client = init_chat_client(config, log)
    if not client:
        return {
            "clean_text": "",
            "links": [],
            "full_summary": "",
            "middle_summary": "",
            "short_summary": "",
            "resources": [],
            "error": {"code": "no_client", "detail": "Не удалось инициализировать AI клиент"},
            "performance": {}
        }
    
    # Загружаем промты из Notion
    prompts_load_start = time.time()
    prompts = load_prompts_from_notion(config, log)
    prompts_load_time = int((time.time() - prompts_load_start) * 1000)
    
    if not prompts:
        log("ERROR", "ai_chat", "Не удалось загрузить промты из Notion")
        return {
            "clean_text": "",
            "links": [],
            "full_summary": "",
            "middle_summary": "",
            "short_summary": "",
            "resources": [],
            "error": {"code": "no_prompts", "detail": "Не удалось загрузить промты из Notion"},
            "performance": {"prompts_load_ms": prompts_load_time}
        }
    
    ai_config = config.get('ai', {})
    model = ai_config.get('model_primary', 'gemini-2.5-flash')
    max_retries = ai_config.get('max_retries', 3)
    backoff_ms = ai_config.get('backoff_ms', [1000, 2000, 4000])
    
    try:
        results = {
            "clean_text": "",
            "links": [],
            "full_summary": "",
            "middle_summary": "",
            "short_summary": "",
            "resources": [],
            "error": None,
            "performance": {"prompts_load_ms": prompts_load_time}
        }
        
        # ЗАПРОС 1: Очистка транскрипта (используем промт из Notion)
        clean_template = prompts.get('P1_CLEAN', '')
        if not clean_template:
            log("ERROR", "ai_chat", "Промт P1_CLEAN не найден в Notion")
            # Откатный промт
            clean_template = "Очисти транскрипт от рекламы, спонсорских вставок, CTA. Верни JSON: {{\"clean\":\"текст\", \"links\":[\"ссылки\"]}}. Транскрипт: <<<transcript>>>"
        
        # Подставляем транскрипт в промт
        clean_prompt = clean_template.replace('<<<transcript>>>', transcript_text)
        
        log("INFO", "ai_chat", "Запрос 1: Очистка транскрипта")
        request1_start = time.time()
        
        def make_request1():
            chat1 = client.chats.create(model=model)
            return chat1.send_message(clean_prompt)
        
        response1 = retry_on_503(make_request1, max_retries, backoff_ms, log)
        request1_time = int((time.time() - request1_start) * 1000)
        results["performance"]["request1_ms"] = request1_time
        
        clean_response = response1.text.strip()
        
        # Парсим JSON ответ очистки
        try:
            clean_data = json.loads(clean_response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', clean_response, re.DOTALL)
            if json_match:
                try:
                    clean_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    clean_data = {"clean": "", "links": []}
            else:
                clean_data = {"clean": "", "links": []}
        
        results["clean_text"] = clean_data.get("clean", "")
        results["links"] = clean_data.get("links", [])
        
        if not results["clean_text"]:
            log("WARNING", "ai_chat", "Пустой результат очистки, используем исходный текст")
            results["clean_text"] = transcript_text
        
        clean_text = results["clean_text"]
        
        # ЗАПРОС 2: Полное саммари (используем промт из Notion)
        full_template = prompts.get('P2_FULL_EXPANDED', '')
        if not full_template:
            log("ERROR", "ai_chat", "Промт P2_FULL_EXPANDED не найден в Notion")
            full_template = "По чистому тексту дай максимально полезное ПОЛНОЕ саммари. Текст: <<<clean_text>>>"
        
        full_prompt = full_template.replace('<<<clean_text>>>', clean_text)
        
        log("INFO", "ai_chat", "Запрос 2: Полное саммари")
        request2_start = time.time()
        
        def make_request2():
            chat2 = client.chats.create(model=model)
            return chat2.send_message(full_prompt)
        
        response2 = retry_on_503(make_request2, max_retries, backoff_ms, log)
        request2_time = int((time.time() - request2_start) * 1000)
        results["performance"]["request2_ms"] = request2_time
        
        results["full_summary"] = response2.text.strip()
        
        # ЗАПРОС 3: Среднее саммари (используем промт из Notion)
        middle_template = prompts.get('P3_MIDDLE_800', '')
        if not middle_template:
            log("ERROR", "ai_chat", "Промт P3_MIDDLE_800 не найден в Notion")
            middle_template = "Суммаризируй чистый текст до 800 символов. Текст: <<<clean_text>>>"
        
        middle_prompt = middle_template.replace('<<<clean_text>>>', clean_text)
        
        log("INFO", "ai_chat", "Запрос 3: Среднее саммари")
        request3_start = time.time()
        
        def make_request3():
            chat3 = client.chats.create(model=model)
            return chat3.send_message(middle_prompt)
        
        response3 = retry_on_503(make_request3, max_retries, backoff_ms, log)
        request3_time = int((time.time() - request3_start) * 1000)
        results["performance"]["request3_ms"] = request3_time
        
        middle_response = response3.text.strip()
        
        # Парсим ответ для среднего саммари (может быть JSON или простой текст)
        middle_text = middle_response
        try:
            # Пробуем парсить как JSON
            middle_data = json.loads(middle_response)
            middle_text = middle_data.get("middle_800", middle_response)
        except json.JSONDecodeError:
            # Если не JSON, ищем JSON в тексте
            json_match = re.search(r'\{.*\}', middle_response, re.DOTALL)
            if json_match:
                try:
                    middle_data = json.loads(json_match.group(0))
                    middle_text = middle_data.get("middle_800", middle_response)
                except json.JSONDecodeError:
                    # Оставляем как обычный текст
                    middle_text = middle_response
        
        # Проверяем лимит 800 символов
        if len(middle_text) > 800:
            middle_text = middle_text[:797] + "..."
        
        results["middle_summary"] = middle_text
        
        # ЗАПРОС 4: Короткое саммари (используем промт из Notion)
        short_template = prompts.get('P4_SHORT_300_TITLECHECK', '')
        if not short_template:
            log("ERROR", "ai_chat", "Промт P4_SHORT_300_TITLECHECK не найден в Notion")
            short_template = "Короткое саммари до 300 символов. Текст: <<<clean_text>>>"
        
        # Подставляем очищенный текст и заголовок (если есть)
        short_prompt = short_template.replace('<<<clean_text>>>', clean_text)
        short_prompt = short_prompt.replace('<<<video_title>>>', 'неопределено')  # По умолчанию
        
        log("INFO", "ai_chat", "Запрос 4: Короткое саммари")
        request4_start = time.time()
        
        def make_request4():
            chat4 = client.chats.create(model=model)
            return chat4.send_message(short_prompt)
        
        response4 = retry_on_503(make_request4, max_retries, backoff_ms, log)
        request4_time = int((time.time() - request4_start) * 1000)
        results["performance"]["request4_ms"] = request4_time
        
        short_response = response4.text.strip()
        
        # Парсим ответ нового формата (3 строки)
        lines = short_response.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        if len(lines) >= 2:
            short_summary = lines[1] if len(lines) > 1 else ""
            if len(short_summary) > 300:
                short_summary = short_summary[:297] + "..."
            results["short_summary"] = short_summary
        else:
            results["short_summary"] = short_response[:300]
        
        # ЗАПРОС 5: Ресурсы (используем промт из Notion)
        resources_template = prompts.get('P5_RESOURCES_FACT', '')
        if not resources_template:
            log("ERROR", "ai_chat", "Промт P5_RESOURCES_FACT не найден в Notion")
            resources_template = "По чистому тексту выдай список упомянутых ресурсов/ссылок. Текст: <<<clean_text>>>"
        
        # Подставляем очищенный текст
        links_str = ', '.join(results['links']) if results['links'] else 'нет'
        resources_prompt = resources_template.replace('<<<clean_text>>>', clean_text)
        
        log("INFO", "ai_chat", "Запрос 5: Ресурсы")
        request5_start = time.time()
        
        def make_request5():
            chat5 = client.chats.create(model=model)
            return chat5.send_message(resources_prompt)
        
        response5 = retry_on_503(make_request5, max_retries, backoff_ms, log)
        request5_time = int((time.time() - request5_start) * 1000)
        results["performance"]["request5_ms"] = request5_time
        
        resources_response = response5.text.strip()
        
        # Парсим ответ для ресурсов (может быть JSON или простой список)
        resources_list = []
        try:
            # Пробуем парсить как JSON
            resources_data = json.loads(resources_response)
            real_world_resources = resources_data.get("resources_real_world", [])
            
            for i, resource in enumerate(real_world_resources, 1):
                name = resource.get("name", f"Ресурс {i}")
                access = resource.get("access_real", "unknown")
                notes = resource.get("notes", "")
                
                resource_str = f"{i}. {name} - {access}"
                if notes:
                    resource_str += f" - {notes}"
                
                resources_list.append(resource_str)
                
        except json.JSONDecodeError:
            # Если не JSON, ищем JSON в тексте
            json_match = re.search(r'\{.*\}', resources_response, re.DOTALL)
            if json_match:
                try:
                    resources_data = json.loads(json_match.group(0))
                    real_world_resources = resources_data.get("resources_real_world", [])
                    
                    for i, resource in enumerate(real_world_resources, 1):
                        name = resource.get("name", f"Ресурс {i}")
                        access = resource.get("access_real", "unknown")
                        notes = resource.get("notes", "")
                        
                        resource_str = f"{i}. {name} - {access}"
                        if notes:
                            resource_str += f" - {notes}"
                        
                        resources_list.append(resource_str)
                        
                except json.JSONDecodeError:
                    # Обрабатываем как обычный текст (список по строкам)
                    lines = resources_response.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and len(line) > 5:
                            resources_list.append(line)
            else:
                # Обрабатываем как обычный текст
                lines = resources_response.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and len(line) > 5:
                        resources_list.append(line)
        
        results["resources"] = resources_list
        
        # Добавляем общее время выполнения
        total_time = int((time.time() - start_time) * 1000)
        results["performance"]["total_ms"] = total_time
        
        log("INFO", "ai_chat", "Независимая обработка с Notion промтами завершена", 
            clean_len=len(results["clean_text"]),
            links_count=len(results["links"]),
            resources_count=len(results["resources"]),
            total_time_ms=total_time,
            performance=results["performance"])
        
        return results
        
    except Exception as e:
        total_time = int((time.time() - start_time) * 1000)
        log("ERROR", "ai_chat", "Ошибка независимой обработки с Notion промтами", error=str(e), total_time_ms=total_time)
        return {
            "clean_text": "",
            "links": [],
            "full_summary": "",
            "middle_summary": "",
            "short_summary": "",
            "resources": [],
            "error": {"code": "processing_error", "detail": str(e)},
            "performance": {"total_ms": total_time}
        }