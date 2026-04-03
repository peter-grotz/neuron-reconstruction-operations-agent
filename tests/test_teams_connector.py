from exaspim_agent.config import TeamsChannelConfig
from exaspim_agent.connectors.teams import TeamsConnector


class FakeTeamsConnector(TeamsConnector):
    def __init__(self) -> None:
        super().__init__(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            channels=[
                TeamsChannelConfig(
                    key="ops_updates",
                    team_name="Ops Team",
                    channel_name="Announcements",
                    include_replies=True,
                )
            ],
        )
        self._payloads = {
            "teams": {
                "value": [{"id": "team-1", "displayName": "Ops Team"}],
            },
            "teams/team-1/channels": {
                "value": [{"id": "channel-1", "displayName": "Announcements"}],
            },
            "teams/team-1/channels/channel-1/messages?$top=100": {
                "value": [
                    {
                        "id": "message-1",
                        "createdDateTime": "2026-04-03T12:00:00Z",
                        "subject": "Pipeline update",
                        "body": {"content": "<div>Imaging completed for sample 822175</div>"},
                        "from": {"user": {"displayName": "Researcher A"}},
                    }
                ]
            },
            "teams/team-1/channels/channel-1/messages/message-1/replies": {
                "value": [
                    {
                        "id": "reply-1",
                        "createdDateTime": "2026-04-03T12:05:00Z",
                        "body": {"content": "<p>Queued for registration next.</p>"},
                        "from": {"user": {"displayName": "Researcher B"}},
                    }
                ]
            },
        }

    def _get_access_token(self) -> str:
        return "fake-token"

    def _graph_request_json(self, path: str) -> dict:
        return self._payloads[path]


def test_teams_connector_fetches_messages_and_replies() -> None:
    connector = FakeTeamsConnector()

    records = connector.fetch()

    assert len(records) == 2
    message = records[0]
    reply = records[1]
    assert message.source_kind.value == "teams"
    assert message.metadata["team_name"] == "Ops Team"
    assert message.metadata["channel_name"] == "Announcements"
    assert message.metadata["author"] == "Researcher A"
    assert "Imaging completed for sample 822175" in message.body
    assert reply.metadata["is_reply"] is True
    assert reply.metadata["parent_message_id"] == "message-1"


def test_teams_connector_resolves_team_and_channel_by_name() -> None:
    connector = FakeTeamsConnector()

    teams = connector._list_teams()
    team = connector._resolve_team(connector.channels[0], teams)
    channel = connector._resolve_channel(connector.channels[0], team, connector._list_channels("team-1"))

    assert team["id"] == "team-1"
    assert channel["id"] == "channel-1"
