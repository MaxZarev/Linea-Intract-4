import asyncio
import random

from loguru import logger

from core.ads import Ads
from core.onchain import Tokens, Onchain
from core.daps import Zeroland, Wowmax, Nile
from loader import config
from database import Accounts
from models import Account
from models import Quest
from utils import random_sleep


class Bot:

    def __init__(self, account: Account):
        self.ads = Ads(account)
        self.onchain = Onchain(account)
        self.zeroland = Zeroland(account)
        self.wowmax = Wowmax(account)
        self.nile = Nile(account, self.wowmax)

    async def run(self) -> None:

        await Accounts.create_account(self.ads.profile_number, self.onchain.address)

        await self.ads.run()
        await self.ads.metamask.authorize()

        quests = [
            Quest(2, 'Supply any asset on Linea on Zerolend'),
            Quest(1, 'Provide liquidity to Zero/ETH on Nile'),
            Quest(3, 'Provide liquidity to Nile/ETH on Nile'),
            Quest(4, 'Stake Zero/ETH on Zerolend.')
        ]
        await self.shuffle_quest(quests)
        # await self.check_statuses(quests)
        await self.run_quests(quests)

        if config.is_withdraw_to_cex:
            await self.onchain.withdraw_to_cex()

        logger.info(f"{self.ads.profile_number}: Все квесты выполнены")


    async def shuffle_quest(self, quests: list[Quest]) -> None:
        """
        Перемешивает первые три квеста
        :param quests:
        :return:
        """
        first_three_quests = quests[:3]
        random.shuffle(first_three_quests)
        quests[:3] = first_three_quests

    async def check_statuses(self, quests: list[Quest]) -> None:
        """
        Проверяет статусы квестов на сайте interact.io
        :param quests: список квестов
        :return:
        """
        await self.open_interact()

        for quest in quests:
            await self.check_status(quest.number, quest.text)

    async def run_quests(self, quests: list[Quest]) -> None:
        """
        Запускает по очереди квесты из списка
        :param quests: список квестов
        :return: None
        """
        for _ in range(3):
            try:
                for quest in quests:
                    logger.info(f"{self.ads.profile_number}: Запускаем квест {quest.number} {quest.text}")
                    run_quest = getattr(self, f'quest_{quest.number}')
                    await run_quest(quest.number, quest.text)
                return
            except Exception as e:
                logger.error(f"{self.ads.profile_number}: Ошибка при выполнении квестов {e}")
                raise e


    async def quest_1(self, quest_number: int, quest_text: str):
        if not await Accounts.get_status(self.ads.profile_number, 1):
            await self.nile.add_liquidity_eth(Tokens.ZERO)
            await self.interact_quest(quest_number, quest_text)

        await self.nile.remove_liquidity(Tokens.ZERO)
        await self.wowmax.swap(Tokens.ZERO, Tokens.ETH)

    async def quest_2(self, quest_number: int, quest_text: str):
        if not await Accounts.get_status(self.ads.profile_number, 2):
            await self.zeroland.supply_zerolend()
            await self.interact_quest(quest_number, quest_text)
        await self.zeroland.withdraw_zerolend()

    async def quest_3(self, quest_number: int, quest_text: str):
        if not await Accounts.get_status(self.ads.profile_number, 3):
            await self.nile.add_liquidity_eth(Tokens.NILE)
            await self.interact_quest(quest_number, quest_text)
        await self.nile.remove_liquidity(Tokens.NILE)
        await self.wowmax.swap(Tokens.NILE, Tokens.ETH)

    async def quest_4(self, quest_number: int, quest_text: str):
        if not await Accounts.get_status(self.ads.profile_number, 4):
            await self.nile.stake()
            await self.interact_quest(quest_number, quest_text)

    async def open_interact(self):
        try:
            await self.ads.page.goto('https://www.intract.io/quest/66bb5618c8ff56cba848ea8f')
        except Exception:
            await self.open_interact()
        await random_sleep(3, 5)

        if await self.ads.page.get_by_text('Sign In').count() > 0:
            logger.info(f"{self.ads.profile_number}: Запускаем подключение кошелька")
            await self.ads.page.get_by_text('Sign In').click()
            await self.ads.metamask.connect(self.ads.page.locator('//div[text()="MetaMask"]'))
            await asyncio.sleep(5)
            signature_page = await self.ads.catch_page('signature-request')
            await signature_page.wait_for_load_state('load')
            await signature_page.get_by_test_id('page-container-footer-next').click()
            await self.ads.page.wait_for_load_state('load')

    async def interact_quest(self, quest_number: int, quest_text: str) -> bool:
        """
        Прокликивает задание на Zerolend
        :return:
        """
        if await Accounts.get_status(self.ads.profile_number, quest_number):
            logger.info(f"{self.ads.profile_number}: Квест {quest_number} уже пройден ранее")
            return True

        logger.info(f"{self.ads.profile_number}: Пробуем пройти квест на interact {quest_number}")
        await self.open_interact()

        quest_block = self.ads.page.locator('//div[contains(@class, "task_trigger_container")]',
                                            has_text=quest_text)

        if await quest_block.get_by_alt_text('check task logo badge').is_visible():
            logger.info(f"{self.ads.profile_number}: Квест {quest_number} пройден")
            await Accounts.change_status(self.ads.profile_number, quest_number)
            return True

        await self.ads.page.get_by_text(quest_text).click()
        await self.ads.page.locator('div.modal-dialog:visible').get_by_role('button').filter(
            has_not_text='Continue').click()
        await self.ads.page.get_by_role('button', name='Verify').click()

        await random_sleep(3, 5)
        if await self.ads.page.get_by_role('heading', name='Choose primary wallet').count() > 0:
            await self.ads.page.locator('div.tab-link-text:visible').click()
            await self.ads.page.get_by_role('button', name='Confirm').click()
            await random_sleep(3, 5)
        await self.interact_quest(quest_number, quest_text)

    async def check_status(self, quest_number: int, quest_text: str) -> None:
        quest_block = self.ads.page.locator('//div[contains(@class, "task_trigger_container")]',
                                            has_text=quest_text)

        if await quest_block.get_by_alt_text('check task logo badge').is_visible():
            await Accounts.change_status(self.ads.profile_number, quest_number)
