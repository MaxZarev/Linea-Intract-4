from better_proxy import Proxy
from pydantic import BaseModel


class Account(BaseModel):
    """
    Модель аккаунта c параметрами для работы с ботом
    """
    profile_number: int
    private_key: str
    password: str
    proxy: Proxy
    withdraw_address: str