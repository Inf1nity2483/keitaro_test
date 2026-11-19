from app.services.campaigns import campaign_url
from app.models import Campaign


def campaign_out(campaign: Campaign) -> dict:
    offers_total = sum(len(stream.offers) for stream in campaign.streams)
    return {
        "keitaro_id": campaign.keitaro_id,
        "name": campaign.name,
        "alias": campaign.alias,
        "domain": campaign.domain,
        "group_name": campaign.group_name,
        "source_name": campaign.source_name,
        "url": campaign_url(campaign),
        "streams": len(campaign.streams),
        "offers": offers_total,
    }


def editor_out(campaign: Campaign) -> dict:
    return {
        "campaign": campaign_out(campaign),
        "streams": [_stream_out(stream) for stream in sorted(campaign.streams, key=lambda item: item.position)],
    }


def _stream_out(stream) -> dict:
    offers = sorted(stream.offers, key=lambda item: (item.status != "active", item.position, item.offer_id))
    return {
        "id": stream.id,
        "keitaro_id": stream.keitaro_id,
        "name": stream.name,
        "stream_type": stream.stream_type,
        "accepts_offers": stream.accepts_offers,
        "dirty": stream.dirty,
        "offers": [
            {
                "id": offer.id,
                "offer_id": offer.offer_id,
                "name": offer.name,
                "share": offer.share,
                "pinned": offer.pinned,
                "status": offer.status,
            }
            for offer in offers
        ],
    }
