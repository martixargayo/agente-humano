import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import negotiation_livetrace2_panel



def test_livetrace2_ui_contains_grid_and_expand_controls():
    html = negotiation_livetrace2_panel()
    assert "timelineGrid" in html
    assert "Desplegar todo" in html
    assert "Collapse all" in html


def test_livetrace2_ui_wide_layout_and_three_columns():
    html = negotiation_livetrace2_panel()
    assert "width:96vw" in html
    assert "grid-template-columns: repeat(3" in html
