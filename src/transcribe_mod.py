try:
    from supadata import Supadata, SupadataError
except ImportError:
    # Fallback для случая когда SDK не установлен
    Supadata = None
    SupadataError = Exception

import time


def fetch_transcript(url: str, config, log) -> dict:
    """
    Получить транскрипт через Supadata SDK или fallback на HTTP API.
    Поддерживает как синхронный, так и асинхронный режимы.
    """
    
    supadata_config = config.get('supadata', {})
    api_keys = supadata_config.get('api_keys', [])
    timeout_sec = supadata_config.get('timeout_sec', 30)
    mode = supadata_config.get('mode', 'auto')
    
    if not api_keys:
        log("ERROR", "transcribe_mod", "Нет API ключей в конфигурации")
        raise ValueError("no_api_keys")
    
    log("INFO", "transcribe_mod", "Начинаем запрос транскрипта", url=url, mode=mode)
    
    # Пробуем ключи по очереди
    for i, api_key in enumerate(api_keys):
        log("DEBUG", "transcribe_mod", f"Пробуем API ключ {i+1}/{len(api_keys)}")
        
        try:
            if Supadata is not None:
                # Используем официальный SDK
                result = _fetch_with_sdk(url, api_key, mode, timeout_sec, log)
            else:
                # Fallback на HTTP API
                result = _fetch_with_http(url, api_key, supadata_config, log)
            
            return result
            
        except ValueError as e:
            error_code = str(e)
            
            # Если ошибка связана с авторизацией/лимитами - пробуем следующий ключ
            if error_code in ['unauthorized', 'rate_limited'] and i < len(api_keys) - 1:
                log("WARN", "transcribe_mod", f"Ошибка с ключом {i+1}, пробуем следующий", error=error_code)
                continue
            else:
                # Если это последний ключ или другая ошибка - пробрасываем
                raise
        except Exception as e:
            log("ERROR", "transcribe_mod", f"Неожиданная ошибка с ключом {i+1}", error=str(e))
            if i < len(api_keys) - 1:
                continue
            else:
                raise ValueError("unexpected_error")
    
    # Если дошли сюда - все ключи исчерпаны
    log("ERROR", "transcribe_mod", "Все API ключи исчерпаны")
    raise ValueError("all_keys_failed")


def _fetch_with_sdk(url: str, api_key: str, mode: str, timeout_sec: int, log) -> dict:
    """
    Получение транскрипта через официальный Supadata SDK
    """
    try:
        # Инициализируем клиент
        client = Supadata(api_key=api_key)
        
        start_time = time.time()
        
        # Запрашиваем транскрипт
        transcript = client.transcript(
            url=url,
            text=True,  # Получаем простой текст
            mode=mode
        )
        
        request_time = time.time() - start_time
        log("INFO", "transcribe_mod", "Получен ответ от Supadata SDK", 
            request_time=f"{request_time:.2f}s")
        
        # Проверяем тип ответа
        if hasattr(transcript, 'content'):
            # Синхронный ответ
            content_len = len(transcript.content)
            log("INFO", "transcribe_mod", "Транскрипт получен успешно (синхронно)", 
                lang=transcript.lang, content_length=content_len)
            return {
                'content': transcript.content,
                'lang': transcript.lang,
                'meta': {'sdk_version': True}
            }
        elif hasattr(transcript, 'job_id'):
            # Асинхронный ответ - опрашиваем статус
            log("INFO", "transcribe_mod", "Получен job_id, ожидаем завершения", job_id=transcript.job_id)
            return _poll_sdk_job(client, transcript.job_id, timeout_sec, log)
        else:
            log("ERROR", "transcribe_mod", "Неожиданный формат ответа от SDK")
            raise ValueError("unexpected_response_format")
            
    except SupadataError as e:
        log("ERROR", "transcribe_mod", "Ошибка Supadata SDK", error_code=e.error, message=e.message)
        
        # Мапим ошибки SDK в наши коды
        if 'unauthorized' in e.error.lower() or 'authentication' in e.error.lower():
            raise ValueError("unauthorized")
        elif 'rate' in e.error.lower() or 'limit' in e.error.lower():
            raise ValueError("rate_limited")
        elif 'invalid' in e.error.lower() and 'url' in e.message.lower():
            raise ValueError("bad_url")
        else:
            raise ValueError("server_error")
    except Exception as e:
        log("ERROR", "transcribe_mod", "Неожиданная ошибка SDK", error=str(e))
        raise ValueError("sdk_error")


def _poll_sdk_job(client, job_id: str, timeout_sec: int, log) -> dict:
    """
    Опрашиваем статус асинхронной задачи через SDK
    """
    start_time = time.time()
    poll_interval = 2
    
    while time.time() - start_time < timeout_sec:
        try:
            # Пробуем получить результаты
            # Примечание: это может потребовать уточнения API
            results = client.batch.get_batch_results(job_id=job_id)
            
            if results.status == 'completed':
                if results.results and len(results.results) > 0:
                    first_result = results.results[0]
                    log("INFO", "transcribe_mod", "Асинхронная задача завершена", job_id=job_id)
                    return {
                        'content': first_result.content,
                        'lang': first_result.lang,
                        'meta': {'job_id': job_id, 'async': True}
                    }
                else:
                    raise ValueError("no_results_in_completed_job")
            elif results.status == 'failed':
                log("ERROR", "transcribe_mod", "Асинхронная задача провалилась", job_id=job_id)
                raise ValueError("async_job_failed")
            elif results.status in ['pending', 'processing']:
                log("DEBUG", "transcribe_mod", "Асинхронная задача выполняется", 
                    job_id=job_id, status=results.status)
                time.sleep(poll_interval)
                continue
            else:
                log("WARN", "transcribe_mod", "Неизвестный статус задачи", 
                    job_id=job_id, status=results.status)
                time.sleep(poll_interval)
                continue
                
        except Exception as e:
            log("WARN", "transcribe_mod", "Ошибка при опросе статуса SDK", error=str(e))
            time.sleep(poll_interval)
            continue
    
    log("ERROR", "transcribe_mod", "Таймаут опроса асинхронной задачи SDK", 
        job_id=job_id, timeout_sec=timeout_sec)
    raise ValueError("job_timeout")


def _fetch_with_http(url: str, api_key: str, supadata_config: dict, log) -> dict:
    """
    Fallback метод для работы через HTTP API в случае отсутствия SDK
    """
    import requests
    import json
    
    base_url = supadata_config.get('base_url')
    timeout_sec = supadata_config.get('timeout_sec', 30)
    mode = supadata_config.get('mode', 'auto')
    
    params = {
        'url': url,
        'text': 'true',
        'mode': mode
    }
    
    headers = {
        'x-api-key': api_key
    }
    
    try:
        log("INFO", "transcribe_mod", "Используем HTTP fallback API")
        start_time = time.time()
        response = requests.get(base_url, params=params, headers=headers, timeout=timeout_sec)
        request_time = time.time() - start_time
        
        log("INFO", "transcribe_mod", "Получен ответ от HTTP API", 
            status_code=response.status_code, request_time=f"{request_time:.2f}s")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'content' in data and 'lang' in data:
                    content_len = len(data['content'])
                    log("INFO", "transcribe_mod", "Транскрипт получен через HTTP API", 
                        lang=data['lang'], content_length=content_len)
                    return {
                        'content': data['content'],
                        'lang': data['lang'],
                        'meta': data
                    }
                else:
                    raise ValueError("unexpected_response_format")
            except json.JSONDecodeError:
                raise ValueError("json_decode_error")
        
        elif response.status_code == 202:
            try:
                data = response.json()
                if 'jobId' in data:
                    job_id = data['jobId']
                    log("INFO", "transcribe_mod", "Получен jobId через HTTP API", job_id=job_id)
                    return _poll_http_job_status(job_id, api_key, supadata_config, log)
                else:
                    raise ValueError("no_job_id")
            except json.JSONDecodeError:
                raise ValueError("json_decode_error")
        
        elif response.status_code in [401, 403]:
            raise ValueError("unauthorized")
        elif response.status_code == 429:
            raise ValueError("rate_limited")
        elif response.status_code >= 500:
            raise ValueError("server_error")
        elif response.status_code == 400:
            raise ValueError("bad_url")
        else:
            raise ValueError("unexpected_status")
            
    except requests.exceptions.Timeout:
        raise ValueError("request_timeout")
    except requests.exceptions.RequestException:
        raise ValueError("network_error")


def _poll_http_job_status(job_id: str, api_key: str, supadata_config: dict, log) -> dict:
    """Опрашиваем статус асинхронной задачи через HTTP"""
    import requests
    
    timeout_sec = supadata_config.get('timeout_sec', 30)
    base_url = supadata_config.get('base_url')
    headers = {'x-api-key': api_key}
    
    start_time = time.time()
    poll_interval = 2
    
    while time.time() - start_time < timeout_sec:
        try:
            status_response = requests.get(f"{base_url}/status/{job_id}", headers=headers, timeout=10)
            
            if status_response.status_code == 200:
                data = status_response.json()
                status = data.get('status', '')
                
                if status == 'completed':
                    log("INFO", "transcribe_mod", "Асинхронная задача завершена (HTTP)", job_id=job_id)
                    if 'content' in data and 'lang' in data:
                        return {
                            'content': data['content'],
                            'lang': data['lang'],
                            'meta': data
                        }
                    else:
                        raise ValueError("incomplete_async_response")
                
                elif status == 'failed':
                    raise ValueError("async_job_failed")
                
                elif status in ['pending', 'processing']:
                    log("DEBUG", "transcribe_mod", "Опрашиваем статус задачи (HTTP)", 
                        job_id=job_id, status=status)
                    time.sleep(poll_interval)
                    continue
                
                else:
                    time.sleep(poll_interval)
                    continue
            
            else:
                time.sleep(poll_interval)
                continue
                
        except requests.exceptions.RequestException:
            time.sleep(poll_interval)
            continue
    
    raise ValueError("job_timeout")