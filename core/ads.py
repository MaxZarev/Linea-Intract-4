from __future__ import annotations

from typing import Optional
import asyncio

from httpx import AsyncClient
from loguru import logger

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator

from models import Account
from loader import config
from utils import random_sleep

lock = asyncio.Lock()


class Ads:
    local_api_url = "http://local.adspower.net:50325/api/v1/"

    def __init__(self, account: Account):
        self.account = account
        self.proxy = account.proxy
        self.profile_number = account.profile_number
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session = AsyncClient()
        self.metamask = Metamask(self)

    async def run(self):
        self.browser = await self._start_browser()
        self.context = self.browser.contexts[0]
        self.page = self.context.pages[0]
        await self._prepare_browser()
        if config.use_proxy:
            await self.set_proxy()

    async def _open_browser(self) -> str:
        """
        Открывает браузер в ADS по номеру профиля
        :return: параметры запущенного браузера
        """
        params = dict(serial_number=self.profile_number)
        url = self.local_api_url + 'browser/start'
        async with lock:
            await random_sleep(1, 2)
            response = await self.session.get(url, params=params)
        data = response.json()
        return data.get('data').get('ws').get('puppeteer')

    async def _check_browser_status(self) -> Optional[str]:
        """
        Проверяет статус браузера в ADS по номеру профиля
        :return: параметры запущенного браузера
        """
        params = dict(serial_number=self.profile_number)
        url = self.local_api_url + 'browser/active'
        async with lock:
            await random_sleep(1, 2)
            response = await self.session.get(url, params=params)
        data = response.json()
        if data['data']['status'] == 'Active':
            return data.get('data').get('ws').get('puppeteer')
        return None

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
            await asyncio.sleep(5)
            pw = await async_playwright().start()
            return await pw.chromium.connect_over_cdp(endpoint, slow_mo=1000)
        except Exception as e:
            if attempts:
                await asyncio.sleep(5)
                return await self._start_browser(attempts - 1)
            raise e

    async def _prepare_browser(self) -> None:
        """
        Закрывает все страницы кроме текущей
        :return: None
        """
        for page in self.context.pages:
            if page != self.page:
                await page.close()

    async def close_browser(self) -> None:
        """
        Останавливает браузер в ADS по номеру профиля
        :return:
        """
        params = dict(serial_number=self.profile_number)
        url = self.local_api_url + 'browser/stop'
        async with lock:
            await random_sleep(1, 2)
            await self.session.get(url, params=params)

    async def catch_page(self, url_contains: str, timeout: int = 10) -> Page:
        """
        Ищет страницу по частичному совпадению url.
        Вызывает исключение если страница не найдена в течении timeout секунд.
        :param url_contains: текст, который ищем в url
        :param timeout:  время ожидания
        :return: страница с нужным url
        """
        for _ in range(timeout):
            for page in self.context.pages:
                if url_contains in page.url:
                    return page
                await asyncio.sleep(1)
        raise Exception(f"Error: {self.profile_number} Страница не найдена: {url_contains}")

    async def set_proxy(self) -> None:
        """
        Устанавливает прокси для профиля в ADS
        :return:
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
            response = await self.session.post(url, json=data, headers={"Content-Type": "application/json"})
        response.raise_for_status()

    async def get_profile_id(self) -> str:
        """
        Get profile id by profile number
        :return: ads profile id
        """
        url = self.local_api_url + 'user/list'
        parameters = {"serial_number": self.profile_number}
        async with lock:
            await random_sleep(1, 2)
            response = await self.session.get(url, params=parameters)
        if response.status_code == 200:
            return response.json()['data']['list'][0]['user_id']


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
        await self.ads.page.goto(self.url, wait_until='load')
        authorized_checker = self.ads.page.get_by_test_id('home__nfts-tab')
        if await authorized_checker.count() > 0:
            logger.info(f"Авторизация в метамаске прошла успешно: {self.ads.profile_number}")
            return

        await self.ads.page.get_by_test_id('unlock-password').fill(self.password)
        await self.ads.page.get_by_test_id('unlock-submit').click()
        await self.ads.page.wait_for_load_state('load')
        await asyncio.sleep(5)
        if await self.ads.page.get_by_test_id('popover-close').count() > 0:
            await self.ads.page.get_by_test_id('popover-close').click()

        if not await authorized_checker.count() > 0:
            raise Exception(f"Error: {self.ads.profile_number} Ошибка авторизации в метамаске")

        logger.info(f"Авторизация в метамаске прошла успешно: {self.ads.profile_number}")

    async def connect(self, locator: Locator) -> None:
        """
        Подтверждает подключение метамаска к сайту во всплывающем окне метамаска.
        :param locator: локатор кнопки подключения метамаска
        :return: None
        """
        async with self.ads.context.expect_page() as page_catcher:
            await locator.click()
        metamask_page = await page_catcher.value
        await metamask_page.wait_for_load_state('load')
        await metamask_page.get_by_test_id('page-container-footer-next').click()
        await metamask_page.get_by_test_id('page-container-footer-next').click()

    async def confirm_tx(self, locator) -> None:
        """
        Подтверждает транзакцию во всплывающем окне метамаска.
        :param locator: локатор кнопки вызывающей подтверждение транзакции
        :return: None
        """
        async with self.ads.context.expect_page() as page_catcher:
            locator.click()
        metamask_page = await page_catcher.value
        await metamask_page.wait_for_load_state('load')
        await metamask_page.get_by_test_id('page-container-footer-next').click()
