from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError, KeitaroError, WeightError
from app.keitaro import KeitaroClient
from app.models import Campaign, Stream, StreamOffer
from app.naming import make_alias, parse_geos, with_prefix
from app.payloads import campaign_payload, google_stream_payload, offer_stream_payload
from app.services.editor import apply_remote_streams, load_offer_names


def create_campaign(
    session: Session,
    client: KeitaroClient,
    settings: Settings,
    *,
    name: str,
    geo: str,
    offer_id: int,
) -> Campaign:
    final_name = _name(name, settings.campaign_prefix)
    geos = _geos(geo)
    offer = client.get_offer(offer_id)
    if offer.get("state") == "deleted":
        raise AppError(f"Оффер {offer_id} архивный")
    domain = _pick_domain(client.get_domains(), settings)
    group = _pick_named(client.get_groups("campaigns"), settings.keitaro_group_name, "группы кампаний")
    source = _pick_named(client.get_sources(), settings.keitaro_source_name, "источника")

    created = client.create_campaign(
        campaign_payload(
            name=final_name,
            alias=make_alias(),
            domain_id=int(domain["id"]),
            group_id=int(group["id"]),
            source_id=int(source["id"]),
        )
    )
    campaign_id = int(created["id"])
    try:
        client.create_stream(google_stream_payload(campaign_id=campaign_id, geos=geos))
        client.create_stream(offer_stream_payload(campaign_id=campaign_id, offer_id=offer_id))
        remote_streams = client.get_streams(campaign_id)
    except Exception:
        try:
            client.delete_campaign(campaign_id)
        except KeitaroError:
            pass
        raise

    campaign = Campaign(
        keitaro_id=campaign_id,
        name=created.get("name") or final_name,
        alias=created.get("alias") or "",
        domain=str(domain.get("name") or ""),
        group_name=str(group.get("name") or ""),
        source_name=str(source.get("name") or ""),
    )
    session.add(campaign)
    names = load_offer_names(client, _offer_ids(remote_streams), {offer_id: offer.get("name") or f"Offer {offer_id}"})
    apply_remote_streams(session, campaign, remote_streams, names)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise AppError(
            f"Кампания уже создана в Keitaro, id={campaign_id}, но локально не сохранилась.",
            500,
        ) from exc
    return campaign


def open_campaign(session: Session, client: KeitaroClient, keitaro_id: int) -> Campaign:
    remote = client.get_campaign(keitaro_id)
    campaign = session.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
    if campaign is None:
        campaign = Campaign(keitaro_id=keitaro_id, name=remote.get("name") or f"campaign {keitaro_id}")
        session.add(campaign)
    campaign.name = remote.get("name") or campaign.name
    campaign.alias = remote.get("alias") or campaign.alias
    _fill_relations(campaign, client, remote)
    remote_streams = client.get_streams(keitaro_id)
    names = load_offer_names(client, _offer_ids(remote_streams), {})
    apply_remote_streams(session, campaign, remote_streams, names)
    session.commit()
    return campaign


def list_campaigns(session: Session) -> list[Campaign]:
    return list(session.scalars(select(Campaign).order_by(Campaign.id.desc())))


def get_local_campaign(session: Session, keitaro_id: int) -> Campaign:
    campaign = session.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_id))
    if campaign is None:
        raise AppError("Кампания ещё не открыта. Нажми Fetch streams.", 404)
    return campaign


def campaign_url(campaign: Campaign) -> str:
    if not campaign.domain or not campaign.alias:
        return ""
    host = campaign.domain
    if not host.startswith("http"):
        host = "https://" + host
    return f"{host.rstrip('/')}/{campaign.alias}"


def _name(name: str, prefix: str) -> str:
    try:
        return with_prefix(name, prefix)
    except ValueError as exc:
        raise AppError(str(exc)) from exc


def _geos(raw: str) -> list[str]:
    try:
        return parse_geos(raw)
    except ValueError as exc:
        raise AppError(str(exc)) from exc


def _pick_named(items: list[dict], expected: str, label: str) -> dict:
    for item in items:
        if str(item.get("name", "")).strip().casefold() == expected.casefold():
            return item
    found = ", ".join(sorted({str(item.get("name")) for item in items if item.get("name")})[:20])
    found = found or "список пуст"
    raise AppError(f"Не нашёл {label} «{expected}». В трекере есть: {found}")


def _pick_domain(domains: list[dict], settings: Settings) -> dict:
    if settings.keitaro_domain_id is not None:
        for domain in domains:
            if int(domain["id"]) == settings.keitaro_domain_id:
                return domain
        raise AppError(f"Домен id={settings.keitaro_domain_id} в трекере не найден")

    usable = [domain for domain in domains if domain.get("state") not in ("disabled", "deleted")]
    if not usable:
        raise AppError("В трекере нет активного домена")
    public = [domain for domain in usable if not domain.get("admin_dashboard")]
    pool = public or usable
    grouped = [
        domain
        for domain in pool
        if str(domain.get("group") or "").strip().casefold() == settings.keitaro_group_name.casefold()
    ]
    if grouped:
        pool = grouped
    secure = [domain for domain in pool if domain.get("is_ssl")]
    return (secure or pool)[0]


def _fill_relations(campaign: Campaign, client: KeitaroClient, remote: dict) -> None:
    domain_id = remote.get("domain_id")
    if domain_id:
        for domain in client.get_domains():
            if int(domain["id"]) == int(domain_id):
                campaign.domain = str(domain.get("name") or campaign.domain)
                break
    group_id = remote.get("group_id")
    if group_id:
        for group in client.get_groups("campaigns"):
            if int(group["id"]) == int(group_id):
                campaign.group_name = str(group.get("name") or campaign.group_name)
                break
    source_id = remote.get("traffic_source_id")
    if source_id:
        for source in client.get_sources():
            if int(source["id"]) == int(source_id):
                campaign.source_name = str(source.get("name") or campaign.source_name)
                break


def _offer_ids(streams: list[dict]) -> set[int]:
    found: set[int] = set()
    for stream in streams:
        for offer in stream.get("offers") or []:
            if offer.get("offer_id"):
                found.add(int(offer["offer_id"]))
    return found


def stream_or_404(campaign: Campaign, stream_id: int) -> Stream:
    for stream in campaign.streams:
        if stream.id == stream_id:
            return stream
    raise AppError("Поток не найден", 404)


def offer_or_404(stream: Stream, row_id: int) -> StreamOffer:
    for offer in stream.offers:
        if offer.id == row_id:
            return offer
    raise AppError("Оффер в потоке не найден", 404)


def ensure_offer_stream(stream: Stream) -> None:
    if not stream.accepts_offers:
        raise WeightError("В этот поток офферы не добавляются")
