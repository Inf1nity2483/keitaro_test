import pytest

from app.models import Campaign
from app.services.editor import (
    add_offer,
    apply_remote_streams,
    cancel_stream,
    push_stream,
    remove_offer,
    restore_offer,
    set_pin,
)


def _campaign(session):
    campaign = Campaign(keitaro_id=10, name="demo")
    session.add(campaign)
    session.flush()
    return campaign


def test_fetch_ignores_redirect_details_and_archives_missing_offers(session):
    campaign = _campaign(session)
    apply_remote_streams(
        session,
        campaign,
        [
            {"id": 1, "name": "Flow 1", "type": "regular", "position": 1, "offers": [], "filters": [{"name": "country"}], "action_payload": "https://google.com"},
            {"id": 2, "name": "Flow 2", "type": "default", "position": 2, "offers": [{"offer_id": 7, "share": 50, "state": "active"}, {"offer_id": 8, "share": 50, "state": "active"}]},
        ],
        {7: "One", 8: "Two"},
    )
    session.flush()
    flow1, flow2 = sorted(campaign.streams, key=lambda item: item.position)
    assert flow1.accepts_offers is False
    assert flow1.offers == []
    assert [(row.offer_id, row.share, row.status) for row in flow2.offers] == [(7, 50, "active"), (8, 50, "active")]
    assert flow2.dirty is False

    apply_remote_streams(
        session,
        campaign,
        [
            {"id": 1, "name": "Flow 1", "type": "regular", "position": 1, "offers": []},
            {"id": 2, "name": "Flow 2", "type": "default", "position": 2, "offers": [{"offer_id": 7, "share": 100, "state": "active"}]},
        ],
        {7: "One"},
    )
    session.flush()
    removed = next(row for row in flow2.offers if row.offer_id == 8)
    assert removed.status == "removed"
    assert removed.share == 0
    assert removed.published_status == "removed"
    assert flow2.dirty is False
    assert flow2.accepts_offers is True


def test_add_remove_pin_cancel_and_push(session):
    campaign = _campaign(session)
    apply_remote_streams(
        session,
        campaign,
        [{"id": 2, "name": "Flow 2", "type": "default", "position": 1, "offers": [{"offer_id": 7, "share": 100, "state": "active"}]}],
        {7: "One"},
    )
    session.flush()
    stream = campaign.streams[0]

    add_offer(stream, 8, "Two")
    session.flush()
    assert stream.dirty is True
    assert sorted(row.share for row in stream.offers if row.status == "active") == [50, 50]

    cancel_stream(session, stream)
    session.flush()
    assert [row.offer_id for row in stream.offers] == [7]
    assert stream.offers[0].share == 100
    assert stream.dirty is False


class Recorder:
    def __init__(self):
        self.payload = None

    def update_stream(self, stream_id, payload):
        self.payload = payload
        return {"id": stream_id, "offers": payload["offers"]}


def test_pin_blocks_add_when_locked_share_is_100(session):
    campaign = _campaign(session)
    apply_remote_streams(
        session,
        campaign,
        [{"id": 2, "name": "Flow 2", "type": "default", "position": 1, "offers": [{"offer_id": 7, "share": 100, "state": "active"}]}],
        {7: "One"},
    )
    session.flush()
    stream = campaign.streams[0]
    set_pin(stream.offers[0], True)
    with pytest.raises(Exception):
        add_offer(stream, 8, "Two")
    session.rollback()


def test_bring_back_keeps_pinned_weight(session):
    campaign = _campaign(session)
    apply_remote_streams(
        session,
        campaign,
        [{"id": 2, "name": "Flow 2", "type": "default", "position": 1, "offers": [
            {"offer_id": 1, "share": 25, "state": "active"},
            {"offer_id": 2, "share": 25, "state": "active"},
            {"offer_id": 3, "share": 25, "state": "active"},
            {"offer_id": 4, "share": 25, "state": "active"},
        ]}],
        {1: "A", 2: "B", 3: "C", 4: "D"},
    )
    session.flush()
    stream = campaign.streams[0]
    pinned = next(row for row in stream.offers if row.offer_id == 1)
    set_pin(pinned, True)
    removed = next(row for row in stream.offers if row.offer_id == 4)
    remove_offer(removed)
    session.flush()
    assert pinned.share == 25
    assert removed.share == 0
    assert removed.status == "removed"
    assert stream.dirty is True

    restore_offer(removed)
    session.flush()
    assert pinned.share == 25
    free = sorted(row.share for row in stream.offers if row.status == "active" and not row.pinned)
    assert free == [25, 25, 25]
    assert sum(row.share for row in stream.offers if row.status == "active") == 100

    client = Recorder()
    push_stream(client, stream)
    session.flush()
    assert stream.dirty is False
    assert client.payload["offers"] == [
        {"offer_id": row.offer_id, "share": row.share, "state": "active"}
        for row in stream.offers
        if row.status == "active"
    ]


def test_remove_then_push_archives_locally(session):
    campaign = _campaign(session)
    apply_remote_streams(
        session,
        campaign,
        [{"id": 2, "name": "Flow 2", "type": "default", "position": 1, "offers": [
            {"offer_id": 7, "share": 50, "state": "active"},
            {"offer_id": 8, "share": 50, "state": "active"},
        ]}],
        {7: "One", 8: "Two"},
    )
    session.flush()
    stream = campaign.streams[0]
    second = next(row for row in stream.offers if row.offer_id == 8)
    remove_offer(second)
    client = Recorder()
    push_stream(client, stream)
    assert [item["offer_id"] for item in client.payload["offers"]] == [7]
    assert second.status == "removed"
    assert second.published_status == "removed"
    assert stream.dirty is False
