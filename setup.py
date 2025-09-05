#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт установки YT_Sum_Prod
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def copy_config_example():
    """Копирует пример конфигурационного файла, если основной файл отсутствует"""
    config_dir = Path("config_prod")
    config_file = config_dir / "app.yaml"
    config_example = config_dir / "app.yaml.example"
    
    if not config_file.exists():
        if config_example.exists():
            shutil.copy(config_example, config_file)
            print("✓ Создан файл конфигурации config_prod/app.yaml")
            print("  Пожалуйста, отредактируйте его и заполните своими значениями")
        else:
            print("✗ Файл config_prod/app.yaml.example не найден")
            return False
    else:
        print("✓ Файл конфигурации config_prod/app.yaml уже существует")
    
    return True

def install_dependencies():
    """Устанавливает зависимости Python из requirements_prod.txt"""
    requirements_file = "requirements_prod.txt"
    
    if not os.path.exists(requirements_file):
        print(f"✗ Файл {requirements_file} не найден")
        return False
    
    try:
        print("Установка зависимостей Python...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
        print("✓ Зависимости успешно установлены")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Ошибка при установке зависимостей: {e}")
        return False
    except FileNotFoundError:
        print("✗ Команда pip не найдена. Убедитесь, что Python и pip установлены")
        return False

def main():
    """Основная функция установки"""
    print("=== Установка YT_Sum_Prod ===")
    
    # Создание конфигурационного файла
    if not copy_config_example():
        sys.exit(1)
    
    print()
    
    # Установка зависимостей
    if not install_dependencies():
        sys.exit(1)
    
    print()
    print("=== Установка завершена успешно ===")
    print("Следующие шаги:")
    print("1. Отредактируйте config_prod/app.yaml и заполните своими значениями")
    print("2. Запустите бота командой: python yt_sum_bot.py")

if __name__ == "__main__":
    main()