from app.config import Settings
from app.services.campaigns import create_campaign


class FakeKeitaro:
    def __init__(self):
        self.campaign = None
        self.streams = []

    def get_offer(self, offer_id):
        return {"id": offer_id, "name": "Mia", "state": "active"}

    def get_domains(self):
        return [
            {"id": 1, "name": "tlgk.host", "state": "active", "admin_dashboard": True, "is_ssl": True},
            {
                "id": 2,
                "name": "track.example",
                "state": "active",
                "admin_dashboard": False,
                "is_ssl": True,
                "group": "FORTESTS",
            },
        ]

    def get_groups(self, group_type):
        return [{"id": 4, "name": "FORTESTS", "type": group_type}]

    def get_sources(self):
        return [{"id": 9, "name": "FORTESTS"}]

    def create_campaign(self, payload):
        self.campaign = payload
        return {"id": 55, "alias": "abc123", "name": payload["name"]}

    def create_stream(self, payload):
        self.streams.append(payload)
        return {"id": 100 + len(self.streams), **payload}

    def get_streams(self, campaign_id):
        return [
            {"id": 101, "name": "Flow 1", "type": "regular", "position": 1, "offers": []},
            {
                "id": 102,
                "name": "Flow 2",
                "type": "default",
                "position": 2,
                "offers": [{"offer_id": 15, "share": 100, "state": "active"}],
            },
        ]

    def delete_campaign(self, campaign_id):
        self.deleted = campaign_id


def test_create_matches_reference_campaign(session):
    fake = FakeKeitaro()
    settings = Settings(
        keitaro_base_url="https://tlgk.host",
        keitaro_api_key="test-key",
        campaign_prefix="test_ivanov_",
        keitaro_group_name="FORTESTS",
        keitaro_source_name="FORTESTS",
        database_url="sqlite://",
    )
    campaign = create_campaign(session, fake, settings, name="campaign1", geo="MX, AU", offer_id=15)

    assert campaign.name == "test_ivanov_campaign1"
    assert campaign.keitaro_id == 55
    assert campaign.domain == "track.example"
    alias = fake.campaign.pop("alias")
    assert len(alias) == 8 and alias.isalnum()
    assert fake.campaign == {
        "name": "test_ivanov_campaign1",
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        "cost_auto": True,
        "group_id": 4,
        "traffic_source_id": 9,
        "domain_id": 2,
    }
    assert fake.streams[0]["type"] == "regular"
    assert fake.streams[0]["schema"] == "redirect"
    assert fake.streams[0]["action_payload"] == "https://google.com"
    assert fake.streams[0]["filters"] == [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}]
    assert fake.streams[1]["type"] == "default"
    assert fake.streams[1]["schema"] == "landings"
    assert fake.streams[1]["offers"] == [{"offer_id": 15, "share": 100, "state": "active"}]
    assert [stream.name for stream in campaign.streams] == ["Flow 1", "Flow 2"]
    assert campaign.streams[0].accepts_offers is False
    assert [(row.offer_id, row.share) for row in campaign.streams[1].offers] == [(15, 100)]
