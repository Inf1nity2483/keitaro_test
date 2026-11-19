from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app


def test_home_and_meta_report_missing_setup(tmp_path):
    settings = Settings(
        keitaro_base_url="https://tlgk.host",
        keitaro_api_key="",
        campaign_prefix="test_фамилия_",
        database_url="sqlite:///" + (tmp_path / "app.db").as_posix(),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)

    page = client.get("/")
    assert page.status_code == 200
    assert "Новая кампания" in page.text
    assert "Fetch streams" in page.text

    meta = client.get("/api/meta").json()
    assert meta["key_set"] is False
    assert meta["prefix_ready"] is False
    assert client.get("/api/campaigns").json() == []
