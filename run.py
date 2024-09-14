import asyncio
import sys
from random import shuffle

from loguru import logger

from database.settings import initialize_database, close_database
from loader import config

from core.bot import Bot
from models import Account
from database import Accounts

semaphore = asyncio.Semaphore(config.threads)

def d_semaphore(func):
    async def wrapper(*args, **kwargs):
        async with semaphore:
            result = await func(*args, **kwargs)
            return result
    return wrapper


@d_semaphore
async def worker(account: Account):
    logger.info(f'{account.profile_number}: Запуск аккаунта')
    if await Accounts.get_statuses(account.profile_number):
        logger.info(f'{account.profile_number}: Аккаунт уже был сделан ранее')
        return

    async with Bot(account) as bot:
        try:
            await bot.run()
        except Exception as e:
            logger.error(f'{account.profile_number}: Ошибка в аккаунте {e}')


async def main():
    print('Версия скрипта 1.0.0')
    print('Скрипт подготовлен Zarev')
    print('Канал https://t.me/maxzarev')
    print('Вопросы https://t.me/max_zarev')

    await initialize_database()
    accounts = config.accounts
    if config.shuffle_profiles:
        shuffle(accounts)
    tasks = [worker(account) for account in accounts]
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_database()


if __name__ == '__main__':
    asyncio.run(main())
