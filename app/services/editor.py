from app.errors import AppError
from app.keitaro import KeitaroClient
from app.models import Campaign, Stream, StreamOffer
from app.weights import rebalance


def apply_remote_streams(session, campaign: Campaign, remote_streams: list[dict], names: dict[int, str]) -> None:
    ordered = sorted(remote_streams, key=lambda item: item.get("position") or 0)
    by_keitaro_id = {stream.keitaro_id: stream for stream in campaign.streams}
    seen: set[int] = set()

    for index, remote in enumerate(ordered):
        keitaro_id = int(remote["id"])
        seen.add(keitaro_id)
        local = by_keitaro_id.get(keitaro_id)
        if local is None:
            local = Stream(
                campaign=campaign,
                keitaro_id=keitaro_id,
                name=remote.get("name") or f"Flow {index + 1}",
                stream_type=remote.get("type") or "regular",
                position=remote.get("position") if remote.get("position") is not None else index,
            )
            session.add(local)
        local.name = remote.get("name") or local.name
        local.stream_type = remote.get("type") or local.stream_type
        local.position = remote.get("position") if remote.get("position") is not None else index
        remote_offers = _active_remote_offers(remote)
        if remote_offers or local.offers:
            local.accepts_offers = True
            _sync_offers(local, remote_offers, names)
        else:
            local.accepts_offers = False

    for local in list(campaign.streams):
        if local.keitaro_id not in seen:
            session.delete(local)


def load_offer_names(client: KeitaroClient, offer_ids: set[int], known: dict[int, str]) -> dict[int, str]:
    names = dict(known)
    missing = [offer_id for offer_id in offer_ids if offer_id not in names]
    if not missing:
        return names
    if len(missing) > 3:
        for offer in client.get_offers():
            names[int(offer["id"])] = offer.get("name") or f"Offer {offer['id']}"
        return names
    for offer_id in missing:
        try:
            offer = client.get_offer(offer_id)
            names[offer_id] = offer.get("name") or f"Offer {offer_id}"
        except AppError:
            names[offer_id] = f"Offer {offer_id}"
    return names


def add_offer(stream: Stream, offer_id: int, name: str) -> None:
    if not stream.accepts_offers:
        raise AppError("В этот поток офферы не добавляются")
    existing = _find(stream, offer_id)
    if existing and existing.status == "active":
        raise AppError("Этот оффер уже есть в потоке")
    if existing:
        existing.status = "active"
        existing.name = name or existing.name
    else:
        stream.offers.append(
            StreamOffer(
                offer_id=offer_id,
                name=name or f"Offer {offer_id}",
                status="active",
                share=0,
                pinned=False,
                position=len(stream.offers),
            )
        )
    rebalance(stream.offers)


def remove_offer(row: StreamOffer) -> None:
    if row.status == "removed":
        return
    row.status = "removed"
    rebalance(row.stream.offers)


def restore_offer(row: StreamOffer) -> None:
    if row.status == "active":
        return
    row.status = "active"
    rebalance(row.stream.offers)


def set_pin(row: StreamOffer, pinned: bool) -> None:
    if row.status != "active":
        raise AppError("Сначала верни оффер в поток, потом пинь долю")
    row.pinned = pinned
    row.pinned_share = row.share if pinned else None
    rebalance(row.stream.offers)


def cancel_stream(session, stream: Stream) -> None:
    for row in list(stream.offers):
        if row.published_status is None:
            stream.offers.remove(row)
            session.delete(row)
        else:
            row.restore_published()


def push_stream(client: KeitaroClient, stream: Stream) -> None:
    from app.payloads import offers_update_payload

    if not stream.accepts_offers:
        raise AppError("У этого потока нет офферов, публиковать нечего")
    active = [offer for offer in stream.offers if offer.status == "active"]
    total = sum(offer.share for offer in active)
    if active and total != 100:
        raise AppError(f"Доли активных офферов дают {total}%, а нужно 100")
    payload = offers_update_payload(stream.offers)
    updated = client.update_stream(stream.keitaro_id, payload)
    if "offers" in updated:
        returned = {
            int(item["offer_id"]): int(item.get("share") or 0)
            for item in updated.get("offers") or []
            if item.get("state") != "disabled" and item.get("offer_id")
        }
        expected = {offer.offer_id: offer.share for offer in active}
        if returned != expected:
            raise AppError(
                "Keitaro принял запрос, но доли в ответе не совпали с отправленными. "
                "Нажми Fetch streams и проверь поток."
            )
    for row in stream.offers:
        row.mark_published()


def _sync_offers(stream: Stream, remote_offers: list[dict], names: dict[int, str]) -> None:
    by_offer_id = {row.offer_id: row for row in stream.offers}
    seen: set[int] = set()
    for index, remote in enumerate(remote_offers):
        offer_id = int(remote["offer_id"])
        seen.add(offer_id)
        share = int(remote.get("share") or 0)
        row = by_offer_id.get(offer_id)
        if row is None:
            stream.offers.append(
                StreamOffer(
                    offer_id=offer_id,
                    name=names.get(offer_id) or f"Offer {offer_id}",
                    share=share,
                    pinned=False,
                    status="active",
                    position=index,
                    published_status="active",
                    published_share=share,
                )
            )
            continue
        row.name = names.get(offer_id) or row.name
        row.position = index
        row.status = "active"
        row.share = share
        if row.pinned:
            row.pinned_share = share
        row.published_status = "active"
        row.published_share = share
        row.published_pinned = row.pinned
        row.published_pinned_share = row.pinned_share

    for row in stream.offers:
        if row.offer_id in seen:
            continue
        row.status = "removed"
        row.share = 0
        row.position = 1000 + row.offer_id
        row.published_status = "removed"
        row.published_share = 0
        row.published_pinned = row.pinned
        row.published_pinned_share = row.pinned_share


def _active_remote_offers(remote: dict) -> list[dict]:
    return [
        offer
        for offer in remote.get("offers") or []
        if offer.get("offer_id") and offer.get("state") != "disabled"
    ]


def _find(stream: Stream, offer_id: int) -> StreamOffer | None:
    for row in stream.offers:
        if row.offer_id == offer_id:
            return row
    return None
