from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evaluacion.engine.communication_llm_config import parse_env_bool, parse_env_choice
from evaluacion.engine.communication_llm_models import (
    COMMUNICATION_LLM_MODELS,
    get_content_llm_model,
    get_delivery_llm_model,
    get_global_synthesis_llm_model,
    get_visual_llm_model,
)


class CommunicationLlmConfigTests(unittest.TestCase):
    def test_parse_env_bool_truthy_falsy_and_default(self) -> None:
        with patch.dict(os.environ, {'FLAG_A': 'true', 'FLAG_B': '0', 'FLAG_C': ''}, clear=False):
            self.assertTrue(parse_env_bool('FLAG_A', default=False))
            self.assertFalse(parse_env_bool('FLAG_B', default=True))
            self.assertFalse(parse_env_bool('FLAG_C', default=False))
            self.assertTrue(parse_env_bool('MISSING_FLAG', default=True))

    def test_parse_env_choice_uses_default_when_invalid(self) -> None:
        with patch.dict(os.environ, {'MODE_A': 'llm_v1', 'MODE_B': 'invalid'}, clear=False):
            self.assertEqual(parse_env_choice('MODE_A', allowed={'metadata', 'llm_v1'}, default='metadata'), 'llm_v1')
            self.assertEqual(parse_env_choice('MODE_B', allowed={'metadata', 'llm_v1'}, default='metadata'), 'metadata')

    def test_model_mapping_is_explicit_in_code(self) -> None:
        self.assertEqual(set(COMMUNICATION_LLM_MODELS.keys()), {'content', 'delivery', 'visual', 'global_synthesis'})
        self.assertEqual(get_content_llm_model(), COMMUNICATION_LLM_MODELS['content'])
        self.assertEqual(get_delivery_llm_model(), COMMUNICATION_LLM_MODELS['delivery'])
        self.assertEqual(get_visual_llm_model(), COMMUNICATION_LLM_MODELS['visual'])
        self.assertEqual(get_global_synthesis_llm_model(), COMMUNICATION_LLM_MODELS['global_synthesis'])

    def test_env_model_vars_do_not_override_code_model_mapping(self) -> None:
        with patch.dict(
            os.environ,
            {
                'COMM_CONTENT_OPENAI_MODEL': 'gpt-override-content',
                'COMM_AUDIO_OPENAI_MODEL': 'gpt-override-delivery',
                'COMM_VISUAL_OPENAI_MODEL': 'gpt-override-visual',
                'COMM_SYNTHESIS_OPENAI_MODEL': 'gpt-override-synthesis',
            },
            clear=False,
        ):
            self.assertEqual(get_content_llm_model(), COMMUNICATION_LLM_MODELS['content'])
            self.assertEqual(get_delivery_llm_model(), COMMUNICATION_LLM_MODELS['delivery'])
            self.assertEqual(get_visual_llm_model(), COMMUNICATION_LLM_MODELS['visual'])
            self.assertEqual(get_global_synthesis_llm_model(), COMMUNICATION_LLM_MODELS['global_synthesis'])


if __name__ == '__main__':
    unittest.main()
