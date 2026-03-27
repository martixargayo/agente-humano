from __future__ import annotations

COMMUNICATION_LLM_MODELS: dict[str, str] = {
    'content': 'gpt-4.1-mini',
    'delivery': 'gpt-4.1-mini',
    'visual': 'gpt-4.1-mini',
    'global_synthesis': 'gpt-4.1-mini',
}


def get_content_llm_model() -> str:
    return COMMUNICATION_LLM_MODELS['content']


def get_delivery_llm_model() -> str:
    return COMMUNICATION_LLM_MODELS['delivery']


def get_visual_llm_model() -> str:
    return COMMUNICATION_LLM_MODELS['visual']


def get_global_synthesis_llm_model() -> str:
    return COMMUNICATION_LLM_MODELS['global_synthesis']
