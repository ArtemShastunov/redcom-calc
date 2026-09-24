# Redcom Calc

Калькулятор абонентской платы «Рэдком».

## Структура

- `src/redcom_calc/` — ядро: домен и CLI
- `tests/` — тесты ядра
- `desktop/app_gui.py` — графический интерфейс на Tkinter

## Установка (dev)

    uv venv
    .\.venv\Scripts\Activate.ps1
    uv pip install -e ".[dev]"

## CLI

    redcom-calc
    # или
    python -m redcom_calc

## Тесты

    pytest

## Сборка десктопного .exe

    uv pip install pyinstaller
    cd desktop
    pyinstaller --onefile --windowed --name=RedcomCalc app_gui.py

Готовый файл: `desktop\dist\RedcomCalc.exe`. Работает на любом Windows без установки Python.
