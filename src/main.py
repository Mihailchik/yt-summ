import sys
import os
import yaml
import time
from pathlib import Path

# Добавляем текущую директорию в путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import log_mod
import input_mod
import transcribe_mod
import output_mod
import store_excel
import ai_mod
import ai_pipeline
import ai_chat
import notion_mod


def load_config():
    """Загружаем конфигурацию из config/app.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "app.yaml"
    
    if not config_path.exists():
        print(f"ОШИБКА: Файл конфигурации не найден: {config_path}")
        print("Создайте файл config/app.yaml на основе примера")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"ОШИБКА: Не удалось прочитать конфигурацию: {e}")
        sys.exit(1)


def main():
    """
    Алгоритм:
    1) handle = store_excel.init_excel(config, log)
    2) run_id = store_excel.allocate_run_id(handle, log)
    3) url = input_mod.get_source_url(config)
    4) store_excel.write_step(handle, run_id, {"Ссылка": url}, log)
    5) res = transcribe_mod.fetch_transcript(url, config, log)
    6) store_excel.write_step(handle, run_id, {"Субтитры": res['content']}, log)
    7) output_mod.print_preview(res['lang'], res['content'], config.test.preview_chars, log)
    8) store_excel.close(handle)
    9) В конце вывести короткий итог 'OK' либо описание ошибки.
    """
    
    # Загружаем конфигурацию
    config = load_config()
    
    # Инициализируем логирование
    log_mod.init_logging(config)
    log = log_mod.log
    
    log("INFO", "main", "Запуск yt-supadata-cli")
    
    excel_handle = None
    notion_client = None
    notion_db_info = None
    notion_page_id = None
    
    # Инициализируем Notion (если включен)
    notion_config = config.get('notion', {})
    if notion_config.get('enabled', False):
        log("INFO", "main", "Инициализируем Notion интеграцию")
        notion_client = notion_mod.init_client(config, log)
        if notion_client:
            notion_db_info = notion_mod.ensure_database(notion_client, config, log)
            if not notion_db_info:
                log("WARNING", "main", "Не удалось инициализировать Notion базу, продолжаем без Notion")
                notion_client = None
    
    try:
        # Шаг 1: Инициализируем Excel хранилище
        log("INFO", "main", "Инициализируем Excel хранилище")
        excel_handle = store_excel.init_excel(config, log)
        
        # Шаг 2: Выделяем ID для новой записи
        log("INFO", "main", "Выделяем ID для новой записи")
        run_id = store_excel.allocate_run_id(excel_handle, log)
        
        # Шаг 3: Получаем URL от пользователя
        log("INFO", "main", "Запрашиваем URL у пользователя")
        url = input_mod.get_source_url(config)
        log("INFO", "main", "URL получен", url=url)
        
        # Шаг 4: Сохраняем ссылку в Excel
        log("INFO", "main", "Сохраняем ссылку в Excel")
        store_excel.write_step(excel_handle, run_id, {"Ссылка": url}, log)
        
        # Шаг 4.5: Создаем страницу в Notion (если доступен)
        if notion_client and notion_db_info:
            log("INFO", "main", "Создаем страницу в Notion")
            import datetime
            created_at_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            notion_page_id = notion_mod.upsert_page_for_run(
                notion_client, notion_db_info['id'], run_id, url, None, created_at_iso, log
            )
        
        # Шаг 5: Получаем транскрипт через Supadata (измеряем время)
        log("INFO", "main", "Запрашиваем транскрипт")
        supadata_start = time.time()
        result = transcribe_mod.fetch_transcript(url, config, log)
        supadata_time_ms = int((time.time() - supadata_start) * 1000)
        log("INFO", "main", "Транскрипт получен успешно", time_ms=supadata_time_ms)
        
        # Шаг 6: Сохраняем транскрипт в Excel
        log("INFO", "main", "Сохраняем транскрипт в Excel")
        store_excel.write_step(excel_handle, run_id, {"Субтитры": result['content']}, log)
        
        # Шаг 7: Независимая AI-обработка транскрипта (5 запросов)
        log("INFO", "main", "Запускаем независимую AI-обработку")
        
        # Подсчитываем символы в исходном транскрипте
        chars_original = len(result['content'])
        
        # Независимая обработка через google-genai
        ai_start = time.time()
        ai_results = ai_chat.process_transcript_chat(result['content'], config, log)
        ai_time_ms = int((time.time() - ai_start) * 1000)
        
        if ai_results.get('error') is None:
            # Все саммари получены успешно
            clean_text = ai_results.get('clean_text', '')
            full_summary = ai_results.get('full_summary', '')
            middle_summary = ai_results.get('middle_summary', '')
            short_summary = ai_results.get('short_summary', '')
            resources_list = ai_results.get('resources', [])
            
            chars_cleaned = len(clean_text)
            
            # Форматируем ресурсы для Excel
            materials_text = '\n'.join(resources_list) if resources_list else "Ресурсы не найдены"
            
            # Записываем все результаты в Excel
            excel_updates = {
                "Чистый текст": clean_text,
                "Фулл саммари": full_summary,
                "Мидл саммари": middle_summary,
                "Шорт саммари": short_summary,
                "Материалы": materials_text
            }
            
            log("INFO", "main", "Записываем AI результаты в Excel", updates=list(excel_updates.keys()))
            store_excel.write_step(excel_handle, run_id, excel_updates, log)
            
            # Выводим результаты в консоль
            if full_summary:
                print(f"\n=== ПОЛНОЕ САММАРИ ===")
                print(full_summary)
            
            if middle_summary:
                print(f"\n=== СРЕДНЕЕ САММАРИ ===")
                print(middle_summary)
            
            if short_summary:
                print(f"\n=== КОРОТКОЕ САММАРИ ===")
                print(short_summary)
            
            if resources_list:
                print(f"\n=== РЕСУРСЫ ===")
                for resource in resources_list:
                    print(resource)
            else:
                print(f"\n=== РЕСУРСЫ ===")
                print("Ресурсы не найдены.")
            
            # Обновляем Notion (если доступен)
            if notion_client and notion_page_id:
                prop_max_len = notion_config.get('prop_max_len', 1950)
                notion_mod.set_rich_text(notion_client, notion_page_id, "Фулл саммари", full_summary, prop_max_len, log)
                notion_mod.set_rich_text(notion_client, notion_page_id, "Мидл саммари", middle_summary, prop_max_len, log)
                notion_mod.set_rich_text(notion_client, notion_page_id, "Шорт саммари", short_summary, prop_max_len, log)
                notion_mod.set_materials(notion_client, notion_page_id, resources_list, prop_max_len, log)
            
            # Логируем успешную обработку
            log("INFO", "main", "ai_independent_processing_complete", 
                id=run_id, 
                fields=["Чистый текст", "Фулл саммари", "Мидл саммари", "Шорт саммари", "Материалы"],
                independent_requests=5)
        else:
            # Ошибка AI обработки
            chars_cleaned = 0
            error_msg = ai_results['error'].get('detail', ai_results['error'].get('code', 'unknown'))
            print(f"\n❌ Ошибка AI обработки: {error_msg}")
            # Записываем пустые значения
            empty_fields = {
                "Чистый текст": "",
                "Фулл саммари": "", 
                "Мидл саммари": "",
                "Шорт саммари": "",
                "Материалы": ""
            }
            store_excel.write_step(excel_handle, run_id, empty_fields, log)
        
        # Шаг 8: Записываем тестовые данные (в тестовый лист)
        test_data = {
            'run_id': run_id,
            'success': ai_results.get('error') is None,
            'model': 'google-genai-independent',  # Новый независимый режим (5 запросов)
            'supadata_time_ms': supadata_time_ms,
            'ai_time_ms': ai_time_ms,
            'chars_original': chars_original,
            'chars_cleaned': chars_cleaned
        }
        store_excel.write_test_record(excel_handle, test_data, log)
        
        # Шаг 9: Закрываем Excel ресурсы
        store_excel.close(excel_handle)
        
        # Шаг 10: Итог
        print(f"\n✅ Обработка завершена! Данные сохранены в Excel (запись №{run_id})")
        log("INFO", "main", "Программа завершена успешно", run_id=run_id)
        
    except ValueError as e:
        # Закрываем Excel ресурсы при ошибке
        if excel_handle:
            store_excel.close(excel_handle)
            
        error_code = str(e)
        log("ERROR", "main", "Ошибка выполнения", error_code=error_code)
        
        # Обрабатываем различные типы ошибок
        if error_code == "invalid_url_exit":
            print("Ошибка: Пользователь не ввел корректный URL")
        elif error_code == "invalid_url_repeated":
            print("Ошибка: Повторно введен некорректный URL. Программа завершена.")
        elif error_code == "unauthorized":
            print("Ошибка: Проблемы с авторизацией API ключей")
        elif error_code == "rate_limited":
            print("Ошибка: Превышен лимит запросов API")
        elif error_code == "server_error":
            print("Ошибка: Проблемы на сервере Supadata")
        elif error_code == "job_timeout":
            print("Ошибка: Таймаут получения результата")
        elif error_code == "bad_url":
            print("Ошибка: Проверьте ссылку в браузере - сервис не может её обработать")
        elif error_code == "no_api_keys":
            print("Ошибка: Не настроены API ключи в конфигурации")
        elif error_code == "excel_file_locked":
            print("Ошибка: Excel файл заблокирован. Закройте Excel и перезапустите.")
        elif error_code.startswith("prompt_file_"):
            print("Ошибка: Проблема с файлом промтов. Проверьте prompts/yt_prompts.txt")
        elif error_code == "no_api_keys":
            print("Ошибка: Не настроены AI API ключи в конфигурации")
        elif error_code == "all_failed":
            print("Ошибка: Все AI ключи и модели исчерпаны")
        else:
            print(f"Ошибка: {error_code}")
        
        sys.exit(1)
        
    except Exception as e:
        # Закрываем Excel ресурсы при ошибке
        if excel_handle:
            store_excel.close(excel_handle)
            
        log("ERROR", "main", "Неожиданная ошибка", error=str(e))
        print(f"Неожиданная ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()