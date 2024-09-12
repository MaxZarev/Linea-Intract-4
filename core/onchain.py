from __future__ import annotations

import json
import os
import random
from decimal import Decimal
from typing import Optional

from web3 import AsyncWeb3
from web3.contract import AsyncContract
from web3.eth import AsyncEth
from web3.types import TxParams, TxReceipt, Wei

from core.okx import OKX
from loader import config
from models import ContractTemp, Account


class Onchain:
    def __init__(self, account: Account):
        self.profile_number = account.profile_number
        self.private_key = account.private_key
        self.w3: AsyncWeb3 = AsyncWeb3(
            provider=AsyncWeb3.AsyncHTTPProvider(
                endpoint_uri=config.rpc_linea,
            ),
            modules={'eth': (AsyncEth,)},
        )
        self.address = self.w3.eth.account.from_key(account.private_key).address
        self.okx = OKX(account)

    async def get_balance(self, token: Optional[ContractTemp] = None) -> Amount:
        if not token:
            amount_wei = await self.w3.eth.get_balance(self.address)
        else:
            contract = self.get_contract(token)
            amount_wei = await contract.functions.balanceOf(self.address).call()
        return Amount(amount_wei, wei=True)

    def get_contract(self, contract: ContractTemp, abi_name: Optional[str] = None) -> AsyncContract:
        """
        Получает контракт по адресу и аби в заливистости от класса
        :return: инициализированный контракт
        """

        abi = self.get_abi(abi_name or contract.abi_name)
        initialized_contract = self.w3.eth.contract(address=contract.address, abi=abi)
        return initialized_contract

    @staticmethod
    def get_abi(file_name: str) -> str:
        """
        Читает json файл в папке data
        :return: словарь с abi
        """
        with open(os.path.join("config", 'data', "ABIs", f"{file_name}.json")) as f:
            return json.loads(f.read())

    async def prepare_transaction(self, *, value: int | Wei = 0,
                                  tx_params: Optional[TxParams] = None) -> TxParams:
        """
        Подготавливает параметры транзакции, от кого, кому, чейн-ади и параметры газа
        :param tx_params:
        :param value: сумма транзакции, если отправляется ETH или нужно платить, сумма в wei
        :return: словарь с параметрами транзакции
        """
        if not tx_params:
            tx_params = TxParams()

        tx_params['from'] = self.address
        tx_params['nonce'] = await self.w3.eth.get_transaction_count(self.address)
        tx_params['chainId'] = await self.w3.eth.chain_id

        if value:
            tx_params['value'] = value

        base_fee = 7

        max_priority_fee_per_gas = await self.get_priority_fee()

        max_fee_per_gas = base_fee + max_priority_fee_per_gas

        tx_params['maxPriorityFeePerGas'] = max_priority_fee_per_gas
        tx_params['maxFeePerGas'] = int(max_fee_per_gas * random.uniform(*config.gas_multiple))
        tx_params['type'] = '0x2'
        return tx_params

    async def get_priority_fee(self) -> int:
        """
        Получает среднюю цену за приоритетную транзакцию за последние 25 блоков
        :return: средняя цена за приоритетную транзакцию
        """
        fee_history = await self.w3.eth.fee_history(25, 'latest', [20.0])
        non_empty_block_priority_fees = [fee[0] for fee in fee_history["reward"] if fee[0] != 0]
        divisor_priority = max(len(non_empty_block_priority_fees), 1)
        priority_fee = int(round(sum(non_empty_block_priority_fees) / divisor_priority))

        return priority_fee

    async def send_transaction(self, tx: TxParams, gas: int = 0) -> TxReceipt:
        """
        Подписывает транзакцию приватным ключем и отправляет в сеть
        :param tx: параметры транзакции
        :param gas: лимит газа, если не указывать считается автоматически
        :return: хэш транзакции
        """
        if gas:
            tx['gas'] = gas
        else:
            tx['gas'] = int((await self.w3.eth.estimate_gas(tx)) * random.uniform(*config.gas_multiple))

        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)

        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return await self.w3.eth.wait_for_transaction_receipt(tx_hash)

    async def approve(self, contract: AsyncContract, spender: ContractTemp, value: Amount) -> TxReceipt:
        """
        Отправляет транзакцию на approve
        :param contract: контракт токена
        :param spender: адрес, которому разрешается снимать токены
        :param value: сумма токенов
        :return: хэш транзакции
        """
        allowance_amount = await contract.functions.allowance(self.address, spender.address).call()
        if allowance_amount < value.wei:
            tx = await contract.functions.approve(spender.address, value.wei).build_transaction(
                await self.prepare_transaction())
            return await self.send_transaction(tx)


class Amount:
    wei: Wei | int
    ether: Decimal
    ether_float: float
    decimals: int

    def __init__(self, amount: int | float | str | Decimal, decimals: int = 18, wei: bool = False) -> None:

        if wei:
            self.wei = int(amount)
            self.ether = Decimal(str(amount)) / 10 ** decimals
            self.ether_float = float(self.ether)
        else:
            self.wei = int(amount * 10 ** decimals)
            self.ether = Decimal(str(amount))
            self.ether_float = float(amount)

        self.decimals = decimals

    def __str__(self) -> str:
        return str(self.ether)

    def __repr__(self) -> str:
        return f"Amount(ether={self.ether_float}, wei={self.wei}, decimals={self.decimals})"






class Contracts:
    wowmax_event_router = ContractTemp('0x9773e6C011e6CF919904b2F99DDc66e616611269')
    nile_router = ContractTemp('0xaaa45c8f5ef92a000a121d102f4e89278a711faa', 'nile_router')
    nile_pair = ContractTemp('0x0040F36784dDA0821E74BA67f86E084D70d67a3A', 'nile_pair')
    nile_locker_lp = ContractTemp('0x8bb8b092f3f872a887f377f73719c665dd20ab06', 'nile_locker_lp')
    zerolend = ContractTemp('0x5d50bE703836C330Fc2d147a631CDd7bb8D7171c', 'zerolend')
    zerolend_pool = ContractTemp('0x2f9bB73a8e98793e26Cb2F6C4ad037BDf1C6B269')


class Tokens:
    ETH = ContractTemp('ETH')
    WETH = ContractTemp('0x0000000000000000000000000000000000000000')
    ZERO = ContractTemp('0x78354f8DcCB269a615A7e0a24f9B0718FDC3C7A7')
    NILE = ContractTemp('0xAAAac83751090C6ea42379626435f805DDF54DC8')
    LP_ZERO_WETH = ContractTemp('0x0040F36784dDA0821E74BA67f86E084D70d67a3A', 'nile_pair')
    LP_NILE_WETH = ContractTemp('0xFC6A4cd4007C3d24D37114d81A801a56F9536625', 'nile_pair')
    ZERO_ETH = ContractTemp('0xb4ffef15daf4c02787bc5332580b838ce39805f5')
    ZERO_LP_VOTING = ContractTemp('0x0374ae8e866723ADAE4A62DcE376129F292369b4')

    @classmethod
    def get_lp_token(cls, token: ContractTemp) -> ContractTemp:
        token_name = cls.get_token_name(token)
        lp_token = getattr(cls, f'LP_{token_name}_WETH')
        return lp_token

    @classmethod
    def get_token_name(cls, token: ContractTemp) -> str:
        """
        Возвращает имя токена по его объекту
        :param token:
        :return:
        """
        for name, value in cls.__dict__.items():
            if isinstance(value, ContractTemp) and value == token:
                return name
