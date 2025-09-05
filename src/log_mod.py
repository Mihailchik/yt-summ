import os
from datetime import datetime


def log(level: str, module: str, msg: str, **kv) -> str:
    """
    Формат строки:
    [ISO8601][<module>][<level>] <msg> key1=val1 key2=val2 ...
    Назначение: stdout; если logging.to_file=true — дублировать в /logs/app.log.
    Уровни: DEBUG, INFO, WARN, ERROR.
    """
    # Формируем временную метку в ISO8601
    timestamp = datetime.now().isoformat()
    
    # Формируем дополнительные параметры
    kv_str = " ".join([f"{k}={v}" for k, v in kv.items()])
    kv_part = f" {kv_str}" if kv_str else ""
    
    # Формируем полное сообщение
    log_message = f"[{timestamp}][{module}][{level}] {msg}{kv_part}"
    
    # Выводим в stdout
    print(log_message)
    
    # Записываем в файл если включено
    if _log_to_file:
        try:
            with open("logs/app.log", "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        except Exception as e:
            print(f"[{timestamp}][log_mod][ERROR] Failed to write to log file: {e}")
    
    return log_message


# Глобальная переменная для контроля файлового логирования
_log_to_file = False


def init_logging(config):
    """Инициализация логирования на основе конфига"""
    global _log_to_file
    _log_to_file = config.get('logging', {}).get('to_file', False)
    
    if _log_to_file:
        os.makedirs("logs", exist_ok=True)