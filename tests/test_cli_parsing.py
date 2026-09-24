import pytest

from redcom_calc.cli.app import parse_block_tag
from redcom_calc.domain.models import BlockType


@pytest.mark.parametrize(
    "raw,name,block",
    [
        ("Интернет", "Интернет", BlockType.NONE),
        ("ЦТВ", "ЦТВ", BlockType.NONE),
        ("Интернет КТВ", "Интернет КТВ", BlockType.NONE),
        ("Интернет ФБ", "Интернет", BlockType.FINANCIAL),
        ("Интернет фб", "Интернет", BlockType.FINANCIAL),
        ("Интернет Фб", "Интернет", BlockType.FINANCIAL),
        ("Интернет FB", "Интернет", BlockType.FINANCIAL),
        ("Интернет fb", "Интернет", BlockType.FINANCIAL),
        ("Интернет ДБ", "Интернет", BlockType.VOLUNTARY),
        ("Интернет дб", "Интернет", BlockType.VOLUNTARY),
        ("Интернет DB", "Интернет", BlockType.VOLUNTARY),
        ("Порт ДБ", "Порт", BlockType.VOLUNTARY),
        ("Порт   ДБ", "Порт", BlockType.VOLUNTARY),
        ("  ЦТВ  ФБ  ", "ЦТВ", BlockType.FINANCIAL),
        ("ФБ", "без названия", BlockType.FINANCIAL),
        ("ДБ", "без названия", BlockType.VOLUNTARY),
        ("", "без названия", BlockType.NONE),
        ("   ", "без названия", BlockType.NONE),
    ],
)
def test_parse_block_tag(raw, name, block):
    assert parse_block_tag(raw) == (name, block)
