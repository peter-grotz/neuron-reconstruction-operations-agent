import pytest

from exaspim_agent.application.live_tools import MorphologyPortalQueryTool
from exaspim_agent.connectors.morphology_portal import MorphologyPortalConnector
from exaspim_agent.domain.models import SourceKind


class FakeClient:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def query(self, query, variables=None):
        self.calls.append((query, variables))
        return self._result


SPECIMENS_RESULT = {
    "data": {
        "specimens": {
            "totalCount": 2,
            "items": [
                {"id": "s1", "label": "841260", "collectionId": "col1", "neuronCount": 1031,
                 "genotype": {"id": "g1", "name": "wt/wt"},
                 "collection": {"id": "col1", "name": "ExaSPIM"}},
                {"id": "s2", "label": "999999", "collectionId": "col2", "neuronCount": 5,
                 "genotype": None, "collection": {"id": "col2", "name": "Other"}},
            ],
        }
    }
}


def test_connector_indexes_one_record_per_specimen() -> None:
    connector = MorphologyPortalConnector(client=FakeClient(SPECIMENS_RESULT))
    records = connector.fetch()
    assert len(records) == 2
    assert all(r.source_kind is SourceKind.MORPHOLOGY_PORTAL for r in records)
    first = records[0]
    assert first.entity_keys == ["841260"]
    assert first.metadata["neuron_count"] == 1031


def test_collection_filter_excludes_other_collections() -> None:
    connector = MorphologyPortalConnector(
        client=FakeClient(SPECIMENS_RESULT), collection_filter="ExaSPIM"
    )
    records = connector.fetch()
    assert [r.metadata["specimen_id"] for r in records] == ["s1"]


def test_query_errors_are_surfaced() -> None:
    connector = MorphologyPortalConnector(
        client=FakeClient({"errors": [{"message": "boom"}]})
    )
    with pytest.raises(RuntimeError, match="boom"):
        connector.fetch()


def test_query_tool_rejects_mutations() -> None:
    tool = MorphologyPortalQueryTool(client=FakeClient(SPECIMENS_RESULT))
    with pytest.raises(ValueError, match="read-only"):
        tool.run({"query": "mutation { deleteSpecimen(id: \"x\") }"})


def test_query_tool_passes_read_queries_through() -> None:
    client = FakeClient(SPECIMENS_RESULT)
    tool = MorphologyPortalQueryTool(client=client)
    result = tool.run({"query": "{ specimens { totalCount } }"})
    assert result.output == SPECIMENS_RESULT
    assert len(client.calls) == 1
