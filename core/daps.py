import random
from datetime import datetime, timedelta
from typing import Optional

from httpx import AsyncClient
from eth_typing import HexStr
from web3.types import TxParams
from loguru import logger

from core.onchain import Amount, Onchain, Contracts, Tokens
from models import ContractTemp, Account
from utils import random_amount, random_sleep, get_eth_price


class Daps(Onchain):
    def __init__(self, account: Account):
        super().__init__(account)
        self.eth_price = get_eth_price()

    async def get_swap_price(self, token: ContractTemp) -> Amount:
        contract_router = self.get_contract(Contracts.nile_router)
        weth_address = await contract_router.functions.weth().call()
        reserves = await contract_router.functions.getReserves(
            token.address,
            weth_address,
            False
        ).call()
        return Amount(reserves[0] / reserves[1])

    async def balance_check_and_popup(self):
        """
        Проверяет баланс эфира и выводит его если он меньше 1$
        :return:
        """
        balance_eth = await self.get_balance()
        if balance_eth.ether_float < 16 / self.eth_price:
            random_round = random.randint(5, 7)
            amount = random_amount(20 / self.eth_price, 25 / self.eth_price, round_n=random_round)
            await self.okx.okx_withdraw(self.address, 'Linea', 'ETH', amount)


class Wowmax(Daps):
    def __init__(self, account: Account):
        super().__init__(account)

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
            token_balance = await self.get_balance(from_token)
            token_price_in_eth = await self.get_swap_price(from_token)
            if token_balance.ether_float < 1 / token_price_in_eth.ether_float:
                logger.warning(f"{self.profile_number}: Баланс токена меньше 1$ - {token_balance}, пропускаем свап")
                return
            # даем апрув контракту на переданную сумму или на баланс токена
            if not amount_from:
                amount_from = token_balance
            token_contract = self.get_contract(from_token)
            await self.approve(token_contract, Contracts.wowmax_event_router, amount_from)
        else:
            await self.balance_check_and_popup()
            if not amount_from:
                amount_from = Amount(random_amount(self.eth_price / 9, self.eth_price / 10))

        # получаем путь для обмена и данные по обмену
        r = await self.get_data(from_token, to_token, amount_from)

        tx_params = TxParams(
            to=Contracts.wowmax_event_router.address,
            data=HexStr(r['data']),
        )
        value = amount_from if from_token == Tokens.ETH else Amount(0)
        tx = await self.prepare_transaction(tx_params=tx_params, value=value.wei)

        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number}: Swap {from_token} - {to_token}: {tx_receipt['transactionHash'].hex()}")
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


class Nile(Daps):
    def __init__(self, account: Account, wowmax: Wowmax):
        super().__init__(account)
        self.wowmax = wowmax

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
        lp_balance = await self.get_balance(lp_token)
        lp_price = await self.get_lp_price(token)

        # Если баланс lp токенов больше 15$ не добавляем ликвидность
        if lp_balance.ether_float > 15 / lp_price.ether_float:
            logger.warning(f"{self.profile_number}: Ликвидность уже добавлена  {lp_balance}")
            return

        # получаем баланс токена и цену токена в eth и usd
        token_balance = await self.get_balance(token)
        token_price_in_eth = await self.get_swap_price(token)
        token_price_in_usd = Amount(token_price_in_eth.ether_float / self.eth_price)

        # Если баланс токена меньше 7.5$ покупаем токен
        if token_balance.ether_float < 7.5 * token_price_in_usd.ether_float:
            # считаем сколько еще нужно токенов
            need_token = 8 * token_price_in_usd.ether_float - token_balance.ether_float
            # считаем сумму эфира на которую нужно закупить токен
            swap_amount = Amount(need_token / token_price_in_eth.ether_float)
            await self.wowmax.swap(Tokens.ETH, token, swap_amount)

        # Получаем баланс токена и делаем апрув контракту
        token_contract = self.get_contract(token)
        amount_token = Amount(await token_contract.functions.balanceOf(self.address).call(), wei=True)
        await self.approve(token_contract, Contracts.nile_router, amount_token)

        # получаем адрес WETH, получаем резервы пула и высчитываем минимальное количество ETH
        contract_router = self.get_contract(Contracts.nile_router)
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
            self.address,
            int(deadline.timestamp())
        ).build_transaction(await self.prepare_transaction(value=amount_eth.wei))
        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number} Добавление ликвидности в пул: {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def remove_liquidity(self, token: ContractTemp):
        lp_contract = self.get_contract(Tokens.get_lp_token(token))
        balance_lp = Amount(await lp_contract.functions.balanceOf(self.address).call(), wei=True)

        lp_price = await self.get_lp_price(token)
        if balance_lp.ether_float < 0.5 / lp_price.ether_float:
            logger.warning(f"{self.profile_number}: Ликвидность уже выведена {balance_lp}")
            return
        await self.approve(lp_contract, Contracts.nile_router, balance_lp)
        reserves = await lp_contract.functions.getReserves().call()
        lp_supply = await lp_contract.functions.totalSupply().call()

        token_supply, eth_supply = reserves[0], reserves[1]
        percent_lp = balance_lp.ether_float / lp_supply
        token_min_amount = int(token_supply * percent_lp * .98)
        eth_min_amount = int(eth_supply * percent_lp * .98)

        contract = self.get_contract(Contracts.nile_router)
        deadline = datetime.now() + timedelta(days=1)
        tx = await contract.functions.removeLiquidityETH(
            token.address,
            False,
            int(balance_lp.wei * 0.995),
            token_min_amount,
            eth_min_amount,
            self.address,
            int(deadline.timestamp())
        ).build_transaction(await self.prepare_transaction())
        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number}: Ликвидность выведена {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def stake(self):

        # проверяем баланс стейка, если уже есть стейк, то не делаем новый
        stake_balance = await self.get_balance(Tokens.ZERO_LP_VOTING)
        if stake_balance.wei:
            logger.warning(f"{self.profile_number}: Стейкинг уже сделан {stake_balance}")
            return

        # проверяем баланс lp токена
        lp_contract = self.get_contract(Tokens.LP_ZERO_WETH)
        lp_balance = Amount(await lp_contract.functions.balanceOf(self.address).call(), wei=True)

        # выбираем рандомную сумму для стейка, если баланс меньше суммы, то стейкаем весь баланс
        lp_amount = Amount(random_amount(0.01, 0.2))
        if lp_balance.ether_float < lp_amount.ether_float:
            random_percent = random_amount(0.98, 0.99, 3)
            lp_amount = Amount(lp_balance.wei * random_percent, wei=True)

        await self.approve(lp_contract, Contracts.nile_locker_lp, lp_amount)

        contract = self.get_contract(Contracts.nile_locker_lp)
        duration = random.choice([7776000, 15552000, 31104000])
        tx = await contract.functions.createLock(
            lp_amount.wei,
            duration,
            True
        ).build_transaction(await self.prepare_transaction())
        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number}: Застейкали {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def get_lp_price(self, token: ContractTemp) -> Amount:
        lp_contract = self.get_contract(Tokens.get_lp_token(token))
        reserves = await lp_contract.functions.getReserves().call()
        lp_supply = Amount(await lp_contract.functions.totalSupply().call(), wei=True)

        token_supply, eth_supply = reserves[0], Amount(reserves[1], wei=True)
        lp_token_price = eth_supply.ether_float * self.eth_price * 2 / lp_supply.ether_float
        return Amount(lp_token_price)


class Zeroland(Daps):
    def __init__(self, account: Account):
        super().__init__(account)

    async def supply_zerolend(self):

        zero_min_amount = Amount(random_amount(16 / self.eth_price, 17 / self.eth_price, round_n=6))

        token_contract = self.get_contract(Tokens.ZERO_ETH)
        zero_balance = Amount(await token_contract.functions.balanceOf(self.address).call(), wei=True)
        if zero_balance.ether_float > zero_min_amount.ether_float:
            logger.info(f"{self.profile_number}: Уже добавили ликивдность в Zerolend ранее")
            return

        await self.balance_check_and_popup()

        zeroland_contract = self.get_contract(Contracts.zerolend)

        tx = await zeroland_contract.functions.depositETH(
            Contracts.zerolend_pool.address,
            self.address,
            0
        ).build_transaction(await self.prepare_transaction(value=zero_min_amount.wei))

        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number}: Добавили ликвидность в Zerolend {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)

    async def withdraw_zerolend(self):
        """
        Выводит ETH из supply на Zerolend
        :return: None
        """
        token_contract = self.get_contract(Tokens.ZERO_ETH)
        value = Amount(await token_contract.functions.balanceOf(self.address).call(), wei=True)
        if value.wei < 1e9:
            logger.warning(f"{self.profile_number}: Уже вывели ликвидность из Zerolend")
            return

        await self.approve(token_contract, Contracts.zerolend, value)
        zeroland_contract = self.get_contract(Contracts.zerolend)
        tx = await zeroland_contract.functions.withdrawETH(
            Contracts.zerolend_pool.address,
            value.wei,
            self.address,
        ).build_transaction(
            await self.prepare_transaction())
        tx_receipt = await self.send_transaction(tx)
        logger.info(f"{self.profile_number}: Успешно вывели ликвидность из Zerolend {tx_receipt['transactionHash'].hex()}")
        await random_sleep(5, 10)
