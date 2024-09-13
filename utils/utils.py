from __future__ import annotations

import asyncio
import os
from random import uniform

import yaml
from better_proxy import Proxy
from httpx import Client
from loguru import logger

from models import Account, Config

CONFIG_PATH = os.path.join(os.getcwd(), 'config')
CONFIG_DATA_PATH = os.path.join(CONFIG_PATH, "data")
CONFIG_PARAMS = os.path.join(CONFIG_PATH, "settings.yaml")

def read_file(
        file_path: str,
        check_empty: bool = True,
        is_yaml: bool = False,
        convert_to_int: bool = False,
) -> list[str] | list[int] | dict:
    if not os.path.exists(file_path):
        logger.error(f"Файл не найден: {file_path}")
        exit(1)

    if check_empty and os.stat(file_path).st_size == 0:
        logger.error(f"Файл пустой: {file_path}")
        exit(1)

    if is_yaml:
        with open(file_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return data

    with open(file_path, "r", encoding="utf-8") as file:
        data = file.readlines()

    if convert_to_int:
        return [int(line.strip()) for line in data]

    return [line.strip() for line in data]


def get_accounts() -> list[Account]:
    """
    Достает из файлов wallets.txt и proxies.txt данные и создает список аккаунтов
    :return: список аккаунтов
    """
    profiles = read_file(os.path.join(CONFIG_DATA_PATH, "profiles.txt"), convert_to_int=True)
    private_keys = read_file(os.path.join(CONFIG_DATA_PATH, "private_keys.txt"))
    passwords = read_file(os.path.join(CONFIG_DATA_PATH, "passwords.txt"))
    proxies = read_file(os.path.join(CONFIG_DATA_PATH, "proxies.txt"), check_empty=False)
    withdraw_addresses = read_file(os.path.join(CONFIG_DATA_PATH, "withdraw_addresses.txt"), check_empty=False)

    if not proxies:
        proxies = ['1.1.1.1:1111'] * len(profiles)

    if not withdraw_addresses:
        proxies = ['0x'] * len(profiles)

    if len(profiles) != len(private_keys) != len(proxies) != len(passwords) != len(withdraw_addresses):
        raise ValueError("Количество аккаунтов, прокси, приватных ключей, паролей и адресов вывода должно быть одинаковым")

    accounts = []
    for profile_number, private_key, password, proxy_str, withdraw_address in zip(profiles, private_keys, passwords, proxies, withdraw_addresses):
        proxy = Proxy.from_str(proxy_str)
        accounts.append(Account(
            profile_number=profile_number,
            private_key=private_key,
            password=password,
            proxy=proxy,
            withdraw_address=withdraw_address,
        ))
    return accounts


def load_config() -> Config:
    """
    Загружает конфигурацию из файла settings.yaml, создает список аккаунтов и возвращает объект Config
    :return: объект Config
    """
    settings = read_file(CONFIG_PARAMS, is_yaml=True)
    accounts = get_accounts()
    config = Config(accounts=accounts, **settings)
    return config


def random_amount(min_n: float, max_n: float, round_n: int = 4) -> float:
    return round(uniform(min_n, max_n), round_n)


async def random_sleep(min_n: float, max_n: float):
    sleep_time = random_amount(min_n, max_n)
    await asyncio.sleep(sleep_time)


def get_eth_price() -> float:
    for _ in range(3):
        try:
            with Client() as session:
                uri = 'https://api-gateway.wowmax.exchange/prices'
                response = session.get(uri)
                response.raise_for_status()
            for token in response.json():
                if token['symbol'] == 'ETH':
                    return token['price']
            asyncio.sleep(5)
        except Exception:
            asyncio.sleep(5)
    logger.error(f"Не можем получить цену ETH, ставим 2300")
    return 2300
