from decimal import Decimal

import pytest

from redcom_calc.domain.models import BlockType, Service, ServiceState, ServiceType
from redcom_calc.domain.rules import monthly_rate_for_state


def _svc(type_, state, fee="500", block=BlockType.NONE):
    return Service(
        type=type_,
        monthly_fee=Decimal(fee),
        state=state,
        block_type=block,
    )


@pytest.mark.parametrize(
    "type_,state,block,expected",
    [
        (ServiceType.INTERNET, ServiceState.SERVICE, BlockType.NONE, "500"),
        (ServiceType.INTERNET, ServiceState.BLOCK, BlockType.VOLUNTARY, "50"),
        (ServiceType.INTERNET, ServiceState.BLOCK, BlockType.FINANCIAL, "150"),
        (ServiceType.KTV, ServiceState.SERVICE, BlockType.NONE, "150"),
        (ServiceType.KTV, ServiceState.BLOCK, BlockType.VOLUNTARY, "150"),
        (ServiceType.KTV, ServiceState.BLOCK, BlockType.FINANCIAL, "150"),
        (ServiceType.CTV, ServiceState.BLOCK, BlockType.VOLUNTARY, "0"),
        (ServiceType.CTV, ServiceState.BLOCK, BlockType.FINANCIAL, "0"),
        (ServiceType.INTERCOM, ServiceState.BLOCK, BlockType.VOLUNTARY, "100"),
        (ServiceType.PHONE, ServiceState.BLOCK, BlockType.FINANCIAL, "180"),
        (ServiceType.CAMERA, ServiceState.BLOCK, BlockType.VOLUNTARY, "800"),
        (ServiceType.EQUIPMENT, ServiceState.BLOCK, BlockType.FINANCIAL, "300"),
        (ServiceType.INTERNET, ServiceState.ATTACH, BlockType.NONE, "0"),
        (ServiceType.INTERNET, ServiceState.CANCEL, BlockType.NONE, "0"),
    ],
)
def test_monthly_rate_for_state(type_, state, block, expected):
    fee = {
        ServiceType.CAMERA: "800",
        ServiceType.EQUIPMENT: "300",
    }.get(type_, "500")
    svc = _svc(type_, state, fee=fee, block=block)
    assert monthly_rate_for_state(svc) == Decimal(expected)


def test_block_requires_block_type():
    with pytest.raises(ValueError):
        Service(
            type=ServiceType.INTERNET,
            monthly_fee=Decimal("500"),
            state=ServiceState.BLOCK,
            block_type=BlockType.NONE,
        )


def test_non_block_requires_none_block_type():
    with pytest.raises(ValueError):
        Service(
            type=ServiceType.INTERNET,
            monthly_fee=Decimal("500"),
            state=ServiceState.SERVICE,
            block_type=BlockType.VOLUNTARY,
        )


def test_negative_fee_rejected():
    with pytest.raises(ValueError):
        Service(
            type=ServiceType.INTERNET,
            monthly_fee=Decimal("-1"),
            state=ServiceState.SERVICE,
        )
