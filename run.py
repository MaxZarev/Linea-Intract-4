import asyncio
from random import shuffle

from loader import config

from database import initialize_database, close_database
from loguru import logger
from core.bot import Bot
from models import Account
from database import Accounts
from utils import setup

semaphore = asyncio.Semaphore(config.threads)


async def worker(account: Account):
    async with semaphore:
        logger.info(f'{account.profile_number}: Запуск аккаунта')
        try:
            async with Bot(account) as bot:
                await bot.run()
        except Exception as e:
                logger.error(f'{account.profile_number}: Ошибка в аккаунте {e}')


async def main():
    print('Версия скрипта 1.2.0')
    print('Скрипт подготовлен Zarev')
    print('Канал https://t.me/maxzarev')
    print('Вопросы https://t.me/max_zarev')

    await initialize_database()

    complete_accounts = await Accounts.get_complete_accounts()
    accounts_for_work = [account for account in config.accounts if account.profile_number not in complete_accounts]

    print(f'Всего аккаунтов: {len(config.accounts)}')
    print(f'Завершенные аккаунты: {len(complete_accounts)}')

    if config.shuffle_profiles:
        shuffle(accounts_for_work)

    tasks = [worker(account) for account in accounts_for_work]
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_database()


if __name__ == '__main__':
    setup()
    asyncio.run(main())
