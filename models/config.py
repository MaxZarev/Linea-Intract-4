from pydantic import BaseModel

from models import Account


class Config(BaseModel):
    accounts: list[Account]
    threads: int
    okx: dict[str, str]
    rpc_linea: str
    metamask_url: str
    gas_multiple: list[float, float]
    zerolend_supply: list[float, float]
    eth_price: float = 0.0
    use_proxy: bool
    is_mobile_proxy: bool
    link_change_ip: str