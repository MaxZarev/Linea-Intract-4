import asyncio
from typing import Literal

import ccxt.async_support as ccxt
from loguru import logger

from loader import config
from models import Account


class OKX:
    def __init__(self, account: Account):
        self.profile_number = account.profile_number
        self.exchange = ccxt.okx({
            "apiKey": config.okx.get("okx_api_key"),
            "secret": config.okx.get("okx_secret_key"),
            "password": config.okx.get("okx_passphrase"),
            "options": {
                "defaultType": "future"
            }
        })

    async def okx_withdraw(
            self,
            address: str,
            chain: Literal["ERC20", "Linea"],
            token: str,
            amount: float
    ) -> None:
        """
        Вывод средств с биржи OKX
        :param address:  Адрес кошелька
        :param chain: сеть
        :param token: токен
        :param amount: сумма
        :return: None
        """
        token_with_chain = token + "-" + chain
        fee = await self._get_withdrawal_fee(token, token_with_chain)
        try:
            response = await self.exchange.withdraw(
                code=token,
                amount=amount,
                address=address,
                params={
                    "toAddress": address,
                    "chainName": token_with_chain,
                    "dest": 4,
                    "fee": fee,
                    "pwd": '-',
                    "amt": amount,
                    "network": chain
                }
            )
            tx_id = response.get("id")
            logger.info(f'{self.profile_number}: Выводим с okx {amount} {token}')
            await self.wait_confirm(tx_id)
            logger.info(f'{self.profile_number}: Успешно выведено {amount} {token}')
            await self.exchange.close()
        except Exception as error:
            await self.exchange.close()
            logger.error(f'{self.profile_number}: Не удалось вывести {amount} {token}: {error} ')
            raise error

    async def _get_withdrawal_fee(self, token: str, token_with_chain: str):
        """
        Получение комиссии за вывод
        :param token: название токена
        :param token_with_chain: айди токен-сеть
        :return:
        """
        currencies = await self.exchange.fetch_currencies()
        for currency in currencies:
            if currency == token:
                currency_info = currencies[currency]
                network_info = currency_info.get('networks', None)
                if network_info:
                    for network in network_info:
                        network_data = network_info[network]
                        network_id = network_data['id']
                        if network_id == token_with_chain:
                            withdrawal_fee = currency_info['networks'][network]['fee']
                            if withdrawal_fee == 0:
                                return 0
                            else:
                                return withdrawal_fee
        logger.error(f" не могу получить сумму комиссии, проверьте значения symbolWithdraw и network")
        return 0

    async def wait_confirm(self, tx_id: str) -> None:
        """
        Ожидание подтверждения транзакции вывода с OKX
        :param tx_id: id транзакции вывода
        :return: None
        """
        for _ in range(30):
            tx_info = await self.exchange.fetch_withdrawal(tx_id)
            if tx_info.get("status") == "ok":
                logger.debug(f"{self.profile_number}: Транзакция {tx_id} завершена")
                return
            await asyncio.sleep(10)
        logger.error(f"{self.profile_number}: Ошибка транзакция {tx_id} не завершена")
        raise Exception(f"{self.profile_number} Транзакция {tx_id} не завершена")
