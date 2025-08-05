"""
Управление конфигурацией CLI
"""

import json
import os
from pathlib import Path
from typing import Dict, Any


def get_config_path() -> Path:
    """Получить путь к файлу конфигурации"""
    config_dir = Path.home() / ".config" / "clinical-matcher"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config() -> Dict[str, Any]:
    """Загрузить конфигурацию"""
    config_path = get_config_path()
    
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # Конфигурация по умолчанию
    default_config = {
        "api_url": "http://localhost:8002",
        "max_concurrent": 5,
        "timeout": 60
    }
    
    # Проверяем переменные окружения
    if "CLINICAL_MATCHER_API_URL" in os.environ:
        default_config["api_url"] = os.environ["CLINICAL_MATCHER_API_URL"]
    
    return default_config


def save_config(config: Dict[str, Any]) -> None:
    """Сохранить конфигурацию"""
    config_path = get_config_path()
    
    # Загружаем существующую конфигурацию
    existing = load_config()
    
    # Обновляем только измененные поля
    existing.update(config)
    
    # Сохраняем
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def get_config_value(key: str, default: Any = None) -> Any:
    """Получить значение из конфигурации"""
    config = load_config()
    return config.get(key, default)