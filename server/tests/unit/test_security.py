from uuid import uuid4

import pytest

from app.core.security import create_access_token, decode_access_token, hash_wechat_openid


def test_access_token_round_trip() -> None:
    player_id = uuid4()
    token = create_access_token(player_id, "a" * 40, 3600)
    assert decode_access_token(token, "a" * 40) == player_id


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(uuid4(), "a" * 40, -1)
    with pytest.raises(ValueError, match="Invalid or expired"):
        decode_access_token(token, "a" * 40)


def test_openid_is_pseudonymized_deterministically() -> None:
    secret = "b" * 40
    digest = hash_wechat_openid("wechat-openid", secret)
    assert len(digest) == 64
    assert digest == hash_wechat_openid("wechat-openid", secret)
    assert digest != "wechat-openid"
