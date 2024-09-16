import asyncio
import random

from core.ads import Ads
from core.onchain import Tokens, Onchain
from core.daps import Zeroland, Wowmax, Nile
from loader import config
from database import Accounts
from models import Account, Quest
from utils import random_sleep, get_request

from loguru import logger


class Bot:

    def __init__(self, account: Account):
        self.ads = Ads(account)
        self.onchain = Onchain(account)
        self.zeroland = Zeroland(account)
        self.wowmax = Wowmax(account)
        self.nile = Nile(account, self.wowmax)

    async def __aenter__(self):
        await self.tg_alert(f"Запуск аккаунта {self.ads.profile_number}")
        logger.info(f"Запуск аккаунта {self.ads.profile_number}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.ads.close_browser()
        if exc_type is None:
            logger.success(f"Аккаунт {self.ads.profile_number} завершен")
            await self.tg_alert(f"Аккаунт {self.ads.profile_number} завершен")
        elif issubclass(exc_type, asyncio.TimeoutError):
            logger.error(f"Аккаунт {self.ads.profile_number} завершен по таймауту")
            await self.tg_alert(f"Аккаунт {self.ads.profile_number} завершен по таймауту")
        else:
            logger.error(f"Аккаунт {self.ads.profile_number} завершен с ошибкой {exc_val}")
            await self.tg_alert(f"Аккаунт {self.ads.profile_number} завершен с ошибкой {exc_val}")
        return False

    async def run(self) -> None:
        """
        Запуск основной логики бота, проверка квестов на сайте interact.io.
        Выполнение квестов по списку в ончейн с пополнением с биржи.
        Прокликивание квестов на сайте interact.io
        Вывод остатка ликвидности на биржу
        :return: None
        """
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
        await self.check_statuses(quests)
        await self.run_quests(quests)

        if config.is_withdraw_to_cex:
            await self.onchain.withdraw_to_cex()

        # await get_request(f"/send_message", {
        #     "chat_id": config.telegram_chat_id,
        #     "mesage": f"Аккаунт {self.ads.profile_number} выполнил все квест
        # #
        # # requests.post(f"https://api.telegram.org/bot{config.TG_TOKEN}/sendMessage", json={
        # #     "chat_id": ,
        # #     "text": message
        # # })

    async def shuffle_quest(self, quests: list[Quest]) -> None:
        """
        Перемешивает первые три квеста, поскольку они выполняются в первую очередь.
        :param quests:
        :return: None
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
        for attempt in range(3):
            try:
                for quest in quests:
                    logger.info(f"{self.ads.profile_number}: Запускаем квест {quest.number} {quest.text}")
                    await self.run_quest(quest.number, quest.text)
                break
            except Exception as e:
                logger.error(f"{self.ads.profile_number}: Ошибка при выполнении квестов {e}")
                if attempt == 2:
                    raise e

    async def run_quest(self, quest_number: int, quest_text: str) -> None:
        """
        Выполнение квеста.
        :param quest_number: номер квеста
        :param quest_text: текст квеста, для поиска кнопок.
        :param attempts: количество попыток запустить квест
        :return: None
        """
        try:
            if quest_number == 1:
                if not await Accounts.get_status(self.ads.profile_number, quest_number):
                    await self.nile.add_liquidity_eth(Tokens.ZERO)
                    await self.interact_quest(quest_number, quest_text)

                await self.nile.remove_liquidity(Tokens.ZERO)
                await self.wowmax.swap(Tokens.ZERO, Tokens.ETH)

            elif quest_number == 2:
                if not await Accounts.get_status(self.ads.profile_number, quest_number):
                    await self.zeroland.supply_zerolend()
                    await self.interact_quest(quest_number, quest_text)
                await self.zeroland.withdraw_zerolend()

            elif quest_number == 3:
                if not await Accounts.get_status(self.ads.profile_number, quest_number):
                    await self.nile.add_liquidity_eth(Tokens.NILE)
                    await self.interact_quest(quest_number, quest_text)
                await self.nile.remove_liquidity(Tokens.NILE)
                await self.wowmax.swap(Tokens.NILE, Tokens.ETH)

            elif quest_number == 4:
                if not await Accounts.get_status(self.ads.profile_number, quest_number):
                    await self.nile.stake()
                    await self.interact_quest(quest_number, quest_text)

        except Exception as e:
            logger.error(f"{self.ads.profile_number}: Ошибка при выполнении квеста {quest_number} {e}")
            raise e

    async def open_interact(self) -> None:
        """
        Открывает сайт interact.io и подключает кошелек метамаск.
        :return: None
        """

        for attempt in range(3):
            try:
                await self.ads.page.goto('https://www.intract.io/quest/66bb5618c8ff56cba848ea8f',
                                         wait_until='load', timeout=30000)
                break
            except Exception:
                if attempt == 9:
                    raise Exception(f"{self.ads.profile_number} Не удалось открыть сайт interact.io")

                logger.warning(
                    f"{self.ads.profile_number}: Не удалось нормально открыть сайт interact.io, пробуем еще раз")
                await random_sleep(3, 5)

        if await self.ads.page.get_by_text('Sign In').count():
            logger.info(f"{self.ads.profile_number}: Запускаем подключение кошелька")
            await self.ads.page.get_by_text('Sign In').click()
            await self.ads.metamask.connect(self.ads.page.locator('//div[text()="MetaMask"]'))
            await asyncio.sleep(5)
            signature_page = await self.ads.catch_page('confirm-transaction')
            if signature_page:
                await signature_page.wait_for_load_state('load')
                confirm_button = signature_page.get_by_test_id('page-container-footer-next')
                if not await confirm_button.count():
                    confirm_button = signature_page.get_by_test_id('confirm-footer-button')
                await confirm_button.click()
                await asyncio.sleep(5)

    async def interact_quest(self, quest_number: int, quest_text: str) -> bool:
        """
        Прокликивает задание на Zerolend
        :return:
        """
        if await Accounts.get_status(self.ads.profile_number, quest_number):
            return True

        logger.info(f"{self.ads.profile_number}: Пробуем пройти квест на interact {quest_number}")
        await self.open_interact()

        if await self.check_status(quest_number, quest_text):
            logger.info(f"{self.ads.profile_number}: Квест {quest_number} пройден")
            return True

        await self.ads.page.get_by_text(quest_text).scroll_into_view_if_needed(timeout=10000)
        await self.ads.page.get_by_text(quest_text).click(timeout=10000)
        await random_sleep(3, 5)
        await self.ads.page.locator('div.modal-dialog:visible').get_by_role('button').filter(
            has_not_text='Continue', has=self.ads.page.locator('i')).first.click(timeout=10000)
        verify_button = self.ads.page.get_by_role('button', name='Verify')

        await verify_button.scroll_into_view_if_needed(timeout=10000)
        await verify_button.click(timeout=10000)

        await random_sleep(5, 10)
        if await self.ads.page.get_by_role('heading', name='Choose primary wallet').count():
            await self.ads.page.locator('div.tab-link-text:visible').click(timeout=10000)
            await self.ads.page.get_by_role('button', name='Confirm').click(timeout=10000)
            await random_sleep(3, 5)
            await verify_button.click(timeout=10000)
            await random_sleep(5, 10)

        if await self.check_status(quest_number, quest_text):
            logger.info(f"{self.ads.profile_number}: Квест {quest_number} пройден")
            return True

        raise Exception(f"{self.ads.profile_number}: Квест {quest_number} не пройден")

    async def check_status(self, quest_number: int, quest_text: str) -> bool:
        """
        Проверяет статус квеста на сайте interact.io
        :param quest_number:
        :param quest_text:
        :return: True если квест пройден, False если нет
        """
        quest_block = self.ads.page.locator('//div[contains(@class, "task_trigger_container")]',
                                            has_text=quest_text)

        if await quest_block.get_by_alt_text('check task logo badge').is_visible():
            await Accounts.change_status(self.ads.profile_number, quest_number)
            return True
        return False

    async def tg_alert(self, message: str) -> None:
        """
        Отправляет сообщение в телеграм
        :param message: текст сообщения
        :return: None
        """
        if not config.tg_token:
            return
        try:
            url = f"https://api.telegram.org/bot{config.tg_token}/sendMessage"
            await get_request(url, {"chat_id": config.tg_chat_id, "text": message})
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение в телеграм {e}")

