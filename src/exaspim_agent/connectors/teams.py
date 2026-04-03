from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from exaspim_agent.config import TeamsChannelConfig
from exaspim_agent.connectors.base import DataConnector
from exaspim_agent.domain.models import SourceKind, SourceRecord


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(part.strip() for part in self.parts if part.strip())


class TeamsConnector(DataConnector):
    name = "teams"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        channels: list[TeamsChannelConfig],
        graph_base_url: str = "https://graph.microsoft.com/v1.0",
        authority_url: str = "https://login.microsoftonline.com",
        scope: str = "https://graph.microsoft.com/.default",
        max_messages_per_channel: int = 100,
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.channels = channels
        self.graph_base_url = graph_base_url.rstrip("/")
        self.authority_url = authority_url.rstrip("/")
        self.scope = scope
        self.max_messages_per_channel = max_messages_per_channel
        self._access_token: Optional[str] = None

    def fetch(self) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        teams_cache: Optional[list[dict[str, Any]]] = None
        channels_cache: dict[str, list[dict[str, Any]]] = {}

        for target in self.channels:
            if teams_cache is None:
                teams_cache = self._list_teams()
            team = self._resolve_team(target, teams_cache)
            team_id = str(team["id"])
            if team_id not in channels_cache:
                channels_cache[team_id] = self._list_channels(team_id)
            channel = self._resolve_channel(target, team, channels_cache[team_id])
            messages = self._list_messages(team_id, str(channel["id"]), include_replies=target.include_replies)
            records.extend(self._messages_to_records(target, team, channel, messages))

        return records

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "mode": "read_only",
            "channel_count": str(len(self.channels)),
            "purpose": "Read selected Microsoft Teams channel messages through Microsoft Graph.",
        }

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        token_url = "{authority}/{tenant}/oauth2/v2.0/token".format(
            authority=self.authority_url,
            tenant=self.tenant_id,
        )
        body = urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = Request(
            token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        payload = self._request_json(request, use_bearer=False)
        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("Microsoft Graph token response did not include an access_token.")
        self._access_token = str(access_token)
        return self._access_token

    def _graph_request_json(self, path: str) -> dict[str, Any]:
        url = "{base}/{path}".format(base=self.graph_base_url, path=path.lstrip("/"))
        request = Request(
            url,
            headers={
                "Authorization": "Bearer {token}".format(token=self._get_access_token()),
                "Accept": "application/json",
            },
        )
        return self._request_json(request, use_bearer=True)

    def _request_json(self, request: Request, use_bearer: bool) -> dict[str, Any]:
        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            auth_kind = "Graph" if use_bearer else "token"
            raise RuntimeError(
                "Microsoft {auth_kind} request failed for {url}: {body}".format(
                    auth_kind=auth_kind,
                    url=request.full_url,
                    body=body,
                )
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Microsoft Graph request failed for {url}: {error}".format(
                    url=request.full_url,
                    error=exc,
                )
            ) from exc

    def _list_teams(self) -> list[dict[str, Any]]:
        payload = self._graph_request_json("teams")
        return payload.get("value", [])

    def _list_channels(self, team_id: str) -> list[dict[str, Any]]:
        payload = self._graph_request_json("teams/{team_id}/channels".format(team_id=team_id))
        return payload.get("value", [])

    def _list_messages(self, team_id: str, channel_id: str, include_replies: bool) -> list[dict[str, Any]]:
        path = "teams/{team_id}/channels/{channel_id}/messages?$top={top}".format(
            team_id=team_id,
            channel_id=channel_id,
            top=self.max_messages_per_channel,
        )
        payload = self._graph_request_json(path)
        messages = payload.get("value", [])
        for message in messages:
            if not include_replies or not self._should_include_replies_for_message(message):
                continue
            replies = self._list_replies(team_id, channel_id, str(message["id"]))
            if replies:
                message["replies"] = replies
        return messages

    def _list_replies(self, team_id: str, channel_id: str, message_id: str) -> list[dict[str, Any]]:
        payload = self._graph_request_json(
            "teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies".format(
                team_id=team_id,
                channel_id=channel_id,
                message_id=message_id,
            )
        )
        return payload.get("value", [])

    def _resolve_team(self, target: TeamsChannelConfig, teams: list[dict[str, Any]]) -> dict[str, Any]:
        if target.team_id:
            for team in teams:
                if str(team.get("id")) == target.team_id:
                    return team
        if target.team_name:
            target_name = target.team_name.strip().lower()
            for team in teams:
                if str(team.get("displayName", "")).strip().lower() == target_name:
                    return team
        raise RuntimeError("Could not resolve Teams target `{key}` to a team.".format(key=target.key))

    def _resolve_channel(
        self,
        target: TeamsChannelConfig,
        team: dict[str, Any],
        channels: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if target.channel_id:
            for channel in channels:
                if str(channel.get("id")) == target.channel_id:
                    return channel
        if target.channel_name:
            target_name = target.channel_name.strip().lower()
            for channel in channels:
                if str(channel.get("displayName", "")).strip().lower() == target_name:
                    return channel
        raise RuntimeError(
            "Could not resolve Teams target `{key}` to a channel in team `{team}`.".format(
                key=target.key,
                team=team.get("displayName", team.get("id")),
            )
        )

    def _messages_to_records(
        self,
        target: TeamsChannelConfig,
        team: dict[str, Any],
        channel: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        for message in messages:
            records.append(self._message_to_record(target, team, channel, message, is_reply=False, parent_id=None))
            for reply in message.get("replies", []):
                records.append(
                    self._message_to_record(
                        target,
                        team,
                        channel,
                        reply,
                        is_reply=True,
                        parent_id=str(message["id"]),
                    )
                )
        return records

    def _message_to_record(
        self,
        target: TeamsChannelConfig,
        team: dict[str, Any],
        channel: dict[str, Any],
        message: dict[str, Any],
        is_reply: bool,
        parent_id: Optional[str],
    ) -> SourceRecord:
        message_id = str(message["id"])
        body = message.get("body", {})
        body_content = self._body_text(body.get("content", ""))
        created = message.get("createdDateTime")
        from_user = self._message_author(message)
        subject = message.get("subject") or ""
        title_parts = [
            str(team.get("displayName", target.team_name or target.team_id or "Team")),
            str(channel.get("displayName", target.channel_name or target.channel_id or "Channel")),
        ]
        if from_user:
            title_parts.append(from_user)
        if created:
            title_parts.append(str(created))
        title = " | ".join(title_parts)
        if is_reply:
            title = "{title} | reply".format(title=title)

        record_lines = [
            "Team: {team}".format(team=team.get("displayName")),
            "Channel: {channel}".format(channel=channel.get("displayName")),
            "Author: {author}".format(author=from_user or "unknown"),
            "Created: {created}".format(created=created or "unknown"),
        ]
        if subject:
            record_lines.append("Subject: {subject}".format(subject=subject))
        if parent_id:
            record_lines.append("Reply to: {parent}".format(parent=parent_id))
        record_lines.append("Body:")
        record_lines.append(body_content or "(empty message)")

        source_uri = "https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages/{message_id}".format(
            team_id=team.get("id"),
            channel_id=channel.get("id"),
            message_id=message_id,
        )
        entity_keys = [
            key
            for key in [
                str(team.get("displayName", "")),
                str(channel.get("displayName", "")),
                from_user or "",
                message_id,
                parent_id or "",
            ]
            if key
        ]
        metadata = {
            "target_key": target.key,
            "team_id": str(team.get("id")),
            "team_name": team.get("displayName"),
            "channel_id": str(channel.get("id")),
            "channel_name": channel.get("displayName"),
            "message_id": message_id,
            "parent_message_id": parent_id,
            "is_reply": is_reply,
            "subject": subject or None,
            "created_at": created,
            "last_modified_at": message.get("lastModifiedDateTime"),
            "deleted_at": message.get("deletedDateTime"),
            "author": from_user,
            "reply_count": message.get("replyCount"),
            "web_url": message.get("webUrl"),
            "importance": message.get("importance"),
        }
        return SourceRecord(
            record_id="{target}:{message_id}".format(target=target.key, message_id=message_id),
            connector=self.name,
            source_kind=SourceKind.TEAMS,
            title=title,
            body="\n".join(record_lines),
            source_uri=source_uri,
            entity_keys=entity_keys,
            metadata=metadata,
        )

    @staticmethod
    def _message_author(message: dict[str, Any]) -> Optional[str]:
        from_payload = message.get("from", {})
        user = from_payload.get("user") or {}
        application = from_payload.get("application") or {}
        device = from_payload.get("device") or {}
        return (
            user.get("displayName")
            or application.get("displayName")
            or device.get("displayName")
            or None
        )

    @staticmethod
    def _body_text(content: str) -> str:
        parser = _HTMLTextExtractor()
        parser.feed(unescape(content or ""))
        return parser.text()

    @staticmethod
    def _should_include_replies_for_message(message: dict[str, Any]) -> bool:
        return bool(message.get("id"))
