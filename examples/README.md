# Примеры использования Clinical Disease Matcher

В этой директории находятся примеры файлов и скриптов для работы с системой.

## Файлы

- `example_diagnoses.csv` - пример CSV файла с диагнозами и генами
- `process_example.sh` - скрипт для демонстрации обработки файла

## Запуск примера

1. Убедитесь, что API сервер запущен:
```bash
cd ../api
docker run -p 8002:8002 --env-file .env clinical-api
```

2. Установите CLI инструмент:
```bash
cd ../cli
./scripts/install.sh
```

3. Запустите пример:
```bash
cd ../examples
./process_example.sh
```

## Формат входных данных

### CSV формат
```csv
Диагноз,Ген (symbol)
Синдром Марфана,FBN1
Дисплазия соединительной ткани,ABCD1
```

### Excel формат
Поддерживаются файлы .xlsx и .xls с аналогичной структурой.

## Формат выходных данных

К исходному файлу добавляются колонки:
```csv
Диагноз,Ген (symbol),OMIM_код,MONDO_код,Название_заболевания,Требует_уточнения
Синдром Марфана,FBN1,OMIM:154700,MONDO:0007947,Marfan syndrome,-
```

## Дополнительные примеры

### Обработка нескольких файлов
```bash
clinical-matcher process file1.xlsx file2.csv file3.xlsx
```

### Сохранение в отдельную директорию
```bash
clinical-matcher process --output-dir /path/to/results/ data.xlsx
```

### Параллельная обработка
```bash
clinical-matcher process --max-concurrent 10 large_dataset.xlsx
```