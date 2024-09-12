import asyncio
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
            try:
                await asyncio.sleep(3)
                result = await func(*args, **kwargs)
                return result
            except Exception as error:
                logger.error(f'Произошла ошибка: {error}')
    return wrapper


@d_semaphore
async def worker(account: Account):
    if await Accounts.get_statuses(account.profile_number):
        return
    bot = Bot(account)
    await bot.run()

async def main():
    print('Скрипт подготовлен Zarev')
    print('Канал https://t.me/maxzarev')
    print('Вопросы https://t.me/max_zarev')

    await initialize_database()
    accounts = config.accounts
    tasks = [worker(account) for account in accounts]
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_database()


if __name__ == '__main__':
    asyncio.run(main())
