#!/usr/bin/env python3
"""
CLI интерфейс для Clinical Matcher
"""

import click
import asyncio
from pathlib import Path
from .processor import ClinicalDataProcessor, test_column_detection
from .config import load_config, save_config, get_config_value
from . import __version__


@click.group()
@click.version_option(version=__version__)
def cli():
    """Clinical Disease Matcher - обработка клинических данных
    
    Инструмент для сопоставления клинических диагнозов с кодами OMIM/MONDO.
    """
    pass


@cli.command()
@click.argument('files', nargs=-1, type=click.Path(exists=True), required=True)
@click.option('--api-url', default=None, help='URL API сервиса')
@click.option('--output-dir', type=click.Path(), help='Директория для результатов')
@click.option('--max-concurrent', type=int, default=None, help='Параллельные запросы')
@click.option('--test-columns', is_flag=True, help='Только проверить столбцы')
def process(files, api_url, output_dir, max_concurrent, test_columns):
    """Обработать клинические файлы
    
    Примеры:
    
    \b
    clinical-matcher process данные.xlsx
    clinical-matcher process --output-dir results/ файл1.xlsx файл2.csv
    clinical-matcher process --test-columns данные.xlsx
    """
    # Загрузка конфигурации
    config = load_config()
    
    # Переопределение параметров из командной строки
    if api_url:
        config['api_url'] = api_url
    if max_concurrent is not None:
        config['max_concurrent'] = max_concurrent
    
    # Проверка API URL
    if not config.get('api_url'):
        click.echo("❌ Ошибка: не настроен API URL", err=True)
        click.echo("Используйте: clinical-matcher configure --api-url <URL>", err=True)
        return
    
    # Создание процессора
    processor = ClinicalDataProcessor(
        api_url=config['api_url'],
        max_concurrent=config.get('max_concurrent', 5)
    )
    
    # Обработка файлов
    click.echo(f"🔧 Используется API: {config['api_url']}")
    click.echo(f"📊 Параллельных запросов: {config.get('max_concurrent', 5)}\n")
    
    async def process_files():
        total_files = len(files)
        processed = 0
        
        for file_path in files:
            file_path = Path(file_path)
            processed += 1
            
            click.echo(f"📄 [{processed}/{total_files}] Обработка: {file_path.name}")
            
            # Определение пути для сохранения
            if output_dir:
                output_dir_path = Path(output_dir)
                output_dir_path.mkdir(parents=True, exist_ok=True)
                if file_path.suffix.lower() == '.csv':
                    output_path = output_dir_path / f"{file_path.stem}_processed.csv"
                else:
                    output_path = output_dir_path / f"{file_path.stem}_processed.xlsx"
            else:
                output_path = None
            
            try:
                stats = await processor.process_excel(
                    file_path,
                    output_path,
                    test_columns=test_columns
                )
                
                if test_columns:
                    click.echo(f"  ✓ Диагноз: {stats.get('diagnosis_column', 'Не найден')}")
                    click.echo(f"  ✓ Ген: {stats.get('gene_column', 'Не найден')}")
                else:
                    if 'error' not in stats:
                        click.echo(f"  ✓ Успешно: {stats['successful']} из {stats['processed']}")
                        if stats['not_found'] > 0:
                            click.echo(f"  ⚠️  Не найдено: {stats['not_found']}")
                        if stats['errors'] > 0:
                            click.echo(f"  ❌ Ошибок: {stats['errors']}")
                
            except Exception as e:
                click.echo(f"  ❌ Ошибка: {str(e)}", err=True)
            
            click.echo()
    
    # Запуск асинхронной обработки
    asyncio.run(process_files())
    click.echo("✅ Обработка завершена")


@cli.command()
@click.option('--api-url', prompt='API URL', help='URL сервера API')
def configure(api_url):
    """Настроить подключение к API"""
    save_config({'api_url': api_url})
    click.echo(f"✅ Конфигурация сохранена")
    click.echo(f"   API URL: {api_url}")
    
    # Проверка доступности API
    click.echo("\n🔍 Проверка подключения...")
    
    async def check_api():
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/v1/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        click.echo(f"✅ API доступен: {data.get('status', 'ok')}")
                        if 'model' in data:
                            click.echo(f"   Модель: {data['model']}")
                    else:
                        click.echo(f"⚠️  API вернул статус: {response.status}")
        except Exception as e:
            click.echo(f"❌ Не удалось подключиться к API: {str(e)}", err=True)
            click.echo("   Проверьте, что сервер запущен", err=True)
    
    asyncio.run(check_api())


@cli.command()
def test():
    """Запустить встроенные тесты"""
    click.echo("🧪 Запуск тестов определения столбцов...\n")
    try:
        test_column_detection()
        click.echo("\n✅ Все тесты пройдены успешно!")
    except AssertionError as e:
        click.echo(f"\n❌ Ошибка в тестах: {str(e)}", err=True)
    except Exception as e:
        click.echo(f"\n❌ Неожиданная ошибка: {str(e)}", err=True)


@cli.command()
def config():
    """Показать текущую конфигурацию"""
    config = load_config()
    click.echo("📋 Текущая конфигурация:\n")
    for key, value in config.items():
        click.echo(f"   {key}: {value}")
    
    config_path = Path.home() / ".config" / "clinical-matcher" / "config.json"
    click.echo(f"\n📁 Файл конфигурации: {config_path}")


def main():
    """Главная точка входа"""
    cli()


if __name__ == '__main__':
    main()