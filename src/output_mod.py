def print_preview(lang: str, content: str, preview_chars: int, log) -> None:
    """
    Напечатать: 'Язык: <lang>' и 'Длина: <N> символов', затем 'Первые <preview_chars> символов:' и сам префью.
    Префью формировать как content[:preview_chars] с заменой \n на пробел.
    Залогировать факт печати префью.
    """
    # Выводим информацию о языке и длине
    print(f"Язык: {lang}")
    print(f"Длина: {len(content)} символов")
    
    # Формируем и выводим превью
    preview = content[:preview_chars].replace('\n', ' ')
    print(f"Первые {preview_chars} символов:")
    print(preview)
    
    # Логируем факт печати
    log("INFO", "output_mod", "Превью транскрипта выведено", 
        lang=lang, length=len(content), preview_chars=preview_chars)