from negotiation.executor.render_executor import (
    detect_question_from_text,
    map_slots_from_questions,
)


def test_no_question_no_slots_even_with_precio_keyword():
    text = "Antes de hablar de precios, quiero X."
    assert detect_question_from_text(text) is False
    assert map_slots_from_questions(text) == []


def test_precio_slot_only_from_interrogative_span():
    text = "¿En qué cifra lo dejas?"
    assert detect_question_from_text(text) is True
    assert map_slots_from_questions(text) == ["precio_objetivo"]

