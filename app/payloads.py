"""Keitaro payloads for the reference campaign shape."""

GOOGLE_URL = "https://google.com"


def campaign_payload(
    *,
    name: str,
    alias: str,
    domain_id: int,
    group_id: int,
    source_id: int,
) -> dict:
    return {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        "cost_auto": True,
        "group_id": group_id,
        "traffic_source_id": source_id,
        "domain_id": domain_id,
    }


def google_stream_payload(*, campaign_id: int, geos: list[str]) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Flow 1",
        "position": 1,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": GOOGLE_URL,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [{"name": "country", "mode": "accept", "payload": geos}],
        "offers": [],
        "landings": [],
    }


def offer_stream_payload(*, campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "default",
        "name": "Flow 2",
        "position": 2,
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "action_payload": "",
        "collect_clicks": True,
        "filter_or": False,
        "filters": [],
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        "landings": [],
    }


def offers_update_payload(offers: list) -> dict:
    active = [offer for offer in offers if offer.status == "active"]
    return {
        "schema": "landings",
        "offers": [
            {"offer_id": offer.offer_id, "share": offer.share, "state": "active"}
            for offer in active
        ]
    }
