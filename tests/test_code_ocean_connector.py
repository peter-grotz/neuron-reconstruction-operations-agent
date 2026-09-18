from exaspim_agent.config import CodeOceanCapsuleConfig
from exaspim_agent.connectors.code_ocean import CodeOceanConnector, classify_run
from exaspim_agent.domain.models import SourceKind


class FakeClient:
    def __init__(self, capsule, computations):
        self._capsule = capsule
        self._computations = computations

    def get_capsule(self, capsule_id):
        return self._capsule

    def list_computations(self, capsule_id):
        return self._computations


def test_classify_run_flags_terminated_machine_as_failure() -> None:
    # completed / exit 0 / succeeded but nothing synced — the nasty case.
    comp = {"state": "completed", "exit_code": 0, "end_status": "succeeded", "has_results": False}
    assert classify_run(comp) == "failed_no_results"


def test_classify_run_recognises_real_success() -> None:
    comp = {"state": "completed", "exit_code": 0, "end_status": "succeeded", "has_results": True}
    assert classify_run(comp) == "succeeded"


def test_classify_run_reports_in_progress_state() -> None:
    assert classify_run({"state": "running"}) == "running"


def test_connector_builds_capsule_and_computation_records() -> None:
    client = FakeClient(
        capsule={"name": "snapshot", "status": "release", "owner": "someone"},
        computations=[
            {"id": "c1", "name": "run-a", "created": 2, "state": "completed",
             "exit_code": 0, "end_status": "succeeded", "has_results": True, "run_time": 400},
            {"id": "c2", "name": "run-b", "created": 1, "state": "completed",
             "exit_code": 0, "end_status": "succeeded", "has_results": False, "run_time": 5},
        ],
    )
    connector = CodeOceanConnector(
        client=client,
        capsules=[CodeOceanCapsuleConfig(key="snapshot", capsule_id="abc", name="Snapshot")],
    )
    records = connector.fetch()

    assert all(r.source_kind is SourceKind.CODE_OCEAN for r in records)
    kinds = [r.metadata.get("kind") for r in records]
    assert kinds.count("capsule") == 1
    assert kinds.count("computation") == 2

    # newest computation first, and the no-results run is flagged as failure
    comp_records = [r for r in records if r.metadata.get("kind") == "computation"]
    assert comp_records[0].metadata["computation_id"] == "c1"
    verdicts = {r.metadata["computation_id"]: r.metadata["verdict"] for r in comp_records}
    assert verdicts == {"c1": "succeeded", "c2": "failed_no_results"}

    # capsule id is an entity key so the run can be found by capsule
    assert "abc" in comp_records[0].entity_keys
