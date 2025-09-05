import os
import json
import re
import time
from pathlib import Path
import requests


def load_prompts(config, log) -> dict:
    """
    Читает ai.prompt_file. Возвращает {id: {"name": str, "text": str}}.
    Ошибка, если файл отсутствует или нет нужного id. Лог: prompts_loaded count=...
    """
    ai_config = config.get('ai', {})
    prompt_file = ai_config.get('prompt_file', 'prompts/yt_prompts.txt')
    
    # Строим путь относительно корня проекта
    project_root = Path(__file__).parent.parent
    prompt_path = project_root / prompt_file
    
    if not prompt_path.exists():
        log("ERROR", "ai_mod", f"Файл промтов не найден: {prompt_path}")
        raise ValueError(f"prompt_file_missing: {prompt_path}")
    
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        log("ERROR", "ai_mod", f"Ошибка чтения файла промтов: {e}")
        raise ValueError(f"prompt_file_read_error: {e}")
    
    # Парсим секции ### <id> <name>
    prompts = {}
    
    # Добавляем разделитель в начало если его нет
    if not content.startswith('\n'):
        content = '\n' + content
    
    sections = re.split(r'\n### (\d+) (\w+)\n', content)
    
    if len(sections) < 4:  # Должно быть: [prefix, id, name, text, ...]
        log("ERROR", "ai_mod", "Файл промтов не содержит корректных секций")
        raise ValueError("prompt_file_invalid_format")
    
    # Обрабатываем секции: sections[0] - префикс, затем триплеты (id, name, text)
    for i in range(1, len(sections), 3):
        if i + 2 >= len(sections):
            break
        
        prompt_id = int(sections[i])
        prompt_name = sections[i + 1]
        prompt_text = sections[i + 2].strip()
        
        prompts[prompt_id] = {
            "name": prompt_name,
            "text": prompt_text
        }
    
    log("INFO", "ai_mod", f"Промты загружены успешно", count=len(prompts))
    return prompts


def call_model(prompt_id: int, input_text: str, config, log) -> dict:
    """
    Склеивает финальный запрос: <prompt_text> + '\\n\\nВХОД: <<<input_text>>>'
    Выполняет вызов к провайдеру (Gemini) с фолбэками
    """
    ai_config = config.get('ai', {})
    
    # Загружаем промты
    prompts = load_prompts(config, log)
    if prompt_id not in prompts:
        log("ERROR", "ai_mod", f"Промт с ID {prompt_id} не найден")
        return {
            "ok": False,
            "text": "",
            "model_used": "",
            "key_index": -1,
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": 0,
            "error": {"code": "prompt_not_found", "detail": f"Prompt ID {prompt_id} not found"}
        }
    
    # Формируем финальный запрос
    prompt_text = prompts[prompt_id]["text"]
    full_prompt = f"{prompt_text}\n\nВХОД: <<<{input_text}>>>"
    
    # Параметры для ретраев
    timeout_sec = ai_config.get('timeout_sec', 20)
    max_retries = ai_config.get('max_retries', 2)
    backoff_ms = ai_config.get('backoff_ms', [600, 1200])
    api_keys = ai_config.get('api_keys', [])
    model_primary = ai_config.get('model_primary', 'gemini-2.0-flash')
    model_backup = ai_config.get('model_backup', [])
    
    if not api_keys:
        log("ERROR", "ai_mod", "API ключи не настроены")
        return {
            "ok": False,
            "text": "",
            "model_used": "",
            "key_index": -1,
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": 0,
            "error": {"code": "no_api_keys", "detail": "No API keys configured"}
        }
    
    models_to_try = [model_primary] + model_backup
    
    start_time = time.time()
    
    for model in models_to_try:
        for key_index, api_key in enumerate(api_keys):
            log("INFO", "ai_mod", "Начинаем вызов AI", model=model, key_index=key_index)
            
            for retry in range(max_retries + 1):
                try:
                    # Формируем запрос к Gemini API
                    headers = {
                        'Content-Type': 'application/json',
                    }
                    
                    # URL для Gemini API
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    
                    payload = {
                        "contents": [{
                            "parts": [{
                                "text": full_prompt
                            }]
                        }],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 4096
                        }
                    }
                    
                    response = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # DEBUG: Логируем структуру ответа для отладки
                        log("DEBUG", "ai_mod", f"Response structure: {json.dumps(result, ensure_ascii=False)[:500]}...")
                        
                        # Извлекаем текст из ответа Gemini
                        text_response = ""
                        if 'candidates' in result and len(result['candidates']) > 0:
                            candidate = result['candidates'][0]
                            log("DEBUG", "ai_mod", f"Candidate structure: {json.dumps(candidate, ensure_ascii=False)[:300]}...")
                            
                            # Проверяем finishReason - возможно контент заблокирован
                            finish_reason = candidate.get('finishReason', 'UNKNOWN')
                            if finish_reason != 'STOP':
                                log("WARN", "ai_mod", f"Gemini finish_reason={finish_reason}, возможна блокировка контента")
                            
                            if 'content' in candidate and 'parts' in candidate['content']:
                                parts = candidate['content']['parts']
                                if len(parts) > 0 and 'text' in parts[0]:
                                    text_response = parts[0]['text']
                        
                        # Проверяем что текст не пустой
                        if not text_response.strip():
                            log("WARN", "ai_mod", "Gemini вернул пустой ответ, пробуем другой ключ")
                            break  # Пробуем следующий ключ
                        
                        log("INFO", "ai_mod", "AI вызов успешен", model=model, key_index=key_index, latency_ms=latency_ms, response_len=len(text_response))
                        
                        return {
                            "ok": True,
                            "text": text_response,
                            "model_used": model,
                            "key_index": key_index,
                            "tokens_in": None,  # Gemini API не всегда возвращает token count
                            "tokens_out": None,
                            "latency_ms": latency_ms,
                            "error": None
                        }
                    
                    elif response.status_code == 429:
                        # Rate limit - ретрай с backoff
                        if retry < max_retries:
                            backoff_time = backoff_ms[min(retry, len(backoff_ms) - 1)] / 1000
                            log("WARN", "ai_mod", f"Rate limit, retry {retry + 1}/{max_retries}", backoff_sec=backoff_time)
                            time.sleep(backoff_time)
                            continue
                        else:
                            log("WARN", "ai_mod", "Rate limit, переключаемся на следующий ключ", key_index=key_index)
                            break
                    
                    elif response.status_code in [401, 403]:
                        # Auth error - сразу следующий ключ
                        log("WARN", "ai_mod", "Auth failed, переключаемся на следующий ключ", status=response.status_code, key_index=key_index)
                        break
                    
                    elif response.status_code >= 500:
                        # Server error - ретрай
                        if retry < max_retries:
                            backoff_time = backoff_ms[min(retry, len(backoff_ms) - 1)] / 1000
                            log("WARN", "ai_mod", f"Server error, retry {retry + 1}/{max_retries}", status=response.status_code, backoff_sec=backoff_time)
                            time.sleep(backoff_time)
                            continue
                        else:
                            log("WARN", "ai_mod", "Server error, переключаемся на следующий ключ", status=response.status_code)
                            break
                    
                    else:
                        # Другие 4xx ошибки - завершаем
                        log("ERROR", "ai_mod", "Bad request", status=response.status_code, response=response.text[:200])
                        return {
                            "ok": False,
                            "text": "",
                            "model_used": model,
                            "key_index": key_index,
                            "tokens_in": None,
                            "tokens_out": None,
                            "latency_ms": latency_ms,
                            "error": {"code": "bad_request", "detail": f"HTTP {response.status_code}: {response.text[:200]}"}
                        }
                
                except requests.exceptions.Timeout:
                    if retry < max_retries:
                        backoff_time = backoff_ms[min(retry, len(backoff_ms) - 1)] / 1000
                        log("WARN", "ai_mod", f"Timeout, retry {retry + 1}/{max_retries}", backoff_sec=backoff_time)
                        time.sleep(backoff_time)
                        continue
                    else:
                        log("WARN", "ai_mod", "Timeout, переключаемся на следующий ключ")
                        break
                
                except Exception as e:
                    log("ERROR", "ai_mod", f"Unexpected error during API call: {e}")
                    if retry < max_retries:
                        backoff_time = backoff_ms[min(retry, len(backoff_ms) - 1)] / 1000
                        time.sleep(backoff_time)
                        continue
                    else:
                        break
    
    # Все попытки неудачны
    latency_ms = int((time.time() - start_time) * 1000)
    log("ERROR", "ai_mod", "Все AI ключи и модели исчерпаны")
    
    return {
        "ok": False,
        "text": "",
        "model_used": "",
        "key_index": -1,
        "tokens_in": None,
        "tokens_out": None,
        "latency_ms": latency_ms,
        "error": {"code": "all_failed", "detail": "All API keys and models exhausted"}
    }


def ai_clean_ads(transcript_text: str, config, log) -> dict:
    """
    Использует prompt_id=1 (P1_CLEAN) и call_model.
    Ожидает одну строку JSON: {"clean":"...","links":[...]}.
    """
    log("INFO", "ai_mod", "Начинаем очистку от рекламы", len=len(transcript_text))
    
    # Вызываем модель
    result = call_model(1, transcript_text, config, log)
    
    if not result["ok"]:
        log("ERROR", "ai_mod", "Ошибка вызова модели", error=result["error"])
        return {
            "clean": "",
            "links": [],
            "raw": "",
            "model_used": "",  # Нет модели при ошибке
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
        log("WARN", "ai_mod", "Невалидный JSON, делаем повторный вызов", error=parse_error)
        clarification_prompt = "Верни JSON строго в формате: {\"clean\":\"текст\",\"links\":[\"url1\",\"url2\"]}"
        retry_result = call_model(1, transcript_text + "\n\n" + clarification_prompt, config, log)
        
        if retry_result["ok"]:
            parsed_data, parse_error = try_parse_json(retry_result["text"])
            
            # Еще раз пытаемся извлечь из скобок
            if parsed_data is None:
                json_match = re.search(r'\{.*\}', retry_result["text"], re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                    parsed_data, parse_error = try_parse_json(json_text)
    
    if parsed_data is None:
        log("ERROR", "ai_mod", "Не удалось распарсить JSON после повторного вызова", error=parse_error)
        return {
            "clean": "",
            "links": [],
            "raw": raw_response,
            "model_used": result.get('model_used', 'unknown'),  # Сохраняем информацию о модели
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
    
    log("INFO", "ai_mod", "Очистка завершена успешно", clean_len=len(clean_text), links=len(links), model=result.get('model_used', 'unknown'))
    
    return {
        "clean": clean_text,
        "links": links,
        "raw": raw_response,
        "model_used": result.get('model_used', 'unknown'),  # Добавляем информацию о модели
        "error": None
    }