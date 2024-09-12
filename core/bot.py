import asyncio
import random
from typing import Optional

from eth_typing import HexStr
from loguru import logger
from web3.types import TxParams
from httpx import AsyncClient
from datetime import datetime, timedelta

from core.ads import Ads
from core.onchain import Onchain, Amount, Tokens, Contracts
from core.okx import OKX
from core.wowmax import Wowmax

from models import Account, ContractTemp
from database import Accounts

from utils import random_amount, random_sleep


class Bot:

    def __init__(self, account: Account):
        self.ads: Ads = Ads(account)
        self.okx = OKX()
        self.onchain = Onchain(account.private_key)
        self.wowmax = Wowmax(account.private_key)
        self.eth_price = 2300

    async def run(self) -> None:

        await Accounts.create_account(self.ads.profile_number, self.onchain.address)
        self.eth_price = await self.get_eth_price()

        # 2 квест
        if not await Accounts.get_status(self.ads.profile_number, 2):
            await self.supply_zerolend()
            await self.interact_quest(2, 'Supply any asset on Linea on Zerolend')
        await self.withdraw_zerolend()

        # 1 квест
        if not await Accounts.get_status(self.ads.profile_number, 1):
            await self.add_liquidity_eth(Tokens.ZERO)
            await self.interact_quest(1, 'Provide liquidity to Zero/ETH on Nile')

        await self.remove_liquidity(Tokens.ZERO)
        await self.swap(Tokens.ZERO, Tokens.ETH)

        # 4 квест
        if not await Accounts.get_status(self.ads.profile_number, 4):
            await self.stake()
            await self.interact_quest(4, 'Stake Zero/ETH on Zerolend.')

        # 3 квест
        if not await Accounts.get_status(self.ads.profile_number, 3):
            await self.add_liquidity_eth(Tokens.NILE)
            await self.interact_quest(3, 'Provide liquidity to Nile/ETH on Nile')
        await self.remove_liquidity(Tokens.NILE)
        await self.swap(Tokens.NILE, Tokens.ETH)
        logger.info(f"{self.ads.profile_number}: All quests are completed")

    async def open_interact(self):
        try:
            await self.ads.page.goto('https://www.intract.io/quest/66bb5618c8ff56cba848ea8f')
        except Exception:
            await self.open_interact()

        if await self.ads.page.get_by_text('Sign In').count() > 0:
            await self.ads.page.get_by_text('Sign In').click()
            await self.ads.metamask.connect(self.ads.page.locator('//div[text()="MetaMask"]'))
            await asyncio.sleep(5)
            signature_page = await self.ads.catch_page('signature-request')
            await signature_page.wait_for_load_state('load')
            await signature_page.get_by_test_id('page-container-footer-next').click()
            await self.ads.page.wait_for_load_state('load')

    async def supply_zerolend(self):

        zero_min_amount = Amount(random_amount(16 / self.eth_price, 17 / self.eth_price, round_n=6))

        token_contract = self.onchain.get_contract(Tokens.ZERO_ETH)
        zero_balance = Amount(await token_contract.functions.balanceOf(self.onchain.address).call(), wei=True)
        if zero_balance.ether_float > zero_min_amount.ether_float:
            logger.info(f"{self.ads.profile_number}: Supply eth zerolend complete")
            return

        balance_eth = await self.onchain.get_balance()
        if balance_eth.ether_float < zero_min_amount.ether_float * 1.1:
            amount = Amount(zero_min_amount.ether_float * 1.1)
            await self.okx.okx_withdraw(self.onchain.address, 'Linea', 'ETH', amount)

        zeroland_contract = self.onchain.get_contract(Contracts.zerolend)

        tx = await zeroland_contract.functions.depositETH(
            Contracts.zerolend_pool.address,
            self.onchain.address,
            0
        ).build_transaction(await self.onchain.prepare_transaction(value=zero_min_amount.wei))

        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"{self.ads.profile_number}: Supply eth zerolend {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def withdraw_zerolend(self):
        """
        Выводит ETH из supply на Zerolend
        :return: None
        """
        token_contract = self.onchain.get_contract(Tokens.ZERO_ETH)
        value = Amount(await token_contract.functions.balanceOf(self.onchain.address).call(), wei=True)
        if value.wei < 1e9:
            logger.warning(f"{self.ads.profile_number} Balance is too low {value} for withdraw")
            return

        await self.onchain.approve(token_contract, Contracts.zerolend, value)
        zeroland_contract = self.onchain.get_contract(Contracts.zerolend)
        tx = await zeroland_contract.functions.withdrawETH(
            Contracts.zerolend_pool.address,
            value.wei,
            self.onchain.address,
        ).build_transaction(
            await self.onchain.prepare_transaction())
        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"{self.ads.profile_number}: Withdraw eth zerolend {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def interact_quest(self, quest: int, quest_text: str) -> bool:
        """
        Прокликивает задание на Zerolend
        :return:
        """

        if await Accounts.get_status(self.ads.profile_number, quest):
            return True

        if not self.ads.browser:
            await self.ads.run()
            await self.ads.metamask.authorize()

        await self.open_interact()

        quest_block = self.ads.page.locator('//div[contains(@class, "task_trigger_container")]',
                                            has_text=quest_text)

        if await quest_block.get_by_alt_text('check task logo badge').is_visible():
            await Accounts.change_status(self.ads.profile_number, quest)
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
        await self.interact_quest(quest, quest_text)

    async def swap(self, from_token: ContractTemp, to_token: ContractTemp,
                   amount_from: Optional[Amount] = None) -> None:
        """
        Свапает токены на Wowmax
        :param from_token: продаваемый токен
        :param to_token: покупаемый токен
        :param amount_from: сумму обмена
        :return: None
        """

        # если меняем токен на эфир
        if from_token != Tokens.ETH:
            # проверяем что баланс токена больше 1$
            token_balance = await self.onchain.get_balance(from_token)
            token_price_in_eth = await self.get_swap_price(from_token)
            if token_balance.ether_float < 1 / token_price_in_eth.ether_float:
                logger.warning(f"Balance is too low {token_balance}")
                return
            # даем апрув контракту на переданную сумму или на баланс токена
            if not amount_from:
                amount_from = token_balance
            token_contract = self.onchain.get_contract(from_token)
            await self.onchain.approve(token_contract, Contracts.wowmax_event_router, amount_from)
        else:
            if not amount_from:
                amount_from = Amount(random_amount(self.eth_price / 9, self.eth_price / 10))

        # получаем путь для обмена и данные по обмену
        r = await self.get_data(from_token, to_token, amount_from)

        tx_params = TxParams(
            to=Contracts.wowmax_event_router.address,
            data=HexStr(r['data']),
        )
        value = amount_from if from_token == Tokens.ETH else Amount(0)
        tx = await self.onchain.prepare_transaction(tx_params=tx_params, value=value.wei)

        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"Swap: {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    @staticmethod
    async def get_data(from_token: ContractTemp, to_token: ContractTemp, amount: Amount) -> dict:
        """
        Получает данные по API для транзакции
        :param from_token: покупаемый токен
        :param to_token: продаваемый токен
        :param amount: сумма обмена
        :return: данные по обмену
        """
        async with AsyncClient() as session:
            uri = 'https://api-gateway.wowmax.exchange/chains/59144/swap'
            params = {
                'from': from_token,
                'to': to_token,
                'amount': amount,
                'slippage': 5
            }
            response = await session.get(uri, params=params)
        return response.json()

    async def add_liquidity_eth(self, token: ContractTemp):
        """
        Добавление ликвидности в пул в пару, переданный токен + ETH на Wowmax,
        берет количество переданного токена, делает апрув контракту,
        считает минимальное количество ETH, которое должно быть передано в пул
        :param token: Токен для добавления ликвидности с ETH
        :return: None
        """

        # получаем баланс и цену lp токена
        lp_token = Tokens.get_lp_token(token)
        lp_balance = await self.onchain.get_balance(lp_token)
        lp_price = await self.get_lp_price(token)

        # Если баланс lp токенов больше 15$ не добавляем ликвидность
        if lp_balance.ether_float > 15 / lp_price.ether_float:
            logger.warning(f"LP balance is not empty {lp_balance}")
            return

        # получаем баланс токена и цену токена в eth и usd
        token_balance = await self.onchain.get_balance(token)
        token_price_in_eth = await self.get_swap_price(token)
        token_price_in_usd = Amount(token_price_in_eth.ether_float / self.eth_price)

        # Если баланс токена меньше 7.5$ покупаем токен
        if token_balance.ether_float < 7.5 * token_price_in_usd.ether_float:
            # считаем сколько еще нужно токенов
            need_token = 8 * token_price_in_usd.ether_float - token_balance.ether_float
            # считаем сумму эфира на которую нужно закупить токен
            swap_amount = Amount(need_token / token_price_in_eth.ether_float)
            await self.swap(Tokens.ETH, token, swap_amount)

        # Получаем баланс токена и делаем апрув контракту
        token_contract = self.onchain.get_contract(token)
        amount_token = Amount(await token_contract.functions.balanceOf(self.onchain.address).call(), wei=True)
        await self.onchain.approve(token_contract, Contracts.nile_router, amount_token)

        # получаем адрес WETH, получаем резервы пула и высчитываем минимальное количество ETH
        contract_router = self.onchain.get_contract(Contracts.nile_router)
        weth_address = await contract_router.functions.weth().call()
        reserves = await contract_router.functions.getReserves(
            token.address,
            weth_address,
            False
        ).call()
        amount_eth = Amount(amount_token.wei * reserves[1] / reserves[0], wei=True)

        # упаковываем параметры и отправляем транзакцию
        deadline = datetime.now() + timedelta(days=1)
        tx = await contract_router.functions.addLiquidityETH(
            token.address,
            False,
            amount_token.wei,
            int(amount_token.wei * 0.98),
            int(amount_eth.wei * 0.98),
            self.onchain.address,
            int(deadline.timestamp())
        ).build_transaction(await self.onchain.prepare_transaction(value=amount_eth.wei))
        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"Add liquidity: {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def remove_liquidity(self, token: ContractTemp):
        lp_contract = self.onchain.get_contract(Tokens.get_lp_token(token))
        balance_lp = Amount(await lp_contract.functions.balanceOf(self.onchain.address).call(), wei=True)

        lp_price = await self.get_lp_price(token)
        if balance_lp.ether_float < 0.5 / lp_price.ether_float:
            logger.warning(f"Balance LP is too low {balance_lp}")
            return
        await self.onchain.approve(lp_contract, Contracts.nile_router, balance_lp)
        reserves = await lp_contract.functions.getReserves().call()
        lp_supply = await lp_contract.functions.totalSupply().call()

        token_supply, eth_supply = reserves[0], reserves[1]
        percent_lp = balance_lp.ether_float / lp_supply
        token_min_amount = int(token_supply * percent_lp * .98)
        eth_min_amount = int(eth_supply * percent_lp * .98)

        contract = self.onchain.get_contract(Contracts.nile_router)
        deadline = datetime.now() + timedelta(days=1)
        tx = await contract.functions.removeLiquidityETH(
            token.address,
            False,
            int(balance_lp.wei * 0.995),
            token_min_amount,
            eth_min_amount,
            self.onchain.address,
            int(deadline.timestamp())
        ).build_transaction(await self.onchain.prepare_transaction())
        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"Remove liquidity: {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def stake(self):

        stake_balance = await self.onchain.get_balance(Tokens.ZERO_LP_VOTING)
        if stake_balance.wei:
            logger.warning(f"Stake balance is not empty {stake_balance}")
            return

        lp_contract = self.onchain.get_contract(Tokens.LP_ZERO_WETH)

        lp_amount = Amount(random_amount(0.01, 0.2))

        await self.onchain.approve(lp_contract, Contracts.nile_locker_lp, lp_amount)

        contract = self.onchain.get_contract(Contracts.nile_locker_lp)
        duration = random.choice([7776000, 15552000, 31104000])
        tx = await contract.functions.createLock(
            lp_amount.wei,
            duration,
            True
        ).build_transaction(await self.onchain.prepare_transaction())
        tx_receipt = await self.onchain.send_transaction(tx)
        logger.info(f"Stake: {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    @staticmethod
    async def get_eth_price() -> float:
        for _ in range(3):
            try:
                async with AsyncClient() as session:
                    uri = 'https://api-gateway.wowmax.exchange/prices'
                    response = await session.get(uri)
                    response.raise_for_status()
                for token in response.json():
                    if token['symbol'] == 'ETH':
                        return token['price']
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(5)
        logger.error(f"Can't get eth price")
        return 2300

    async def get_swap_price(self, token: ContractTemp) -> Amount:
        contract_router = self.onchain.get_contract(Contracts.nile_router)
        weth_address = await contract_router.functions.weth().call()
        reserves = await contract_router.functions.getReserves(
            token.address,
            weth_address,
            False
        ).call()

        return Amount(reserves[0] / reserves[1])

    async def get_lp_price(self, token: ContractTemp) -> Amount:
        lp_contract = self.onchain.get_contract(Tokens.get_lp_token(token))
        reserves = await lp_contract.functions.getReserves().call()
        lp_supply = Amount(await lp_contract.functions.totalSupply().call(), wei=True)

        token_supply, eth_supply = reserves[0], Amount(reserves[1], wei=True)
        lp_token_price = eth_supply.ether_float* self.eth_price * 2 / lp_supply.ether_float
        return Amount(lp_token_price)
