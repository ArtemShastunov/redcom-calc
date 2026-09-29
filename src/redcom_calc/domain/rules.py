from __future__ import annotations

from decimal import Decimal

from .models import BlockType, Service, ServiceState, ServiceType

# КТВ: 50 ₽ без блока, 150 ₽ в блоке (ДБ или ФБ)
KTV_MONTHLY_RATE = Decimal(50)
KTV_BLOCK_RATE = Decimal(150)

BLOCK_RATES: dict[ServiceType, dict[BlockType, Decimal]] = {
    ServiceType.INTERNET: {
        BlockType.VOLUNTARY: Decimal(50),
        BlockType.FINANCIAL: Decimal(150),
    },
    ServiceType.KTV: {
        BlockType.VOLUNTARY: KTV_BLOCK_RATE,
        BlockType.FINANCIAL: KTV_BLOCK_RATE,
    },
    ServiceType.CTV: {
        BlockType.VOLUNTARY: Decimal(0),
        BlockType.FINANCIAL: Decimal(0),
    },
    ServiceType.INTERCOM: {
        BlockType.VOLUNTARY: Decimal(100),
        BlockType.FINANCIAL: Decimal(100),
    },
    ServiceType.PHONE: {
        BlockType.VOLUNTARY: Decimal(180),
        BlockType.FINANCIAL: Decimal(180),
    },
}

_TYPES_WITH_TARIFF_IN_BLOCK = frozenset(
    {
        ServiceType.EQUIPMENT,
        ServiceType.CAMERA,
    }
)


def monthly_rate_for_state(service: Service) -> Decimal:
    """Месячная ставка услуги в её текущем состоянии (ТЗ §3.1–3.2)."""
    if service.state in (ServiceState.ATTACH, ServiceState.CANCEL):
        return Decimal(0)
    if service.state is ServiceState.SERVICE:
        if service.type is ServiceType.KTV:
            return KTV_MONTHLY_RATE
        return service.monthly_fee
    # BLOCK
    if service.type in _TYPES_WITH_TARIFF_IN_BLOCK:
        return service.monthly_fee
    return BLOCK_RATES[service.type][service.block_type]


def monthly_rate_if_service(service: Service) -> Decimal:
    """Ставка, как если бы услуга была в SERVICE (для подписи «полный тариф»)."""
    if service.type is ServiceType.KTV:
        return KTV_MONTHLY_RATE
    return service.monthly_fee
