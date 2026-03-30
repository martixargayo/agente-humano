from __future__ import annotations

import json
import unittest

from negociacion.contexts import list_official_negotiation_contexts
from negociacion.state.canonical_state import parse_negotiation_brief_payload


class NegotiationContextAssetsSchemaTests(unittest.TestCase):
    def test_all_official_context_negotiation_brief_files_follow_runtime_parser(self) -> None:
        contexts = list_official_negotiation_contexts()
        for context in contexts:
            with self.subTest(context_id=context.context_id):
                payload = json.loads(context.negotiation_brief_path.read_text(encoding='utf-8'))
                model = parse_negotiation_brief_payload(payload)
                self.assertEqual(model.schema_version, 'negotiation_brief.v1')

    def test_sala_reuniones_supports_restricciones_and_legacy_keys(self) -> None:
        contexts = {c.context_id: c for c in list_official_negotiation_contexts()}
        payload = json.loads(contexts['sala_reuniones'].negotiation_brief_path.read_text(encoding='utf-8'))
        model = parse_negotiation_brief_payload(payload)
        self.assertIsNotNone(model.restricciones)
        self.assertIn('única sala demo', model.contexto_de_mercado.valor_estimado)


if __name__ == '__main__':
    unittest.main()
