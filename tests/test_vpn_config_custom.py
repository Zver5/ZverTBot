import pytest

from handlers.admin.vpn_config import parse_custom_parameters
from services.vpn_server_setup import (
    AWG_DEFAULT_PARAMS,
    AWG_DEFAULT_PORT,
    XRAY_DEFAULT_DEST,
    XRAY_DEFAULT_PORT,
    XRAY_DEFAULT_SNI,
)


def test_xray_custom_parser_uses_defaults():
    result = parse_custom_parameters("xray", "")
    assert result == {
        "port": XRAY_DEFAULT_PORT,
        "sni": XRAY_DEFAULT_SNI,
        "dest": XRAY_DEFAULT_DEST,
        "flow": "xtls-rprx-vision",
    }


def test_xray_custom_parser_accepts_custom_values():
    result = parse_custom_parameters(
        "xray",
        "port=8443\nsni=example.com\ndest=example.com:443\nflow=none",
    )
    assert result == {
        "port": 8443,
        "sni": "example.com",
        "dest": "example.com:443",
        "flow": "",
    }


def test_xray_flow_accepts_vision_alias():
    result = parse_custom_parameters("xray", "flow=vision")
    assert result["flow"] == "xtls-rprx-vision"


def test_xray_empty_value_keeps_default():
    result = parse_custom_parameters("xray", "port=")
    assert result["port"] == XRAY_DEFAULT_PORT


def test_awg_custom_parser_uses_defaults():
    result = parse_custom_parameters("awg", "")
    assert result == {"port": AWG_DEFAULT_PORT, **AWG_DEFAULT_PARAMS}


def test_awg_custom_parser_accepts_custom_values():
    result = parse_custom_parameters(
        "awg",
        "port=51820\njc=5\njmin=30\njmax=80\ns1=101\nh4=14",
    )
    assert result["port"] == 51820
    assert result["jc"] == 5
    assert result["jmin"] == 30
    assert result["jmax"] == 80
    assert result["s1"] == 101
    assert result["h4"] == 14
    assert result["s2"] == AWG_DEFAULT_PARAMS["s2"]


@pytest.mark.parametrize(
    "raw",
    [
        "port=0",
        "port=65536",
        "port=abc",
        "flow=invalid",
        "dest=invalid",
        "unknown=1",
        "port=8443\nport=8444",
    ],
)
def test_xray_parser_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        parse_custom_parameters("xray", raw)


@pytest.mark.parametrize(
    "raw",
    [
        "port=0",
        "jc=-1",
        "jmin=90\njmax=20",
        "s1=abc",
        "unknown=1",
    ],
)
def test_awg_parser_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        parse_custom_parameters("awg", raw)


def test_parser_rejects_unknown_protocol():
    with pytest.raises(ValueError):
        parse_custom_parameters("unknown", "")
