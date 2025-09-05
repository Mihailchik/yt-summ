import re


def get_source_url(config) -> str:
    """
    Показать приглашение: 'Вставь ссылку на YouTube (Enter — тестовая): '
    Если пользователь нажал Enter — вернуть config.test.default_url.
    Выполнить базовую валидацию: строка похожа на http/https URL. Иначе — вернуть специальную ошибку для main.
    """
    default_url = config.get('test', {}).get('default_url', '')
    
    # Первая попытка ввода
    user_input = input("Вставь ссылку на YouTube (Enter — тестовая): ").strip()
    
    # Если пустой ввод - возвращаем дефолтную ссылку
    if not user_input:
        return default_url
    
    # Проверяем валидность URL
    if _is_valid_url(user_input):
        return user_input
    
    # Если невалидный URL - даем вторую попытку
    print("Ошибка: введенная строка не похожа на корректный URL")
    user_input = input("Попробуйте еще раз (или Enter для выхода): ").strip()
    
    # Если снова пустой ввод - выходим
    if not user_input:
        raise ValueError("invalid_url_exit")
    
    # Проверяем валидность второй попытки
    if _is_valid_url(user_input):
        return user_input
    
    # Если и вторая попытка невалидна - выходим с ошибкой
    raise ValueError("invalid_url_repeated")


def _is_valid_url(url: str) -> bool:
    """Базовая валидация URL - проверяем что строка начинается с http/https"""
    url_pattern = re.compile(
        r'^https?://'  # http:// или https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # опциональный порт
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))