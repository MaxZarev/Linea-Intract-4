import datetime
import random

from loguru import logger

from core.onchain import Amount, Tokens, Contracts, Onchain
from models import ContractTemp
from utils import random_amount, random_sleep


class Nile(Onchain):
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

