import asyncio
from typing import Literal

from loguru import logger
from okx import Funding

from loader import config
from models import Account


class OKX:
    def __init__(self, account: Account):
        self.profile_number = account.profile_number

        self.funding_api = Funding.FundingAPI(
            config.okx.get("okx_api_key"),
            config.okx.get("okx_secret_key"),
            config.okx.get("okx_passphrase"),
            flag="0",
            debug=False
        )

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
            logger.info(f'{self.profile_number}: Выводим с okx {amount} {token}')
            response = self.funding_api.withdrawal(
                ccy=token,
                amt=amount,
                dest=4,
                toAddr=address,
                fee=fee,
                chain=token_with_chain,
            )
            if response.get("code") != "0":
                raise Exception(f'{self.profile_number}: Не удалось вывести {amount} {token}: {response.get("msg")}')
            tx_id = response.get("data")[0].get("wdId")
            await self.wait_confirm(tx_id)
            logger.info(f'{self.profile_number}: Успешно выведено {amount} {token}')
        except Exception as error:
            logger.error(f'{self.profile_number}: Не удалось вывести {amount} {token}: {error} ')
            raise error

    async def _get_withdrawal_fee(self, token: str, token_with_chain: str):
        """
        Получение комиссии за вывод
        :param token: название токена
        :param token_with_chain: айди токен-сеть
        :return:
        """
        response = self.funding_api.get_currencies(token)
        for network in response.get("data"):
            if network.get("chain") == token_with_chain:
                return network.get("minFee")

        logger.error(f" не могу получить сумму комиссии, проверьте значения symbolWithdraw и network")
        return 0

    async def wait_confirm(self, tx_id: str) -> None:
        """
        Ожидание подтверждения транзакции вывода с OKX
        :param tx_id: id транзакции вывода
        :return: None
        """
        for _ in range(30):
            tx_info = self.funding_api.get_deposit_withdraw_status(wdId=tx_id)
            if tx_info.get("code") == "0":
                if 'Withdrawal complete' in tx_info.get("data")[0].get("state"):
                    logger.debug(f"{self.profile_number}: Транзакция {tx_id} завершена")
                    return
            await asyncio.sleep(10)
        logger.error(f"{self.profile_number}: Ошибка транзакция {tx_id} не завершена")
        raise Exception(f"{self.profile_number} Транзакция {tx_id} не завершена")
