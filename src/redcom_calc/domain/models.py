from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ServiceType(str, Enum):
    INTERNET = "internet"
    CTV = "ctv"
    KTV = "ktv"
    INTERCOM = "intercom"
    PHONE = "phone"
    CAMERA = "camera"
    EQUIPMENT = "equipment"


class ServiceState(str, Enum):
    SERVICE = "service"
    ATTACH = "attach"
    BLOCK = "block"
    CANCEL = "cancel"


class BlockType(str, Enum):
    NONE = "none"
    VOLUNTARY = "voluntary"   # ДБ
    FINANCIAL = "financial"   # ФБ


@dataclass(frozen=True)
class Service:
    type: ServiceType
    monthly_fee: Decimal
    state: ServiceState
    block_type: BlockType = BlockType.NONE
    name: str = ""

    def __post_init__(self) -> None:
        if self.monthly_fee < 0:
            raise ValueError("monthly_fee must be >= 0")
        if self.state is ServiceState.BLOCK and self.block_type is BlockType.NONE:
            raise ValueError("BLOCK requires non-NONE block_type")
        if self.state is not ServiceState.BLOCK and self.block_type is not BlockType.NONE:
            raise ValueError("non-BLOCK requires NONE block_type")
