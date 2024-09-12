import asyncio
from typing import Optional

from eth_typing import HexStr
from loguru import logger
from web3.types import TxParams
from httpx import AsyncClient

from core.onchain import Amount, Tokens, Contracts, Onchain
from models import ContractTemp
from utils import random_amount, random_sleep


class Wowmax(Onchain):
    def __init__(self, private_key: str):
        super().__init__(private_key)
        self.onchain = Onchain(private_key)
        self.eth_price = 0

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
