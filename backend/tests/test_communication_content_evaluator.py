from __future__ import annotations

import unittest

from pydantic import ValidationError

from evaluacion.contracts.communication_models import (
    CommunicationContentAidaBlockEvalV1,
    CommunicationContentAidaEvalV1,
)


class CommunicationContentEvaluatorContractsTests(unittest.TestCase):
    def test_aida_block_requires_label_matching_score(self) -> None:
        block = CommunicationContentAidaBlockEvalV1(
            score_1_3=2,
            label='mejorable',
            reason_short='Tu bloque aparece, pero puede ser más claro.',
        )
        self.assertEqual(block.label, 'mejorable')
        with self.assertRaises(ValidationError):
            CommunicationContentAidaBlockEvalV1(
                score_1_3=3,
                label='mal',
                reason_short='inconsistente',
            )

    def test_aida_eval_shape(self) -> None:
        payload = CommunicationContentAidaEvalV1(
            attention={'score_1_3': 1, 'label': 'mal', 'reason_short': 'Falta gancho inicial.'},
            interest={'score_1_3': 2, 'label': 'mejorable', 'reason_short': 'Conecta, pero de forma parcial.'},
            development={'score_1_3': 3, 'label': 'correcto', 'reason_short': 'Explicas con orden y claridad.'},
            action={'score_1_3': 2, 'label': 'mejorable', 'reason_short': 'El cierre puede orientar mejor.'},
        )
        self.assertEqual(payload.development.score_1_3, 3)


if __name__ == '__main__':
    unittest.main()
