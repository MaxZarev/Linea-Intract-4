from pydantic import BaseModel

from models import Account


class Config(BaseModel):
    """
    Конфигурация бота c валидацией
    """
    accounts: list[Account]
    threads: int
    is_withdraw_to_wallet: bool
    okx: dict[str, str]
    rpc_linea: str
    metamask_url: str
    gas_multiple: list[float, float]
    gas_limit_multiple: list[float, float]
    shuffle_profiles: bool
    eth_price: float = 0.0
    use_proxy: bool
    is_mobile_proxy: bool
    link_change_ip: str
    is_withdraw_to_cex: bool
    min_balance: list[float, float]
    tg_token: str
    tg_chat_id: str
