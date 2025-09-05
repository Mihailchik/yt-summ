#!/bin/bash

# Скрипт установки YT_Sum_Prod
# Проверяет наличие Python, устанавливает зависимости и копирует конфигурационный файл

set -e  # Завершить выполнение при ошибке

echo "=== Установка YT_Sum_Prod ==="

# Проверка наличия Python
echo "Проверка наличия Python..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo "Найден Python3: $($PYTHON_CMD --version)"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    echo "Найден Python: $($PYTHON_CMD --version)"
else
    echo "Python не найден. Пожалуйста, установите Python 3.10 или выше."
    exit 1
fi

# Проверка версии Python (минимальная версия 3.10)
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    echo "Требуется Python 3.10 или выше. Установленная версия: $PYTHON_VERSION"
    exit 1
fi

echo "Версия Python подходит: $PYTHON_VERSION"

# Создание виртуального окружения
echo "Создание виртуального окружения..."
$PYTHON_CMD -m venv venv
echo "Виртуальное окружение создано"

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate

# Обновление pip
echo "Обновление pip..."
pip install --upgrade pip

# Установка зависимостей
echo "Установка зависимостей из requirements_prod.txt..."
if [ -f "requirements_prod.txt" ]; then
    pip install -r requirements_prod.txt
    echo "Зависимости успешно установлены"
else
    echo "Файл requirements_prod.txt не найден"
    exit 1
fi

# Копирование конфигурационного файла
echo "Копирование конфигурационного файла..."
if [ -f "config_prod/app.yaml.example" ]; then
    if [ ! -f "config_prod/app.yaml" ]; then
        cp config_prod/app.yaml.example config_prod/app.yaml
        echo "Файл конфигурации config_prod/app.yaml создан из примера"
        echo "Пожалуйста, отредактируйте его и заполните своими значениями"
    else
        echo "Файл конфигурации config_prod/app.yaml уже существует"
    fi
else
    echo "Файл config_prod/app.yaml.example не найден"
    exit 1
fi

echo ""
echo "=== Установка завершена успешно ==="
echo "Следующие шаги:"
echo "1. Отредактируйте config_prod/app.yaml и заполните своими значениями"
echo "2. Активируйте виртуальное окружение: source venv/bin/activate"
echo "3. Запустите бота: python yt_sum_bot.py"