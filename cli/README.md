# CLI инструмент Clinical Matcher

Инструмент командной строки для обработки клинических Excel/CSV файлов с автоматическим сопоставлением диагнозов и кодов OMIM/MONDO.

## Требования

- Python 3.7 или выше
- Unix-подобная система (macOS, Linux, WSL)

## Установка

### Автоматическая установка (рекомендуется)

```bash
./scripts/install.sh
```

Скрипт автоматически:
- Создаст виртуальное окружение в `~/.clinical-matcher-venv`
- Установит все зависимости
- Создаст исполняемый файл в `~/bin/clinical-matcher`
- Настроит конфигурацию по умолчанию
- **Определит вашу оболочку** (bash/zsh/fish) и предложит добавить в PATH

#### Настройка PATH

Установщик предложит три варианта:

1. **Автоматически добавить в PATH** - добавит нужную команду в ваш `.bashrc`, `.zshrc` или `config.fish`
2. **Добавить вручную** - покажет точную команду для вашей оболочки
3. **Пропустить** - вы будете использовать полный путь `~/bin/clinical-matcher`

После добавления в PATH перезапустите терминал или выполните:
```bash
source ~/.zshrc  # для zsh (macOS по умолчанию)
source ~/.bashrc # для bash (Linux по умолчанию)
```

### Ручная установка

```bash
# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите пакет
pip install -e .

# Создайте конфигурацию
mkdir -p ~/.config/clinical-matcher
echo '{
  "api_url": "http://localhost:8002",
  "max_concurrent": 5,
  "timeout": 60
}' > ~/.config/clinical-matcher/config.json
```

## Использование

### Основные команды

```bash
# Справка
clinical-matcher --help

# Версия
clinical-matcher --version

# Настройка API сервера
clinical-matcher configure --api-url http://api-server:8002

# Обработка одного файла
clinical-matcher process данные.xlsx

# Обработка нескольких файлов
clinical-matcher process файл1.xlsx файл2.csv файл3.xlsx

# Сохранение результатов в отдельную директорию
clinical-matcher process --output-dir results/ данные.xlsx

# Проверка определения столбцов без обработки через API
clinical-matcher process --test-columns данные.xlsx

# Запуск встроенных тестов
clinical-matcher test

# Показать текущую конфигурацию
clinical-matcher config
```

### Параметры команды process

- `--api-url URL` - переопределить URL API для конкретного запуска
- `--output-dir PATH` - директория для сохранения результатов
- `--max-concurrent N` - количество параллельных запросов (по умолчанию: 5)
- `--test-columns` - только проверить автоматическое определение столбцов

## Формат данных

### Поддерживаемые форматы
- Excel (.xlsx, .xls)
- CSV (.csv)

### Автоматическое определение столбцов

CLI использует интеллектуальное определение столбцов:

**Столбец диагноза** (обязательный):
- Точные совпадения: `диагноз`, `диагноз*`, `diagnosis`, `заключение`
- Fuzzy matching: столбцы содержащие слова `диагноз` или `diagnosis`

**Столбец гена** (опциональный):
- Точные совпадения: `ген (symbol)`, `ген`, `gene`, `gene symbol`, `gene name`
- Fuzzy matching: столбцы содержащие слова `ген` или `gene`
- Исключения: игнорирует `генотип`, `генетический`

### Обработка пустых значений

Следующие значения считаются пустыми и пропускаются:
- `-`, `–`, `—`
- `nan`, `NaN`, `None`, `null`, `NULL`
- `<NULL>`, `<null>`
- `N/A`, `n/a`
- `#N/A`, `#VALUE!`
- Пустые строки

## Результаты

К исходному файлу добавляются колонки:
- `OMIM_код` - код заболевания в базе OMIM
- `MONDO_код` - код заболевания в базе MONDO
- `Название_заболевания` - стандартизированное название (приоритет MONDO)
- `Требует_уточнения` - пометки о необходимости проверки:
  - "OMIM не найден" - если в первом результате нет OMIM кода
  - "MONDO не найден" - если в первом результате нет MONDO кода
  - Ближайшие альтернативы из последующих результатов
  - Специальные сообщения от API о необходимости уточнения

## Конфигурация

Файл конфигурации: `~/.config/clinical-matcher/config.json`

```json
{
  "api_url": "http://localhost:8002",
  "max_concurrent": 5,
  "timeout": 60
}
```

Поддерживается переменная окружения:
```bash
export CLINICAL_MATCHER_API_URL=http://api-server:8002
```

## Примеры использования

### Обработка реальных клинических данных

```bash
# NGS данные
clinical-matcher process "Данные по заключениям NGS_2023_12_22.xlsx" \
  --output-dir results/ngs/

# WGS данные  
clinical-matcher process "Таблица_с_находками_по_WGS.xlsx" \
  --output-dir results/wgs/

# Пакетная обработка
clinical-matcher process data/clinical/*.xlsx \
  --output-dir results/ \
  --max-concurrent 10
```

### Интеграция в pipeline

```bash
#!/bin/bash
# process_clinical_data.sh

API_URL="http://api-server:8002"
INPUT_DIR="./input"
OUTPUT_DIR="./output"
LOG_FILE="./process.log"

# Настройка
clinical-matcher configure --api-url $API_URL

# Обработка всех файлов
for file in $INPUT_DIR/*.xlsx; do
    echo "Processing: $file" | tee -a $LOG_FILE
    clinical-matcher process "$file" \
        --output-dir $OUTPUT_DIR \
        2>&1 | tee -a $LOG_FILE
done

echo "Processing complete" | tee -a $LOG_FILE
```

## Отладка

Для включения подробного логирования отредактируйте файл `processor.py`:
```python
# Измените уровень логирования
logger.setLevel(logging.DEBUG)
```

## Известные ограничения

1. Размер файла ограничен доступной памятью
2. Скорость обработки зависит от API сервера (10-20 сек на диагноз)
3. Требуется стабильное интернет-соединение для работы с API
4. Максимальное количество параллельных запросов ограничено настройками API сервера

## Требования

- Python 3.7+
- API сервер clinical-disease-matcher
- Интернет-соединение для работы с API