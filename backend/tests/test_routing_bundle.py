"""routing_bundle 单测（P1-4）。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from services.routing_bundle import build_routing_search_bundle


@patch("services.routing_bundle.search_metrics_and_terms")
@patch("services.routing_bundle.search_kb_hybrid_unified")
@patch("services.routing_bundle._embed")
def test_build_routing_bundle_dedupes_kb_search(mock_embed, mock_unified, mock_metrics):
    mock_embed.return_value = [[0.1] * 8]
    mock_unified.return_value = [{"source_type": "entry", "entry_id": 1, "title": "t", "summary": "", "snippet": "s"}]
    mock_metrics.return_value = ("", set(), {})

    db = MagicMock()
    with patch("services.context_builder.kb_ids_for_business_domain", return_value=[3, 4]):
        with patch("services.context_builder.tables_from_business_domain", return_value=[]):
            bundle = asyncio.run(build_routing_search_bundle(db, "GMV 趋势", business_domain_id=1, table_id=None))

    assert bundle.embed_calls == 1
    assert bundle.kb_search_calls == 2
    assert mock_unified.call_count == 2
    assert len(bundle.merged_hits) == 1
