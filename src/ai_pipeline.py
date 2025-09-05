"""
Модуль для полной AI-обработки транскриптов
"""
import re
import json
import ai_mod


def run_clean(transcript_text: str, config, log) -> dict:
    """
    Вызывает промт CLEAN (id=ai.prompts_map.CLEAN).
    Возвращает {"clean": str, "links": list[str], "raw": str, "error": None|{...}}
    Если JSON кривой — как в ai_mod.ai_clean_ads: попытка автопочинки, затем один повторный запрос.
    Логи: ai_clean_start / ai_clean_parsed / ai_clean_error
    """
    log("INFO", "ai_pipeline", "ai_clean_start", input_len=len(transcript_text))
    
    # Получаем ID промта из конфигурации
    prompts_map = config.get('ai', {}).get('prompts_map', {})
    prompt_id = prompts_map.get('CLEAN', 1)
    
    # Вызываем модель
    result = ai_mod.call_model(prompt_id, transcript_text, config, log)
    
    if not result["ok"]:
        log("ERROR", "ai_pipeline", "ai_clean_error", error=result["error"])
        return {
            "clean": "",
            "links": [],
            "raw": "",
            "error": result["error"]
        }
    
    raw_response = result["text"]
    
    # Пытаемся распарсить JSON
    def try_parse_json(text):
        try:
            return json.loads(text), None
        except json.JSONDecodeError as e:
            return None, str(e)
    
    # Первая попытка парсинга
    parsed_data, parse_error = try_parse_json(raw_response)
    
    if parsed_data is None:
        # Пытаемся извлечь JSON из фигурных скобок
        json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
        if json_match:
            json_text = json_match.group(0)
            parsed_data, parse_error = try_parse_json(json_text)
    
    if parsed_data is None:
        # Второй вызов с уточнением
        log("WARN", "ai_pipeline", "Invalid JSON, retrying", error=parse_error)
        clarification_prompt = "Верни JSON строго в формате: {\"clean\":\"текст\",\"links\":[\"url1\",\"url2\"]}"
        retry_result = ai_mod.call_model(prompt_id, transcript_text + "\n\n" + clarification_prompt, config, log)
        
        if retry_result["ok"]:
            parsed_data, parse_error = try_parse_json(retry_result["text"])
            
            # Еще раз пытаемся извлечь из скобок
            if parsed_data is None:
                json_match = re.search(r'\{.*\}', retry_result["text"], re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                    parsed_data, parse_error = try_parse_json(json_text)
    
    if parsed_data is None:
        log("ERROR", "ai_pipeline", "ai_clean_error", error=f"JSON parse error: {parse_error}")
        return {
            "clean": "",
            "links": [],
            "raw": raw_response,
            "error": {"code": "invalid_json", "detail": f"JSON parse error: {parse_error}"}
        }
    
    # Извлекаем данные
    clean_text = parsed_data.get("clean", "")
    links = parsed_data.get("links", [])
    
    # Валидируем структуру
    if not isinstance(clean_text, str):
        clean_text = str(clean_text)
    
    if not isinstance(links, list):
        links = []
    else:
        # Фильтруем только строки и URL
        valid_links = []
        for link in links:
            if isinstance(link, str) and (link.startswith("http://") or link.startswith("https://")):
                valid_links.append(link)
        links = valid_links
    
    log("INFO", "ai_pipeline", "ai_clean_parsed", clean_len=len(clean_text), links=len(links))
    
    return {
        "clean": clean_text,
        "links": links,
        "raw": raw_response,
        "error": None
    }


def run_full(clean_text: str, config, log) -> str:
    """
    Промт FULL: полное саммари (полезная выжимка без воды и ссылок).
    Вернуть строку (можно многострочную). По месту триммится при записи в Excel.
    Лог: ai_full_done len=...
    """
    prompts_map = config.get('ai', {}).get('prompts_map', {})
    prompt_id = prompts_map.get('FULL', 2)
    
    result = ai_mod.call_model(prompt_id, clean_text, config, log)
    
    if not result["ok"]:
        log("ERROR", "ai_pipeline", "ai_full_error", error=result["error"])
        return ""
    
    full_summary = result["text"].strip()
    log("INFO", "ai_pipeline", "ai_full_done", len=len(full_summary))
    
    return full_summary


def run_middle_10(clean_text: str, config, log) -> str:
    """
    Промт MIDDLE_10: одно связное саммари на РОВНО 10 предложений.
    Пост-обработка: посчитать предложения ('.', '!', '?'), если >10 — обрезать до первых 10;
    если <10 — оставить как есть (логом отметить short_count).
    Вернуть строку. Лог: ai_middle_done sentences=...
    """
    prompts_map = config.get('ai', {}).get('prompts_map', {})
    prompt_id = prompts_map.get('MIDDLE_10', 3)
    
    result = ai_mod.call_model(prompt_id, clean_text, config, log)
    
    if not result["ok"]:
        log("ERROR", "ai_pipeline", "ai_middle_error", error=result["error"])
        return ""
    
    middle_text = result["text"].strip()
    
    # Подсчет предложений
    sentences = re.split(r'[.!?]+', middle_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    actual_count = len(sentences)
    
    if actual_count > 10:
        # Обрезаем до 10 предложений
        truncated_sentences = sentences[:10]
        middle_text = '. '.join(truncated_sentences) + '.'
        log("INFO", "ai_pipeline", "ai_middle_done", sentences=10, original_count=actual_count, truncated=True)
    else:
        log("INFO", "ai_pipeline", "ai_middle_done", sentences=actual_count, short_count=actual_count < 10)
    
    return middle_text


def run_short_300(clean_text: str, config, log) -> str:
    """
    Промт SHORT_300: 1–2 предложения, ЖЁСТКИЙ лимит 300 символов.
    Пост-обработка: если >300 — усечь до 300 символов (обрезать по границе слова, если можно).
    Вернуть строку. Лог: ai_short_done len=... truncated=true|false
    """
    prompts_map = config.get('ai', {}).get('prompts_map', {})
    prompt_id = prompts_map.get('SHORT_300', 4)
    
    result = ai_mod.call_model(prompt_id, clean_text, config, log)
    
    if not result["ok"]:
        log("ERROR", "ai_pipeline", "ai_short_error", error=result["error"])
        return ""
    
    short_text = result["text"].strip()
    original_len = len(short_text)
    truncated = False
    
    if original_len > 300:
        # Усекаем до 300 символов с попыткой сохранить границы слов
        truncated_text = short_text[:300]
        
        # Ищем последний пробел, чтобы не обрезать слово посередине
        last_space = truncated_text.rfind(' ')
        if last_space > 250:  # Если пробел не слишком далеко от конца
            short_text = truncated_text[:last_space]
        else:
            short_text = truncated_text
        
        truncated = True
    
    log("INFO", "ai_pipeline", "ai_short_done", len=len(short_text), original_len=original_len, truncated=truncated)
    
    return short_text


def run_resources(clean_text: str, links_from_clean: list[str], config, log) -> list[str]:
    """
    Если links_from_clean непустой — взять их за основу.
    ИНАЧЕ вызвать промт RESOURCES (id=ai.prompts_map.RESOURCES) — извлечь упоминания сервисов/ресурсов/ссылок из текста.
    Объединить, дедуплицировать (по точной строке), вернуть список.
    Лог: ai_resources_done count=...
    """
    all_resources = set()
    
    # Добавляем ссылки из CLEAN
    for link in links_from_clean:
        if isinstance(link, str) and link.strip():
            all_resources.add(link.strip())
    
    # Если ссылок из CLEAN нет, пытаемся извлечь через RESOURCES промт
    if not all_resources:
        prompts_map = config.get('ai', {}).get('prompts_map', {})
        prompt_id = prompts_map.get('RESOURCES', 5)
        
        result = ai_mod.call_model(prompt_id, clean_text, config, log)
        
        if result["ok"]:
            resources_text = result["text"].strip()
            # Простой парсинг ресурсов построчно
            for line in resources_text.split('\n'):
                line = line.strip()
                if line and (line.startswith('http') or '://' in line):
                    all_resources.add(line)
    
    final_list = list(all_resources)
    log("INFO", "ai_pipeline", "ai_resources_done", count=len(final_list))
    
    return final_list