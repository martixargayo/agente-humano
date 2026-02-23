import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import negotiation_livetrace2_panel


def test_livetrace2_ui_contains_accumulated_turn_list_and_controls():
    html = negotiation_livetrace2_panel()
    assert 'id="turnsList"' in html
    assert 'id="expandAllBtn"' in html
    assert 'id="filtersBtn"' in html
    assert 'Desplegar todo' in html


def test_livetrace2_ui_uses_upsert_identity_for_turns():
    html = negotiation_livetrace2_panel()
    assert 'function turnId(evt)' in html
    assert 'session_id' in html
    assert 'turn_idx' in html
    assert 'trace_index' in html
    assert 'function upsertTurn(evt)' in html


def test_livetrace2_filters_panel_has_exact_items_in_order():
    html = negotiation_livetrace2_panel()
    expected = [
        "'advisor_llm'",
        "'world_gate'",
        "'world_extractor_llm'",
        "'belief_gate'",
        "'belief_llm'",
        "'planner_gate'",
        "'planner_llm'",
        "'executor_llm'",
    ]
    start = html.index('const FILTER_NODE_ORDER = [')
    end = html.index('];', start)
    block = html[start:end]
    cursor = -1
    for item in expected:
        pos = block.find(item)
        assert pos != -1
        assert pos > cursor
        cursor = pos


def test_livetrace2_collapsed_turn_summary_strip_uses_fixed_order_and_boxes():
    html = negotiation_livetrace2_panel()
    assert 'const SUMMARY_NODE_ORDER = FILTER_NODE_ORDER;' in html
    assert 'function buildSummaryNodes(allNodes)' in html
    assert 'class="summary-strip"' in html
    assert 'class="summary-box' in html


def test_livetrace2_filters_apply_to_strip_and_reset_opened_node():
    html = negotiation_livetrace2_panel()
    assert 'expandedNodeByTurn = new Map()' in html
    assert 'if(nodeName === name && !activeFilters.has(nodeName)) expandedNodeByTurn.set(tid, null);' in html
    assert '.filter((node)=>activeFilters.has(String(node.node_name || \'\')))' in html


def test_livetrace2_collapsed_strip_click_toggles_single_node_detail_per_turn():
    html = negotiation_livetrace2_panel()
    assert "const selectedNodeName = expandedNodeByTurn.get(id) || null;" in html
    assert "const oneNodeDetail = selectedNode ? `<div class=\"node\" style=\"margin-top:8px\">${detail(selectedNode)}</div>` : '';" in html
    assert "expandedNodeByTurn.set(tid, current === nodeName ? null : nodeName);" in html


def test_livetrace2_has_global_and_local_expand_controls():
    html = negotiation_livetrace2_panel()
    assert 'expandAll = !expandAll' in html
    assert "expandAll ? 'Contraer todo' : 'Desplegar todo'" in html
    assert 'class="pill local-toggle"' in html
    assert "localExpanded.has(id) ? 'Ocultar' : 'Desplegar'" in html


def test_livetrace2_ts_helper_handles_invalid_timestamp_values():
    html = negotiation_livetrace2_panel()
    assert "Number.isNaN(d.getTime()) ? 'NO TIMESTAMPS' : d.toISOString()" in html
    assert "Math.abs(v) < 1e12" in html
