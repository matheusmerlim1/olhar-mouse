"""Teste de mira: correção que acompanha a cabeça."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from olhar import mira
from olhar.modelo_olhar import ModeloOlhar


def cabecas(n=10, seed=0):
    rng = np.random.default_rng(seed)
    return np.array([0.5, 0.5, 0.2, 0.0, 0.5]) + rng.normal(0, [0.08, 0.05, 0.03, 0.08, 0.08], (n, 5))


class TestAjuste(unittest.TestCase):
    def test_correcao_acompanha_a_cabeca(self):
        rng = np.random.default_rng(1)
        h = cabecas()
        # erro que cresce conforme a cabeça vai para o lado
        r = np.column_stack([60 + (h[:, 0] - 0.5) * 2500, -40 + (h[:, 4] - 0.5) * 1500]) + rng.normal(0, 8, (10, 2))
        ajuste, base, depois = mira.ajustar(h, r)
        self.assertIsNotNone(ajuste)
        self.assertLess(depois, base * 0.6)
        esq = np.array([0.42, 0.5, 0.2, 0.0, 0.5])
        dir_ = np.array([0.58, 0.5, 0.2, 0.0, 0.5])
        self.assertGreater(ajuste.aplicar(dir_)[0] - ajuste.aplicar(esq)[0], 200)

    def test_deslocamento_constante(self):
        rng = np.random.default_rng(2)
        r = np.array([120.0, -80.0]) + rng.normal(0, 10, (10, 2))
        ajuste, base, depois = mira.ajustar(cabecas(), r)
        self.assertLess(depois, base * 0.3)
        dx, dy = ajuste.aplicar(cabecas()[0])
        self.assertAlmostEqual(dx, 120, delta=30)
        self.assertAlmostEqual(dy, -80, delta=30)

    def test_so_ruido_nao_vira_correcao(self):
        r = np.random.default_rng(3).normal(0, 60, (10, 2))
        ajuste, base, depois = mira.ajustar(cabecas(), r)
        self.assertIsNone(ajuste)
        self.assertEqual(base, depois)

    def test_cabeca_muito_longe_nao_explode(self):
        h = cabecas()
        ajuste, _, _ = mira.ajustar(h, np.column_stack([(h[:, 0] - 0.5) * 3000, np.zeros(10)]))
        dx, dy = ajuste.aplicar([5.0, 5.0, 5.0, 5.0, 5.0])
        self.assertLessEqual(abs(dx), 500)
        self.assertLessEqual(abs(dy), 500)

    def test_guardar_e_ler(self):
        arq = Path(tempfile.mkdtemp()) / "calib.json"
        arq.write_text(json.dumps({"olhar": {}}), encoding="utf-8")
        h = cabecas()
        a, _, _ = mira.ajustar(h, np.array([100.0, 50.0]) + np.random.default_rng(0).normal(0, 5, (10, 2)))
        mira.salvar_ajuste(arq, a)
        d = json.loads(arq.read_text(encoding="utf-8"))
        self.assertIn("olhar", d)
        b = mira.AjusteCabeca.de_dict(d["ajuste"])
        self.assertEqual(a.aplicar(h[0]), b.aplicar(h[0]))
        self.assertIsNone(mira.AjusteCabeca.de_dict(None))


class TestFluxo(unittest.TestCase):
    def rodar(self, teclas, resposta):
        fila = list(teclas)
        with mock.patch.multiple(cv2, imshow=mock.DEFAULT, namedWindow=mock.DEFAULT, setWindowProperty=mock.DEFAULT,
                                 destroyWindow=mock.DEFAULT, waitKey=mock.Mock(side_effect=lambda *_: fila.pop(0))), \
                mock.patch.object(mira, "_medir_ponto", side_effect=resposta):
            return mira.testar(None, None, (1920, 1080), None, "ambos", None, None, None)

    def medicoes(self):
        h = iter(cabecas())
        # o anel cai sempre 150 px à esquerda do alvo
        return lambda *a: (np.array([a[-3][0] - 150, a[-3][1]], float), next(h))

    def test_enter_aplica(self):
        ajuste = self.rodar([13], self.medicoes())
        self.assertIsNotNone(ajuste)
        self.assertAlmostEqual(ajuste.aplicar(cabecas()[0])[0], 150, delta=25)

    def test_esc_descarta(self):
        self.assertIsNone(self.rodar([27], self.medicoes()))

    def test_poucos_pontos_avisa(self):
        with self.assertRaises(RuntimeError):
            self.rodar([], lambda *a: None)


class TestFaixaDaCabeca(unittest.TestCase):
    def test_cabeca_parada_na_calibracao_nao_torna_tudo_fora(self):
        rng = np.random.default_rng(0)
        f = rng.normal([0, -0.08, 0.03, 0.56], [0.09, 0.014, 0.015, 0.016], (200, 4))
        m = ModeloOlhar()
        m.ajustar(f, 960 + f[:, :2] * [6000, 9000])
        mexeu = m.media.copy()
        mexeu[2] += 0.12                 # virada pequena, normal durante o uso
        mexeu[3] -= 0.12
        self.assertFalse(m.fora(mexeu))
        virou = m.media.copy()
        virou[2] += 0.8                  # olhando para o lado de verdade
        self.assertTrue(m.fora(virou))
