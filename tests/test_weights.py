from types import SimpleNamespace

import pytest

from app.errors import WeightError
from app.weights import rebalance


def offer(offer_id, share=0, pinned=False, pinned_share=None, status="active"):
    return SimpleNamespace(
        id=offer_id,
        offer_id=offer_id,
        share=share,
        pinned=pinned,
        pinned_share=pinned_share,
        status=status,
    )


def shares(offers):
    return [(item.offer_id, item.share, item.status) for item in offers]


def test_equal_splits_use_whole_percents():
    one = [offer(1)]
    rebalance(one)
    assert shares(one) == [(1, 100, "active")]

    two = [offer(1), offer(2)]
    rebalance(two)
    assert shares(two) == [(1, 50, "active"), (2, 50, "active")]

    three = [offer(1), offer(2), offer(3)]
    rebalance(three)
    assert shares(three) == [(1, 34, "active"), (2, 33, "active"), (3, 33, "active")]
    assert sum(item.share for item in three) == 100


def test_pinned_share_stays_and_the_rest_splits_the_remainder():
    rows = [offer(1, share=25, pinned=True, pinned_share=25), offer(2), offer(3)]
    rebalance(rows)
    assert shares(rows) == [(1, 25, "active"), (2, 38, "active"), (3, 37, "active")]


def test_removed_offer_gets_zero_and_drops_out_of_the_split():
    rows = [offer(1), offer(2), offer(3, status="removed", share=40)]
    rebalance(rows)
    assert shares(rows) == [(1, 50, "active"), (2, 50, "active"), (3, 0, "removed")]


def test_pin_that_fills_100_percent_blocks_a_new_offer():
    rows = [offer(1, share=100, pinned=True, pinned_share=100), offer(2)]
    with pytest.raises(WeightError):
        rebalance(rows)


def test_pinned_offers_must_cover_100_when_nothing_else_is_left():
    rows = [offer(1, share=25, pinned=True, pinned_share=25), offer(2, share=25, pinned=True, pinned_share=25)]
    with pytest.raises(WeightError):
        rebalance(rows)
