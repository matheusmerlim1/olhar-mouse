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
        arq.write_text(json.dumps({"olhar": {}, "palpebra": {"x": 1}}), encoding="utf-8")
        h = cabecas()
        a, _, _ = mira.ajustar(h, np.array([100.0, 50.0]) + np.random.default_rng(0).normal(0, 5, (10, 2)))
        m = ModeloOlhar()
        f = np.random.default_rng(0).normal(0, 0.05, (40, 4))
        m.ajustar(f, 900 + f[:, :2] * 4000)
        mira.salvar_mira(arq, m, a, [{"v": [0, 0, 0, 0], "alvo": [1, 2]}])
        d = json.loads(arq.read_text(encoding="utf-8"))
        self.assertEqual(d["palpebra"], {"x": 1})             # o resto da calibração continua
        self.assertEqual(len(d["pontos"]), 1)
        b = mira.AjusteCabeca.de_dict(d["ajuste"])
        self.assertEqual(a.aplicar(h[0]), b.aplicar(h[0]))
        self.assertIsNone(mira.AjusteCabeca.de_dict(None))


class TestRodadas(unittest.TestCase):
    """Cada rodada recalibra; para na meta, sem melhora ou no Esc."""

    def setUp(self):
        self._espera = (mira.ESPERA_RODADA, mira.ESPERA_FINAL)
        mira.ESPERA_RODADA = mira.ESPERA_FINAL = 0.0

    def tearDown(self):
        mira.ESPERA_RODADA, mira.ESPERA_FINAL = self._espera

    @staticmethod
    def olhar(alvo, rng):
        return np.array([(alvo[0] / 1920 - 0.5) * -0.3 + rng.normal(0, 0.0005),
                         (alvo[1] / 1080 - 0.5) * 0.08 + rng.normal(0, 0.0003),
                         rng.normal(0, 0.01), 0.56 + rng.normal(0, 0.01)])

    def modelo_errado(self, rng):
        w, h, v, a = 1920, 1080, [], []
        for x in (0.1, 0.5, 0.9):
            for y in (0.1, 0.5, 0.9):
                p = (x * w, y * h)
                v.append(self.olhar(p, rng))
                a.append((p[0] + 250, p[1] - 120))       # a calibração saiu deslocada
        m = ModeloOlhar()
        m.ajustar(np.array(v), np.array(a, float))
        return m

    def rodar(self, resposta, modelo, rodadas=None):
        pacote = mock.patch.multiple(cv2, imshow=mock.DEFAULT, namedWindow=mock.DEFAULT, setWindowProperty=mock.DEFAULT,
                                     destroyWindow=mock.DEFAULT, waitKey=mock.Mock(return_value=255))
        with pacote, mock.patch.object(mira, "_medir_ponto", side_effect=resposta) as medir:
            r = mira.testar(None, None, (1920, 1080), modelo, "ambos", None, lambda: None, None, [])
        return r, medir.call_count

    def test_recalibra_e_para_na_meta(self):
        rng = np.random.default_rng(0)
        r, chamadas = self.rodar(lambda *a: (self.olhar(a[-3], rng), cabecas(1, int(rng.integers(1000)))[0]),
                                 self.modelo_errado(rng))
        self.assertIsNotNone(r)
        modelo, _, pontos = r
        self.assertEqual(chamadas, 10)                    # 1ª rodada errada, 2ª já na meta
        self.assertEqual(len(pontos), 10)
        alvo = (300, 900)
        self.assertLess(np.hypot(*(modelo.prever(self.olhar(alvo, rng)) - alvo)), 70)

    def test_esc_no_meio_mantem_o_que_havia(self):
        def esc(*a):
            raise mira.Cancelado
        r, _ = self.rodar(esc, self.modelo_errado(np.random.default_rng(1)))
        self.assertIsNone(r)

    def test_sem_melhorar_para_e_nao_troca(self):
        rng = np.random.default_rng(2)
        r, chamadas = self.rodar(lambda *a: (self.olhar((rng.uniform(0, 1920), rng.uniform(0, 1080)), rng), cabecas(1, 3)[0]),
                                 self.modelo_errado(rng))
        self.assertLessEqual(chamadas, 10 * mira.MAX_RODADAS)
        self.assertGreater(chamadas, 10)

    def test_poucos_pontos_avisa(self):
        with self.assertRaises(RuntimeError):
            self.rodar(lambda *a: None, self.modelo_errado(np.random.default_rng(3)))


class TestDuasTelas(unittest.TestCase):
    MONITORES = [(0, 441, 1920, 1080), (1920, 0, 1080, 1920)]     # o arranjo real: a 2ª em pé, à direita

    def test_alvos_nas_duas_telas(self):
        roteiro = mira.pontos_rodada(self.MONITORES, 1, np.random.default_rng(0))
        self.assertEqual(len(roteiro), 10)
        for (x, y), _, _ in roteiro:
            self.assertTrue(any(m[0] <= x < m[0] + m[2] and m[1] <= y < m[1] + m[3] for m in self.MONITORES), (x, y))
        self.assertEqual(sum(1 for (x, _), _, _ in roteiro if x >= 1920), 5)

    def test_rodadas_mudam_quais_alvos_mexem_a_cabeca(self):
        a = [t for _, t, _ in mira.pontos_rodada(self.MONITORES, 1, np.random.default_rng(0))]
        b = [t for _, t, _ in mira.pontos_rodada(self.MONITORES, 2, np.random.default_rng(0))]
        self.assertNotEqual(a, b)

    def test_ponto_na_area_morta_vai_para_a_tela_mais_proxima(self):
        from olhar.mouse import prender
        self.assertEqual(prender(500, 10, self.MONITORES), (500, 441))       # acima da tela principal
        self.assertEqual(prender(2500, 1000, self.MONITORES), (2500, 1000))  # dentro da 2ª: não mexe
        self.assertEqual(prender(5000, 5000, self.MONITORES), (2999, 1919))


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
