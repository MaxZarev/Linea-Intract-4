from loguru import logger

from core.onchain import Amount, Tokens, Contracts, Onchain
from utils import random_amount, random_sleep


class Zeroland(Onchain):
    def __init__(self, private_key: str):
        super().__init__(private_key)
        self.eth_price = 0

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


