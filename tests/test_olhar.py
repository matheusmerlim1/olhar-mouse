"""Geometria dos olhos, regressão olhar→tela, filtro e congelamento do cursor."""
import unittest

import numpy as np

from olhar.app import Congelador
from olhar.calibracao import pontos_calibracao
from olhar.filtro import OneEuro2D
from olhar.modelo_olhar import ModeloOlhar
from olhar.olhos import OLHO, ear, medir, posicao_iris, vetor_olhar


def rosto_sintetico(abertura=0.3, iris_dx=0.0, iris_dy=0.0, nariz_dx=0.0):
    """478 pontos com os olhos desenhados à mão (só os índices que o código usa)."""
    pts = np.zeros((478, 2))
    for lado, cx in (("direito", 200.0), ("esquerdo", 320.0)):
        o = OLHO[lado]
        larg = 60.0
        sinal = 1 if lado == "direito" else -1      # externo→interno: +x no direito, -x no esquerdo
        ext = np.array([cx - sinal * larg / 2, 200.0])
        inn = np.array([cx + sinal * larg / 2, 200.0])
        p1, p2, p3, p4, p5, p6 = o["ear"]
        pts[p1], pts[p4] = ext, inn
        a = abertura * larg / 2
        pts[p2] = [cx - sinal * 10, 200 - a]
        pts[p3] = [cx + sinal * 10, 200 - a]
        pts[p6] = [cx - sinal * 10, 200 + a]
        pts[p5] = [cx + sinal * 10, 200 + a]
        c = np.array([cx + iris_dx * larg, 200 + iris_dy * larg])
        for k, d in zip(o["iris"], [(0, 0), (6, 0), (0, -6), (-6, 0), (0, 6)]):
            pts[k] = c + d
    pts[1] = [260 + nariz_dx, 260]
    return pts


class TestOlhos(unittest.TestCase):
    def test_ear_aberto_maior_que_fechado(self):
        aberto = ear(rosto_sintetico(0.3), "direito")
        fechado = ear(rosto_sintetico(0.05), "direito")
        self.assertAlmostEqual(aberto, 0.3, places=6)
        self.assertLess(fechado, 0.1)

    def test_iris_mesmo_sentido_nos_dois_olhos(self):
        m = medir(rosto_sintetico(iris_dx=0.1))
        f = vetor_olhar(m, "ambos")
        self.assertAlmostEqual(f[0], 0.1, places=6)  # olhar para +x da imagem → u > 0
        self.assertAlmostEqual(vetor_olhar(m, "direito")[0], 0.1, places=6)
        self.assertAlmostEqual(vetor_olhar(m, "esquerdo")[0], -0.1, places=6)

    def test_iris_vertical_para_baixo_positivo(self):
        u, v = posicao_iris(rosto_sintetico(iris_dy=0.05), "esquerdo")
        self.assertAlmostEqual(v, 0.05, places=6)

    def test_pose_da_cabeca(self):
        m0 = medir(rosto_sintetico(nariz_dx=0))
        m1 = medir(rosto_sintetico(nariz_dx=24))
        self.assertAlmostEqual(m1.yaw - m0.yaw, 24 / 120, places=6)


class TestModelo(unittest.TestCase):
    def test_recupera_mapeamento_com_ruido(self):
        rng = np.random.default_rng(1)
        w, h = 1920, 1080
        alvos, feats = [], []
        for p in pontos_calibracao(w, h, 13):
            for _ in range(25):
                u = (p[0] / w - 0.5) * 0.3 + rng.normal(0, 0.004)
                v = (p[1] / h - 0.5) * 0.12 + rng.normal(0, 0.003)
                feats.append([u, v, rng.normal(0, 0.01), rng.normal(0, 0.01)])
                alvos.append(p)
        m = ModeloOlhar()
        erro = m.ajustar(np.array(feats), np.array(alvos, float))
        self.assertLess(erro, 60)
        # ponto que não estava na calibração
        prev = m.prever(np.array([(0.6 - 0.5) * 0.3, (0.4 - 0.5) * 0.12, 0, 0]))
        self.assertLess(np.hypot(prev[0] - 0.6 * w, prev[1] - 0.4 * h), 60)

    def test_salvar_e_carregar(self):
        m = ModeloOlhar()
        f = np.random.default_rng(0).normal(size=(50, 4))
        m.ajustar(f, f[:, :2] * 100)
        m2 = ModeloOlhar.de_dict(m.para_dict())
        np.testing.assert_allclose(m.prever(f[0]), m2.prever(f[0]))

    def test_pontos_cobrem_a_tela(self):
        pts = pontos_calibracao(1000, 500, 13)
        self.assertEqual(len(pts), 13)
        self.assertEqual(pts[0], (500, 250))  # começa no centro
        self.assertEqual(min(p[0] for p in pts), 80)
        self.assertEqual(max(p[1] for p in pts), 460)


class TestFiltro(unittest.TestCase):
    def test_tira_tremor_parado(self):
        rng = np.random.default_rng(2)
        f = OneEuro2D(min_cutoff=0.6, beta=0.004)
        saidas = [f(500 + rng.normal(0, 15), 300 + rng.normal(0, 15), i / 30)[0] for i in range(120)]
        self.assertLess(np.std(saidas[30:]), 5)

    def test_acompanha_movimento_grande(self):
        f = OneEuro2D(min_cutoff=0.6, beta=0.004)
        for i in range(30):
            f(100, 100, i / 30)
        for i in range(30, 60):
            x, _ = f(1500, 100, i / 30)
        self.assertGreater(x, 1400)  # em 1 s chegou perto do destino


class TestConfig(unittest.TestCase):
    def test_escolhas_do_menu_ficam_em_dados_e_valem_por_cima(self):
        import json
        import tempfile
        from pathlib import Path
        from olhar.app import ler_config, salvar_config
        d = Path(tempfile.mkdtemp())
        base = d / "config.json"
        base.write_text(json.dumps({"_ajuda": "x", "camera": 0, "oculos": False,
                                    "gestos": {"janela": 2.0}}), encoding="utf-8")
        pessoal = d / "dados" / "config.json"
        cfg = ler_config(base, pessoal)          # sem arquivo pessoal ainda
        self.assertEqual(cfg["camera"], 0)
        cfg["camera"], cfg["oculos"] = "usb", True
        salvar_config(cfg, pessoal)
        self.assertEqual(json.loads(base.read_text(encoding="utf-8"))["camera"], 0)  # base intocada
        cfg2 = ler_config(base, pessoal)
        self.assertEqual((cfg2["camera"], cfg2["oculos"]), ("usb", True))
        self.assertEqual(cfg2["gestos"]["janela"], 2.0)       # ajuste fino da base continua
        self.assertEqual(cfg2["gestos"]["lento_min"], 0.30)   # padrão do programa
        self.assertNotIn("gestos", json.loads(pessoal.read_text(encoding="utf-8")))


class TestCongelador(unittest.TestCase):
    def test_volta_para_antes_da_piscada(self):
        c = Congelador(recuo=0.15, espera=0.2)
        for i in range(30):
            c.registrar(i / 30, 100 + i, 200)  # cursor andando
        p = c.atualizar(1.0, fechando=True)
        self.assertLessEqual(p[0], 100 + 0.85 * 30 + 1)
        self.assertEqual(c.atualizar(1.3, fechando=True), p)    # segue preso
        self.assertEqual(c.atualizar(1.35, fechando=False), p)  # acabou de abrir: espera
        self.assertIsNone(c.atualizar(1.6, fechando=False))     # liberado


if __name__ == "__main__":
    unittest.main()
