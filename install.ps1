# Скрипт установки YT_Sum_Prod для Windows
# Проверяет наличие Python, устанавливает зависимости и копирует конфигурационный файл

Write-Host "=== Установка YT_Sum_Prod ===" -ForegroundColor Green

# Проверка наличия Python
Write-Host "Проверка наличия Python..." -ForegroundColor Yellow
$pythonVersion = $null
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python") {
        Write-Host "Найден $pythonVersion" -ForegroundColor Green
        $pythonCmd = "python"
    }
} catch {
    try {
        $pythonVersion = python3 --version 2>&1
        if ($pythonVersion -match "Python") {
            Write-Host "Найден $pythonVersion" -ForegroundColor Green
            $pythonCmd = "python3"
        }
    } catch {
        Write-Host "Python не найден. Пожалуйста, установите Python 3.10 или выше." -ForegroundColor Red
        exit 1
    }
}

if (-not $pythonCmd) {
    Write-Host "Python не найден. Пожалуйста, установите Python 3.10 или выше." -ForegroundColor Red
    exit 1
}

# Проверка версии Python (минимальная версия 3.10)
$versionMatch = [regex]::Match($pythonVersion, "Python (\d+)\.(\d+)")
if ($versionMatch.Success) {
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value
    
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "Требуется Python 3.10 или выше. Установленная версия: $pythonVersion" -ForegroundColor Red
        exit 1
    }
    Write-Host "Версия Python подходит: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "Не удалось определить версию Python" -ForegroundColor Red
    exit 1
}

# Создание виртуального окружения
Write-Host "Создание виртуального окружения..." -ForegroundColor Yellow
& $pythonCmd -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка при создании виртуального окружения" -ForegroundColor Red
    exit 1
}
Write-Host "Виртуальное окружение создано" -ForegroundColor Green

# Активация виртуального окружения
Write-Host "Активация виртуального окружения..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка при активации виртуального окружения" -ForegroundColor Red
    exit 1
}

# Обновление pip
Write-Host "Обновление pip..." -ForegroundColor Yellow
pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка при обновлении pip" -ForegroundColor Red
    exit 1
}

# Установка зависимостей
Write-Host "Установка зависимостей из requirements_prod.txt..." -ForegroundColor Yellow
if (Test-Path "requirements_prod.txt") {
    pip install -r requirements_prod.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Ошибка при установке зависимостей" -ForegroundColor Red
        exit 1
    }
    Write-Host "Зависимости успешно установлены" -ForegroundColor Green
} else {
    Write-Host "Файл requirements_prod.txt не найден" -ForegroundColor Red
    exit 1
}

# Копирование конфигурационного файла
Write-Host "Копирование конфигурационного файла..." -ForegroundColor Yellow
if (Test-Path "config_prod\app.yaml.example") {
    if (-not (Test-Path "config_prod\app.yaml")) {
        Copy-Item "config_prod\app.yaml.example" "config_prod\app.yaml"
        Write-Host "Файл конфигурации config_prod\app.yaml создан из примера" -ForegroundColor Green
        Write-Host "Пожалуйста, отредактируйте его и заполните своими значениями" -ForegroundColor Yellow
    } else {
        Write-Host "Файл конфигурации config_prod\app.yaml уже существует" -ForegroundColor Green
    }
} else {
    Write-Host "Файл config_prod\app.yaml.example не найден" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Установка завершена успешно ===" -ForegroundColor Green
Write-Host "Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Отредактируйте config_prod\app.yaml и заполните своими значениями" -ForegroundColor Yellow
Write-Host "2. Активируйте виртуальное окружение: .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "3. Запустите бота: python yt_sum_bot.py" -ForegroundColor Yellow