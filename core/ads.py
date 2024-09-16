from __future__ import annotations

from typing import Optional
import asyncio

from aiohttp import ClientSession
from loguru import logger

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator

from models import Account
from loader import config, lock
from utils import random_sleep
from utils import get_request

class Ads:
    local_api_url = "http://local.adspower.net:50325/api/v1/"

    def __init__(self, account: Account):
        self.account = account
        self.proxy = account.proxy
        self.profile_number = account.profile_number
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.metamask = Metamask(self)

    async def run(self):
        """
        Запускает браузер в ADS и подготавливает его к работе
        :return: None
        """
        # установка прокси в ADS если включена
        if config.use_proxy:
            if self.proxy.host == "1.1.1.1":
                logger.error(
                    f'{self.profile_number}: Ошибка заполните файл с прокси или отключите использование прокси"')
                exit()
            await self.set_proxy()

        # запуск и настройка браузера
        try:
            self.browser = await self._start_browser()
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0]
            await self._prepare_browser()
        except Exception as e:
            logger.error(f"{self.profile_number}: Ошибка при запуске и настройке браузера: {e}")
            raise e

    async def _open_browser(self) -> str:
        """
        Открывает браузер в ADS по номеру профиля
        :return: параметры запущенного браузера
        """
        try:
            params = dict(serial_number=self.profile_number)
            url = self.local_api_url + 'browser/start'
            async with lock:
                await random_sleep(1, 2)
                data = await get_request(url, params)
            return data.get('data').get('ws').get('puppeteer')
        except Exception as e:
            logger.error(f"{self.profile_number}: Ошибка при открытии браузера: {e}")
            raise e

    async def _check_browser_status(self) -> Optional[str]:
        """
        Проверяет статус браузера в ADS по номеру профиля
        :return: параметры запущенного браузера
        """
        try:
            params = dict(serial_number=self.profile_number)
            url = self.local_api_url + 'browser/active'
            async with lock:
                await random_sleep(1, 2)
                data = await get_request(url, params)
            if data['data']['status'] == 'Active':
                return data.get('data').get('ws').get('puppeteer')
            return None
        except Exception as e:
            logger.error(f"{self.profile_number}: Ошибка при проверке статуса браузера: {e}")
            raise e

    async def _start_browser(self, attempts: int = 3) -> Browser:
        """
        Запускает браузер в ADS по номеру профиля.
        Делает 3 попытки прежде чем вызвать исключение.
        :return: Browser
        """
        try:
            if not (endpoint := await self._check_browser_status()):
                await asyncio.sleep(3)
                endpoint = await self._open_browser()
            await asyncio.sleep(10)
            pw = await async_playwright().start()
            return await pw.chromium.connect_over_cdp(endpoint, slow_mo=1000)
        except Exception as e:
            if attempts:
                await asyncio.sleep(5)
                return await self._start_browser(attempts - 1)
            logger.error(f"{self.profile_number}: Error не удалось запустить браузер, после 3 попыток: {e}")
            raise e

    async def _prepare_browser(self) -> None:
        """
        Закрывает все страницы кроме текущей
        :return: None
        """
        # todo: провести тесты смены разрешения экрана
        # await self.page.set_viewport_size({'width': 1920, 'height': 1080})
        try:
            for page in self.context.pages:
                if page != self.page:
                    await page.close()
        except Exception as e:
            logger.error(f"{self.profile_number}: Ошибка при закрытии страниц: {e}")
            raise e

    async def close_browser(self) -> None:
        """
        Останавливает браузер в ADS по номеру профиля
        :return:
        """
        await self.browser.close()

        params = dict(serial_number=self.profile_number)
        url = self.local_api_url + 'browser/stop'
        async with lock:
            await random_sleep(1, 2)
            try:
                await get_request(url, params)
            except Exception as e:
                logger.error(f"{self.profile_number} Ошибка при остановке браузера: {e}")
                raise e

    async def catch_page(self, url_contains: str | list[str] = None, timeout: int = 10) -> \
            Optional[Page]:
        """
        Ищет страницу по частичному совпадению url.
        :param url_contains: текст, который ищем в url или список текстов
        :param timeout:  время ожидания
        :return: страница с нужным url или None
        """
        if isinstance(url_contains, str):
            url_contains = [url_contains]

        for attempt in range(timeout):
            for page in self.context.pages:
                for url in url_contains:
                    if url in page.url:
                        return page
                    if attempt and attempt % 5 == 0:
                        await self.pages_context_reload()
                    await asyncio.sleep(1)

        logger.warning(f"{self.profile_number} Ошибка страница не найдена: {url_contains}")
        return None

    async def pages_context_reload(self):
        """
        Перезагружает контекст страниц
        :return: None
        """
        await self.context.new_page()
        await random_sleep(1, 2)
        for page in self.context.pages:
            if 'about:blank' in page.url:
                await page.close()

    async def set_proxy(self) -> None:
        """
        Устанавливает прокси для профиля в ADS
        :return: None
        """
        proxy_config = {
            "proxy_type": "http",
            "proxy_host": self.proxy.host,
            "proxy_port": self.proxy.port,
            "proxy_user": self.proxy.login,
            "proxy_password": self.proxy.password,
            "proxy_soft": "other"
        }
        ads_id = await self.get_profile_id()
        data = {
            "user_id": ads_id,
            "user_proxy_config": proxy_config
        }
        url = self.local_api_url + 'user/update'
        async with lock:
            await random_sleep(1, 2)
            async with ClientSession() as session:
                async with session.post(url, json=data,
                                        headers={"Content-Type": "application/json"}) as response:
                    await response.text()

        # смена ip мобильных прокси если включена
        if config.is_mobile_proxy:
            try:
                await get_request(config.link_change_ip)
            except:
                logger.warning(f"{self.profile_number}: Ошибка смены ip мобильного прокси")
                pass

    async def get_profile_id(self) -> str:
        """
        Запрашивает id профиля в ADS по номеру профиля
        :return: id профиля в ADS
        """
        url = self.local_api_url + 'user/list'
        params = {"serial_number": self.profile_number}
        async with lock:
            await random_sleep(1, 2)
            data = await get_request(url, params)
        return data['data']['list'][0]['user_id']


class Metamask:
    def __init__(self, ads: Ads):
        self.url = config.metamask_url
        self.ads = ads
        self.password = self.ads.account.password

    async def authorize(self) -> None:
        """
        Авторизация в метамаске
        :return: None
        """
        if self.ads.page.is_closed():
            self.ads.page = await self.ads.context.new_page()
            await self.ads._prepare_browser()

        await self.ads.page.goto(self.url, wait_until='load')
        authorized_checker = self.ads.page.get_by_test_id('account-options-menu-button')
        if await authorized_checker.count():
            logger.info(f'{self.ads.profile_number}: Уже авторизован в метамаске')
            return

        await self.ads.page.get_by_test_id('unlock-password').fill(self.password)
        await self.ads.page.get_by_test_id('unlock-submit').click()
        await self.ads.page.wait_for_load_state('load')
        await asyncio.sleep(10)
        if await self.ads.page.get_by_test_id('popover-close').count():
            await self.ads.page.get_by_test_id('popover-close').click()
            logger.info(f'{self.ads.profile_number}: Авторизован в метамаске')

        if not await authorized_checker.count():
            raise Exception(f"Error: {self.ads.profile_number} Ошибка авторизации в метамаске")

        logger.info(f"{self.ads.profile_number}: Авторизация в метамаске прошла успешно")

    async def connect(self, locator: Locator) -> None:
        """
        Подтверждает подключение метамаска к сайту во всплывающем окне метамаска.
        :param locator: локатор кнопки подключения метамаска
        :return: None
        """
        try:
            async with self.ads.context.expect_page(timeout=10) as page_catcher:
                await locator.click()
            metamask_page = await page_catcher.value
        except:
            metamask_page = await self.ads.catch_page(['connect', 'confirm-transaction'])
            if not metamask_page:
                raise Exception(f"Error: {self.ads.profile_number} Ошибка подключения метамаска")

        await metamask_page.wait_for_load_state('load')

        confirm_button = metamask_page.get_by_test_id('page-container-footer-next')
        if not await confirm_button.count():
            confirm_button = metamask_page.get_by_test_id('confirm-footer-button')

        await confirm_button.click()
        await random_sleep(1, 3)
        if not metamask_page.is_closed():
            await confirm_button.click()


    # async def import_wallet(self):
    #     """
    #     Импортирует кошелек в metamask
    #     :return:
    #     """
    #
    #     if self.ads.page.is_closed():
    #         self.ads.page = await self.ads.context.new_page()
    #         await self.ads._prepare_browser()
    #
    #     await self.ads.page.goto(self.url, wait_until='load')
    #
    #     authorized_checker = self.ads.page.get_by_test_id('account-options-menu-button')
    #
    #     if await authorized_checker.count():
    #         logger.info(f'{self.ads.profile_number}: Уже авторизован в метамаске')
    #         return
    #
    #     if await self.ads.page.get_by_test_id('unlock-password').count():
    #         await self.authorize()
    #
    #     self.open_metamask()
    #
    #     seed_list = self.seed.split(" ")
    #     if not self.password:
    #         self.password = generate_password()
    #
    #     if self.ads.find_element("//button[@data-testid='onboarding-create-wallet']", 5):
    #         self.ads.click_element("//input[@data-testid='onboarding-terms-checkbox']")
    #         sleep_random()
    #         self.ads.click_element("//button[@data-testid='onboarding-import-wallet']")
    #         self.ads.click_element("//button[@data-testid='metametrics-no-thanks']")
    #         for i, word in enumerate(seed_list):
    #             self.ads.input_text(f"//input[@data-testid='import-srp__srp-word-{i}']", word)
    #         self.ads.click_element("//button[@data-testid='import-srp-confirm']")
    #         self.ads.input_text("//input[@data-testid='create-password-new']", self.password)
    #         self.ads.input_text("//input[@data-testid='create-password-confirm']", self.password)
    #         sleep_random()
    #         self.ads.click_element("//input[@data-testid='create-password-terms']")
    #         self.ads.click_element("//button[@data-testid='create-password-import']")
    #
    #         sleep_random(3, 5)
    #         self.ads.click_element("//button[@data-testid='onboarding-complete-done']")
    #
    #         sleep_random()
    #         self.ads.click_element("//button[@data-testid='pin-extension-next']")
    #         sleep_random()
    #         self.ads.click_element("//button[@data-testid='pin-extension-done']")
    #         sleep_random(3, 3)
    #         self.ads.click_element("//button[@data-testid='popover-close']", 5)
    #         sleep_random()
    #     else:
    #         self.ads.click_element("//a[text()='Forgot password?']", 5)
    #         for i, word in enumerate(seed_list):
    #             self.ads.input_text(f"//input[@data-testid='import-srp__srp-word-{i}']", word)
    #         self.ads.input_text("//input[@data-testid='create-vault-password']", self.password)
    #         self.ads.input_text("//input[@data-testid='create-vault-confirm-password']", self.password)
    #         self.ads.click_element("//button[@data-testid='create-new-vault-submit-button']")
    #         sleep_random(3, 3)
    #         self.ads.click_element("//button[@data-testid='popover-close']", 5)
    #
    #     self.ads.click_element("//button[@data-testid='account-options-menu-button']")
    #     sleep_random()
    #
    #     self.ads.click_element("//button[@data-testid='account-list-menu-details']")
    #     sleep_random()
    #
    #     address = self.ads.get_text("//button[@data-testid='address-copy-button-text']/span/div")
    #     sleep_random()
    #
    #     write_text_to_file("new_wallets.txt", f"{self.ads.profile_number} {address} {self.password} {self.seed}")
