from __future__ import annotations

from exaspim_agent.domain.models import Citation, QueryResponse, RetrievalResult


class RuleBasedSynthesizer:
    def synthesize(self, query: str, results: list[RetrievalResult]) -> QueryResponse:
        if not results:
            return QueryResponse(
                query=query,
                answer="No matching source records were found in the local knowledge base.",
                inferences=["This answer is limited by the currently ingested connectors and local index."],
            )

        working_results = self._filter_for_query_intent(query, results) or results
        facts: list[str] = []
        derived_metrics: list[str] = []
        inferences: list[str] = []
        citations: list[Citation] = []
        seen_documents: set[str] = set()

        for result in working_results:
            chunk = result.chunk
            metadata = chunk.metadata
            sample_id = metadata.get("sample_id")
            project_id = metadata.get("project_id")
            stage = metadata.get("pipeline_stage")
            reconstruction_status = metadata.get("reconstruction_status")
            blocker = metadata.get("blocker")

            summary_parts = [chunk.title]
            if sample_id:
                summary_parts.append(f"sample {sample_id}")
            if project_id:
                summary_parts.append(f"project {project_id}")
            if stage:
                summary_parts.append(f"stage {stage}")
            if reconstruction_status:
                summary_parts.append(f"reconstruction {reconstruction_status}")
            if blocker:
                summary_parts.append(f"blocker {blocker}")

            if chunk.document_id not in seen_documents:
                facts.append("; ".join(summary_parts))
                seen_documents.add(chunk.document_id)

            if "reconstructed_cell_count" in metadata:
                derived_metrics.append(
                    f"{chunk.title} reports {metadata['reconstructed_cell_count']} reconstructed cells."
                )

            if blocker:
                inferences.append(f"{chunk.title} appears delayed by {blocker}.")

            citations.append(
                Citation(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    connector=chunk.connector,
                    source_uri=chunk.source_uri,
                    excerpt=chunk.text[:240],
                )
            )

        answer_lines = self._build_answer_lines(query, working_results, facts, derived_metrics, inferences)

        return QueryResponse(
            query=query,
            answer="\n".join(answer_lines),
            facts=facts[:6],
            derived_metrics=derived_metrics[:6],
            inferences=list(dict.fromkeys(inferences))[:6],
            citations=citations[:6],
        )

    def _filter_for_query_intent(
        self,
        query: str,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        normalized_query = query.lower()
        if "annotation" in normalized_query and "reconstruction" in normalized_query and any(
            phrase in normalized_query for phrase in (" not ", "awaiting", "pending", "not reconstruction")
        ):
            filtered = [
                result
                for result in results
                if result.chunk.metadata.get("annotation_status") == "complete"
                and result.chunk.metadata.get("reconstruction_status") != "complete"
            ]
            if filtered:
                return filtered

        if "how many" in normalized_query and "reconstructed" in normalized_query and "cell" in normalized_query:
            filtered = [
                result for result in results if "reconstructed_cell_count" in result.chunk.metadata
            ]
            if filtered:
                return filtered

        return []

    def _build_answer_lines(
        self,
        query: str,
        results: list[RetrievalResult],
        facts: list[str],
        derived_metrics: list[str],
        inferences: list[str],
    ) -> list[str]:
        normalized_query = query.lower()
        unique_sample_ids = []
        seen_samples = set()
        total_cells = 0
        seen_documents = set()
        for result in results:
            metadata = result.chunk.metadata
            sample_id = metadata.get("sample_id")
            if sample_id and sample_id not in seen_samples:
                unique_sample_ids.append(sample_id)
                seen_samples.add(sample_id)
            if result.chunk.document_id not in seen_documents and "reconstructed_cell_count" in metadata:
                total_cells += int(metadata["reconstructed_cell_count"])
                seen_documents.add(result.chunk.document_id)

        if "how many" in normalized_query and "reconstructed" in normalized_query and "cell" in normalized_query:
            lines = [f"{total_cells} reconstructed cells are explicitly reported in the matched records."]
        elif normalized_query.startswith("which") and unique_sample_ids:
            lines = [f"Matching samples: {', '.join(unique_sample_ids)}."]
        else:
            lines = ["Relevant source records indicate the following:"]

        lines.extend(f"- {fact}" for fact in facts[:4])
        if derived_metrics:
            lines.append("Derived metrics:")
            lines.extend(f"- {item}" for item in derived_metrics[:3])
        if inferences:
            lines.append("Operational observations:")
            lines.extend(f"- {item}" for item in inferences[:3])
        return lines
