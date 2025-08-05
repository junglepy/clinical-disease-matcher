#!/bin/bash
# Пример обработки клинических данных

# Убедитесь, что API сервер запущен на http://localhost:8002
# и CLI инструмент установлен

echo "=== Пример обработки клинических данных ==="
echo ""

# 1. Настройка API сервера
echo "1. Настройка подключения к API..."
clinical-matcher configure --api-url http://localhost:8002

# 2. Проверка определения столбцов
echo ""
echo "2. Проверка автоматического определения столбцов..."
clinical-matcher process --test-columns example_diagnoses.csv

# 3. Обработка файла
echo ""
echo "3. Обработка файла с диагнозами..."
clinical-matcher process example_diagnoses.csv --output-dir results/

# 4. Просмотр результатов
echo ""
echo "4. Результаты сохранены в:"
echo "   results/example_diagnoses_processed.csv"
echo ""
echo "Готово!"