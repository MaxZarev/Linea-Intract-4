from __future__ import annotations

from dataclasses import dataclass

from eth_typing import ChecksumAddress
from web3 import Web3


@dataclass
class ContractTemp:
    """
    Класс для хранения адреса контракта и его имени аби
    """
    address: ChecksumAddress | str
    abi_name: str = 'token'

    def __post_init__(self) -> None:
        if isinstance(self.address, str):
            if not 'ETH' in self.address:
                self.address = Web3.to_checksum_address(self.address)

    def __str__(self) -> ChecksumAddress:
        return self.address

    def __repr__(self) -> ChecksumAddress:
        return self.address

    def __hash__(self) -> int:
        return hash(self.address)


