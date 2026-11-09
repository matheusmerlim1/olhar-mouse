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


class TestEstabilidade(unittest.TestCase):
    """Olhar parado num ponto, com o ruído típico da íris: o cursor não pode tremer.
    Testa o caminho inteiro do app (mediana → regressão → One Euro → zona de repouso)."""

    class ModeloIdentidade:
        def prever(self, v):
            return np.asarray(v[:2], float)

    def simular(self, nivel, alvos, ruido=35, seed=3):
        from olhar.app import Suavizador
        rng = np.random.default_rng(seed)
        s, m = Suavizador(nivel), self.ModeloIdentidade()
        return np.array([s([x + rng.normal(0, ruido), y + rng.normal(0, ruido)], m, i / 30)
                         for i, (x, y) in enumerate(alvos)])

    def test_parado_nao_treme(self):
        alvos = [(900, 500)] * 150                      # 5 s olhando o mesmo ponto
        resumo = []
        for nivel in ("baixa", "media", "alta"):
            sai = self.simular(nivel, alvos)[60:]          # depois de a fixação assentar
            passos = np.hypot(*np.diff(sai, axis=0).T)
            mexeu = int((passos > 0.5).sum())
            resumo.append(f"{nivel}: mexeu em {mexeu}/{len(passos)} quadros, média {passos.mean():.1f} px")
            if nivel != "baixa":
                self.assertLess(mexeu, 6, nivel)
                self.assertLess(np.hypot(*(sai.mean(0) - (900, 500))), 25, nivel)  # parado no lugar certo
        print("\n  " + " | ".join(resumo))

    def test_salto_do_olhar_ainda_chega_rapido(self):
        for nivel in ("media", "alta"):
            alvos = [(400, 300)] * 60 + [(1400, 800)] * 60      # olha para outro canto da tela
            sai = self.simular(nivel, alvos)
            chegada = next(i for i in range(60, 120) if np.hypot(*(sai[i] - (1400, 800))) < 80)
            self.assertLess((chegada - 60) / 30, 0.7, nivel)    # menos de 0,7 s
            # e para lá: no máximo UMA correção pequena quando a fixação se firma
            passos = np.hypot(*np.diff(sai[75:], axis=0).T)
            self.assertLessEqual(int((passos > 0.5).sum()), 1, nivel)
            self.assertLess(passos.max(), 60, nivel)

    def test_mediana_tira_pico_de_um_quadro(self):
        from olhar.filtro import MedianaVetor
        m = MedianaVetor(5)
        for v in ([0, 0], [0, 0], [9, 9], [0, 0], [0, 0]):
            r = m(v)
        np.testing.assert_allclose(r, [0, 0])


class TestSegundoMouse(unittest.TestCase):
    def test_cede_ao_mouse_fisico_e_so_retoma_num_olhar_novo(self):
        from olhar.filtro import Estabilizador
        e = Estabilizador(raio=40)
        t = 0.0
        for _ in range(30):                       # olhando para (500, 500)
            e(500, 500, t); t += 1 / 30
        e.ceder()                                 # a pessoa mexeu no mouse físico
        for _ in range(60):                       # continua olhando o mesmo ponto
            self.assertIsNone(e(500 + (t * 7 % 20), 500, t))   # não puxa o cursor de volta
            t += 1 / 30
        self.assertTrue(e.cedido)
        saida = None
        for _ in range(30):                       # olha para outro lugar da tela
            saida = e(1200, 300, t); t += 1 / 30
        self.assertFalse(e.cedido)
        self.assertLess(np.hypot(saida[0] - 1200, saida[1] - 300), 5)


class TestForaDaCalibracao(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        f = rng.normal(0, [0.05, 0.02, 0.1, 0.08], (200, 4))
        self.m = ModeloOlhar()
        self.m.ajustar(f, 960 + f[:, :2] * [6000, 9000] + rng.normal(0, 20, (200, 2)))

    def test_detecta_cabeca_virada(self):
        self.assertFalse(self.m.fora([0.0, 0.0, 0.0, 0.0]))
        self.assertTrue(self.m.fora([0.0, 0.0, 1.2, 0.0]))     # yaw 12 desvios: cabeça virada

    def test_previsao_nao_explode(self):
        longe = self.m.prever([0.5, -0.4, 1.3, 0.6])            # valores medidos com a cabeça virada
        self.assertLess(np.abs(longe - 960).max(), 3000)        # antes chegava a dezenas de milhares


class TestVertical(unittest.TestCase):
    """Olhar e cabeça para cima têm de subir o ponto, mesmo com a íris vertical fraca."""

    def amostras(self, cabeca_na_calibracao, seed=2):
        from olhar.calibracao import pontos_cabeca
        rng = np.random.default_rng(seed)
        w, h = 1920, 1080
        feats, alvos = [], []
        def adiciona(p, olho, cabeca):
            for _ in range(20):
                dx, dy = p[0] / w - 0.5, p[1] / h - 0.5
                feats.append([-0.3 * dx * olho + rng.normal(0, 0.008), 0.05 * dy * olho + rng.normal(0, 0.008),
                              -0.5 * dx * cabeca + rng.normal(0, 0.012), 0.56 + 0.6 * dy * cabeca + rng.normal(0, 0.012)])
                alvos.append(p)
        for p in pontos_calibracao(w, h, 13):
            adiciona(p, 1.0, 0.0)
        if cabeca_na_calibracao:
            for p in pontos_cabeca(w, h):
                adiciona(p, 0.3, 1.0)
        return np.array(feats), np.array(alvos, float)

    def test_cabeca_para_cima_sobe_o_ponto(self):
        m = ModeloOlhar()
        m.ajustar(*self.amostras(True))
        centro = m.media.copy()
        cima = centro.copy()
        cima[3] -= 0.2                                   # levantar o rosto: pitch diminui
        self.assertFalse(m.fora(cima))                   # continua dentro da área calibrada
        self.assertLess(m.prever(cima)[1], m.prever(centro)[1] - 150)

    def test_aprendizado_contrario_da_cabeca_e_descartado(self):
        m = ModeloOlhar()
        f, a = self.amostras(False)
        f[:, 3] = 0.56 - 0.02 * (a[:, 1] / 1080 - 0.5) + np.random.default_rng(0).normal(0, 0.005, len(f))
        m.ajustar(f, a)
        self.assertEqual(m.coef[4, 1], 0.0)              # cabeça ao contrário da íris: fora

    def test_eixos_nao_se_misturam(self):
        m = ModeloOlhar()
        m.ajustar(*self.amostras(True))
        self.assertEqual(m.coef[2, 0], 0.0)              # íris vertical não move o X
        self.assertEqual(m.coef[1, 1], 0.0)              # íris horizontal não move o Y

    def test_calibracao_antiga_continua_valendo(self):
        m = ModeloOlhar()
        f, a = self.amostras(True)
        m.ajustar(f, a, ridge=1.0, forma="quadratico")
        m2 = ModeloOlhar.de_dict(m.para_dict())
        np.testing.assert_allclose(m.prever(f[0]), m2.prever(f[0]))


class TestOlhosENariz(unittest.TestCase):
    """O mesmo modelo tem de servir só com os olhos e apontando o nariz."""

    @staticmethod
    def amostra(alvo, modo, rng):
        dx, dy = alvo[0] / 1920 - 0.5, alvo[1] / 1080 - 0.5
        if modo == "olhos":
            yaw, pitch = rng.normal(0, 0.01), 0.56 + rng.normal(0, 0.01)
            u, v = -0.3 * dx, 0.06 * dy
        else:
            yaw, pitch = -1.0 * dx, 0.56 + 0.2 * dy
            u, v = -0.05 * dx, 0.01 * dy
        # virar o rosto encurta o olho: a íris anda menos com a cabeça girada
        ganho = 1 - 0.5 * abs(yaw)
        return [u * ganho + rng.normal(0, 0.003), v + rng.normal(0, 0.002),
                yaw + rng.normal(0, 0.01), pitch + rng.normal(0, 0.01)]

    def test_acerta_nos_dois_modos(self):
        rng = np.random.default_rng(4)
        grade = [(x * 1920, y * 1080) for x in (0.1, 0.3, 0.5, 0.7, 0.9) for y in (0.1, 0.5, 0.9)]
        f, a, modos = [], [], []
        for p in grade:
            for modo in ("olhos", "nariz"):
                for _ in range(10):
                    f.append(self.amostra(p, modo, rng))
                    a.append(p)
                    modos.append(modo)
        m = ModeloOlhar()
        m.ajustar(np.array(f), np.array(a, float))
        self.assertEqual(m.forma, "modos")
        for modo in ("olhos", "nariz"):
            alvo = (1250, 400)
            erro = np.mean([np.hypot(*(m.prever(self.amostra(alvo, modo, rng)) - alvo)) for _ in range(30)])
            self.assertLess(erro, 200, modo)

    def test_salva_e_le_o_modelo_novo(self):
        rng = np.random.default_rng(5)
        f = np.array([self.amostra((x, 500), "olhos", rng) for x in np.linspace(100, 1800, 60)])
        a = np.column_stack([np.linspace(100, 1800, 60), np.full(60, 500.0)])
        m = ModeloOlhar()
        m.ajustar(f, a)
        m2 = ModeloOlhar.de_dict(m.para_dict())
        self.assertEqual(m2.forma, "modos")
        np.testing.assert_allclose(m.prever(f[0]), m2.prever(f[0]))
