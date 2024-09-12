from tortoise import Tortoise
from loguru import logger

async def initialize_database() -> None:
    try:
        await Tortoise.init(
            db_url='sqlite://database/database.sqlite3',
            modules={'models': ['database.models.accounts']},
        )
        await Tortoise.generate_schemas(safe=True)

    except Exception as error:
        logger.error(f'Ошибка инициализации бд: {error}')
        exit(0)

async def close_database() -> None:
    try:
        await Tortoise.close_connections()
        logger.info('Соединение с бд закрыто.')
    except Exception as error:
        logger.error(f'Ошибка при попытке закрыть подключение к бд: {error}')