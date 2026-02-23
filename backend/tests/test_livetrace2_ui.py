import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import negotiation_livetrace2_panel



def test_livetrace2_ui_contains_grid_and_expand_controls():
    html = negotiation_livetrace2_panel()
    assert "timelineGrid" in html
    assert "Desplegar todo" in html
    assert "Collapse all" in html
    assert "Show skipped/not captured" in html


def test_livetrace2_ui_wide_layout_and_three_columns():
    html = negotiation_livetrace2_panel()
    assert "width:96vw" in html
    assert "grid-template-columns: minmax(420px, 2fr) minmax(210px, 1fr) minmax(210px, 1fr)" in html
    assert "timeline-scroll" in html


def test_ui_does_not_collapse_nodes_by_name():
    html = negotiation_livetrace2_panel()
    assert "const used = new Set();" in html
    assert "for(const node of sorted){" in html
    assert "node.node_id" in html


def test_ui_hidden_nodes_warning_reports_reason():
    html = negotiation_livetrace2_panel()
    assert "computeHiddenNodesMeta" in html
    assert "filtro=" in html
    assert "layout=" in html


def test_ui_order_respects_gate_before_llm_when_same_timestamp():
    html = negotiation_livetrace2_panel()
    assert "const pa = ta === 'gate' ? 0 : 1;" in html
    assert "const pb = tb === 'gate' ? 0 : 1;" in html
