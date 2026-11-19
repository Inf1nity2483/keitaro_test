import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.keitaro import KeitaroClient
from app.services.campaigns import (
    create_campaign,
    ensure_offer_stream,
    get_local_campaign,
    list_campaigns,
    offer_or_404,
    open_campaign,
    stream_or_404,
)
from app.services.editor import add_offer, cancel_stream, push_stream, remove_offer, restore_offer, set_pin
from app.services.serialize import campaign_out, editor_out

router = APIRouter(prefix="/api")
_offers_cache: dict[str, object] = {"at": 0.0, "rows": []}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(min_length=2, max_length=200)
    offer_id: int


class OfferIn(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_client(settings: Settings = Depends(get_settings)) -> KeitaroClient:
    return KeitaroClient(settings)


def get_db(request: Request):
    session: Session = request.app.state.session_factory()
    try:
        if not inspect(session.get_bind()).has_table("campaigns"):
            raise AppError("База не создана. В корне проекта выполни alembic upgrade head", 503)
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/meta")
def meta(settings: Settings = Depends(get_settings)):
    prefix_ready = settings.campaign_prefix.startswith("test_") and settings.campaign_prefix not in {
        "test_",
        "test_фамилия_",
    }
    return {
        "tracker": settings.keitaro_base_url,
        "key_set": bool(settings.keitaro_api_key),
        "prefix": settings.campaign_prefix,
        "prefix_ready": prefix_ready,
        "group_name": settings.keitaro_group_name,
        "source_name": settings.keitaro_source_name,
    }


@router.get("/offers")
def search_offers(q: str = "", client: KeitaroClient = Depends(get_client)):
    rows = _cached_offers(client)
    needle = q.strip().casefold()
    found = []
    for offer in rows:
        if offer.get("state") == "deleted":
            continue
        offer_id = offer.get("id")
        if offer_id is None:
            continue
        name = str(offer.get("name") or "")
        if needle and needle not in name.casefold() and needle not in str(offer_id):
            continue
        found.append({"id": int(offer_id), "name": name})
        if len(found) >= 20:
            break
    return found


@router.get("/campaigns")
def campaigns(session: Session = Depends(get_db)):
    return [campaign_out(campaign) for campaign in list_campaigns(session)]


@router.post("/campaigns")
def create(
    body: CampaignIn,
    session: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
):
    campaign = create_campaign(
        session,
        client,
        settings,
        name=body.name,
        geo=body.geo,
        offer_id=body.offer_id,
    )
    return editor_out(campaign)


@router.get("/campaigns/{keitaro_id}")
def read_campaign(keitaro_id: int, session: Session = Depends(get_db)):
    return editor_out(get_local_campaign(session, keitaro_id))


@router.post("/campaigns/{keitaro_id}/fetch")
def fetch_campaign(keitaro_id: int, session: Session = Depends(get_db), client: KeitaroClient = Depends(get_client)):
    return editor_out(open_campaign(session, client, keitaro_id))


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/offers")
def create_offer(
    keitaro_id: int,
    stream_id: int,
    body: OfferIn,
    session: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_client),
):
    campaign = get_local_campaign(session, keitaro_id)
    stream = stream_or_404(campaign, stream_id)
    ensure_offer_stream(stream)
    remote = client.get_offer(body.offer_id)
    add_offer(stream, body.offer_id, remote.get("name") or f"Offer {body.offer_id}")
    session.commit()
    return editor_out(campaign)


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/offers/{row_id}/remove")
def delete_offer(keitaro_id: int, stream_id: int, row_id: int, session: Session = Depends(get_db)):
    campaign = get_local_campaign(session, keitaro_id)
    row = offer_or_404(stream_or_404(campaign, stream_id), row_id)
    remove_offer(row)
    session.commit()
    return editor_out(campaign)


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/offers/{row_id}/restore")
def bring_back(keitaro_id: int, stream_id: int, row_id: int, session: Session = Depends(get_db)):
    campaign = get_local_campaign(session, keitaro_id)
    row = offer_or_404(stream_or_404(campaign, stream_id), row_id)
    restore_offer(row)
    session.commit()
    return editor_out(campaign)


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/offers/{row_id}/pin")
def pin_offer(
    keitaro_id: int,
    stream_id: int,
    row_id: int,
    body: PinIn,
    session: Session = Depends(get_db),
):
    campaign = get_local_campaign(session, keitaro_id)
    row = offer_or_404(stream_or_404(campaign, stream_id), row_id)
    set_pin(row, body.pinned)
    session.commit()
    return editor_out(campaign)


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/push")
def push(keitaro_id: int, stream_id: int, session: Session = Depends(get_db), client: KeitaroClient = Depends(get_client)):
    campaign = get_local_campaign(session, keitaro_id)
    stream = stream_or_404(campaign, stream_id)
    push_stream(client, stream)
    session.commit()
    return editor_out(campaign)


@router.post("/campaigns/{keitaro_id}/streams/{stream_id}/cancel")
def cancel(keitaro_id: int, stream_id: int, session: Session = Depends(get_db)):
    campaign = get_local_campaign(session, keitaro_id)
    stream = stream_or_404(campaign, stream_id)
    cancel_stream(session, stream)
    session.commit()
    return editor_out(campaign)


def _cached_offers(client: KeitaroClient) -> list[dict]:
    now = time.time()
    cached_at = float(_offers_cache["at"])
    rows = _offers_cache["rows"]
    if isinstance(rows, list) and rows and now - cached_at < 60:
        return rows
    fresh = client.get_offers()
    _offers_cache["at"] = now
    _offers_cache["rows"] = fresh
    return fresh
