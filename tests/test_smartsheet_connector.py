from exaspim_agent.config import SmartsheetSheetConfig
from exaspim_agent.connectors.smartsheet import SmartsheetConnector


def test_smartsheet_sheet_to_records_preserves_parent_context() -> None:
    connector = SmartsheetConnector(
        api_token="test-token",
        sheets=[
            SmartsheetSheetConfig(
                key="neuron_reconstruction",
                name="Neuron Reconstruction",
                reference="https://app.smartsheet.com/sheets/example",
                important_columns=[
                    "Neuron manually estimated soma compartment",
                    "Neuron CCF soma compartment",
                    "Status One",
                ],
            )
        ],
    )
    sheet_payload = {
        "id": 123,
        "name": "Neuron Reconstruction",
        "columns": [
            {"id": 1, "title": "Labtracks/Specimen ID"},
            {"id": 2, "title": "Genotype"},
            {"id": 3, "title": "Neuron manually estimated soma compartment"},
            {"id": 4, "title": "Neuron CCF soma compartment"},
            {"id": 5, "title": "Status One"},
        ],
        "rows": [
            {
                "id": 10,
                "rowNumber": 1,
                "cells": [
                    {"columnId": 1, "displayValue": "EXA-100"},
                    {"columnId": 2, "displayValue": "Slc17a7-Cre"},
                ],
            },
            {
                "id": 11,
                "rowNumber": 2,
                "parentId": 10,
                "permalink": "https://app.smartsheet.com/row/11",
                "cells": [
                    {"columnId": 3, "displayValue": "VISp"},
                    {"columnId": 4, "displayValue": "VISp2/3"},
                    {"columnId": 5, "displayValue": "Tracing"},
                ],
            },
        ],
    }

    records = connector._sheet_to_records(connector.sheets[0], sheet_payload)

    assert len(records) == 2
    child_record = next(record for record in records if record.metadata["row_id"] == "11")
    assert child_record.metadata["sample_id"] == "EXA-100"
    assert child_record.metadata["reconstruction_sheet_genotype"] == "Slc17a7-Cre"
    assert "genotype" not in child_record.metadata
    assert child_record.metadata["manual_soma_compartment"] == "VISp"
    assert child_record.metadata["ccf_soma_compartment"] == "VISp2/3"
    assert child_record.metadata["status_one"] == "Tracing"
    assert child_record.metadata["is_child_row"] is True
    assert child_record.metadata["parent_columns"]["Labtracks/Specimen ID"] == "EXA-100"
    assert "Parent row context:" in child_record.body


def test_smartsheet_reference_matching_uses_permalink_tokens() -> None:
    connector = SmartsheetConnector(
        api_token="test-token",
        sheets=[SmartsheetSheetConfig(key="specimen_pipeline", name="Specimen Pipeline", reference="unused")],
    )
    summary = connector._resolve_sheet_summary(
        SmartsheetSheetConfig(
            key="manual_registration",
            name="Manual Registration Status",
            reference="https://app.smartsheet.com/sheets/HRFFHXxHP2gfM2CCWmVxvP5PPRjwJ44R2jmRWQv1?view=grid",
        ),
        [
            {
                "id": 999,
                "name": "Manual Registration Status",
                "permalink": "https://app.smartsheet.com/sheets/HRFFHXxHP2gfM2CCWmVxvP5PPRjwJ44R2jmRWQv1",
            }
        ],
    )

    assert summary["id"] == 999


def test_neuron_id_suffix_derives_sample_id() -> None:
    connector = SmartsheetConnector(
        api_token="test-token",
        sheets=[
            SmartsheetSheetConfig(
                key="neuron_reconstruction",
                name="Neuron Reconstruction",
                reference="https://app.smartsheet.com/sheets/example",
            )
        ],
    )
    sheet_payload = {
        "id": 123,
        "name": "Neuron Reconstruction",
        "columns": [
            {"id": 1, "title": "ID"},
            {"id": 2, "title": "Status 1"},
            {"id": 3, "title": "Manual Estimated Soma Compartment"},
        ],
        "rows": [
            {
                "id": 99,
                "rowNumber": 1,
                "cells": [
                    {"columnId": 1, "displayValue": "N005-789202"},
                    {"columnId": 2, "displayValue": "Completed"},
                    {"columnId": 3, "displayValue": "Midbrain"},
                ],
            }
        ],
    }

    records = connector._sheet_to_records(connector.sheets[0], sheet_payload)

    assert len(records) == 1
    record = records[0]
    assert record.metadata["neuron_id"] == "N005-789202"
    assert record.metadata["sample_id"] == "789202"
    assert record.metadata["sample_id_source"] == "derived_from_neuron_id"
