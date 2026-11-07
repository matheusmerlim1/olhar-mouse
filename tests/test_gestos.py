"""Testes da máquina de piscadas com sequências sintéticas (30 quadros/s)."""
import unittest

from olhar.gestos import CalibPalpebra, ConfigGestos, Gestos, Palpebras

FPS = 30


class Roteiro:
    """Monta uma linha do tempo: lista de (duração_s, olho_esq_fechado, olho_dir_fechado)."""

    def __init__(self, gestos):
        self.g = gestos
        self.t = 0.0
        self.cliques = []

    def rodar(self, *trechos):
        for dur, fe, fd in trechos:
            for _ in range(round(dur * FPS)):
                c = self.g.atualizar(self.t, fe, fd)
                if c:
                    self.cliques.append(c)
                self.t += 1 / FPS
        return self.cliques


A = (False, False)   # aberto
F = (True, True)     # os dois fechados
E = (True, False)    # só o esquerdo fechado
D = (False, True)    # só o direito fechado


def t(dur, estado):
    return (dur, *estado)


class TestGestosDoisOlhos(unittest.TestCase):
    def novo(self, **kw):
        return Roteiro(Gestos(ConfigGestos(**kw)))

    def test_duas_piscadas_lentas_clique_direito(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.5, F), t(0.4, A), t(0.5, F), t(1, A))
        self.assertEqual(c, ["direito"])

    def test_duas_piscadelas_lentas_clique_esquerdo(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.5, E), t(0.4, A), t(0.5, E), t(1, A))
        self.assertEqual(c, ["esquerdo"])

    def test_piscadela_com_olho_direito_tambem_vale(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.5, D), t(0.4, A), t(0.5, D), t(1, A))
        self.assertEqual(c, ["esquerdo"])

    def test_olho_segurado_e_outro_pisca_duas_vezes(self):
        # esquerdo fica fechado o tempo todo; o direito pisca 2x devagar
        r = self.novo()
        c = r.rodar(t(1, A), t(0.6, E), t(0.5, F), t(0.4, E), t(0.5, F), t(0.5, E), t(1, A))
        self.assertEqual(c, ["esquerdo"])

    def test_olho_segurado_terminando_com_os_dois_abrindo_juntos(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.6, D), t(0.5, F), t(0.4, D), t(0.5, F), t(1, A))
        self.assertEqual(c, ["esquerdo"])

    def test_piscadas_normais_rapidas_sao_ignoradas(self):
        r = self.novo()
        c = r.rodar(*[x for _ in range(6) for x in (t(0.15, F), t(0.6, A))])
        self.assertEqual(c, [])

    def test_uma_so_piscada_lenta_nao_clica(self):
        r = self.novo()
        self.assertEqual(r.rodar(t(1, A), t(0.5, F), t(3, A)), [])

    def test_intervalo_longo_entre_piscadas_nao_clica(self):
        r = self.novo()
        self.assertEqual(r.rodar(t(1, A), t(0.5, F), t(2.5, A), t(0.5, F), t(1, A)), [])

    def test_olho_fechado_muito_tempo_cancela(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.5, F), t(0.4, A), t(3.0, F), t(1, A))
        self.assertEqual(c, [])

    def test_piscada_rapida_no_meio_nao_atrapalha(self):
        r = self.novo()
        c = r.rodar(t(1, A), t(0.5, F), t(0.3, A), t(0.12, F), t(0.3, A), t(0.5, F), t(1, A))
        self.assertEqual(c, ["direito"])

    def test_mistura_piscada_e_piscadela_nao_clica(self):
        r = self.novo()
        self.assertEqual(r.rodar(t(1, A), t(0.5, F), t(0.4, A), t(0.5, E), t(1, A)), [])

    def test_olhos_nao_fecham_ao_mesmo_tempo(self):
        # o esquerdo fecha 50 ms antes e abre 50 ms depois: ainda é piscada
        r = self.novo()
        c = r.rodar(t(1, A), t(0.05, E), t(0.45, F), t(0.05, E), t(0.4, A),
                    t(0.05, D), t(0.45, F), t(1, A))
        self.assertEqual(c, ["direito"])

    def test_ruido_de_um_quadro_e_filtrado(self):
        r = self.novo()
        ruido = [x for _ in range(20) for x in (t(1 / FPS, F), t(0.3, A))]
        self.assertEqual(r.rodar(*ruido), [])

    def test_quatro_piscadas_lentas_dao_dois_cliques_respeitando_pausa(self):
        r = self.novo()
        seq = [t(1, A)] + [x for _ in range(4) for x in (t(0.5, F), t(0.5, A))] + [t(1, A)]
        self.assertEqual(r.rodar(*seq), ["direito", "direito"])

    def test_fechando_indica_olho_fechado(self):
        g = Gestos()
        tt = 0.0
        for _ in range(10):
            g.atualizar(tt, False, False)
            tt += 1 / FPS
        self.assertFalse(g.fechando)
        g.atualizar(tt, True, True)
        self.assertTrue(g.fechando)  # já congela no primeiro quadro fechado


class TestGestosUmOlho(unittest.TestCase):
    def novo(self):
        return Roteiro(Gestos(ConfigGestos(um_olho=True)))

    def test_duas_lentas_direito(self):
        c = self.novo().rodar(t(1, A), t(0.5, F), t(0.4, A), t(0.5, F), t(2, A))
        self.assertEqual(c, ["direito"])

    def test_tres_lentas_esquerdo(self):
        c = self.novo().rodar(t(1, A), t(0.5, F), t(0.4, A), t(0.5, F), t(0.4, A), t(0.5, F), t(2, A))
        self.assertEqual(c, ["esquerdo"])

    def test_uma_lenta_nada(self):
        self.assertEqual(self.novo().rodar(t(1, A), t(0.5, F), t(3, A)), [])


class TestPalpebras(unittest.TestCase):
    def test_calibracao_por_usuario(self):
        # pessoa de óculos: EAR aberto 0,20 e fechado 0,12 (faixa estreita)
        cal = CalibPalpebra(aberto_e=0.20, fechado_e=0.12, aberto_d=0.21, fechado_d=0.13)
        p = Palpebras(cal, janela_mediana=1)
        self.assertEqual(p.atualizar(0.20, 0.21), (False, False))
        self.assertEqual(p.atualizar(0.12, 0.21), (True, False))
        self.assertEqual(p.atualizar(0.12, 0.13), (True, True))

    def test_histerese(self):
        cal = CalibPalpebra(0.30, 0.10, 0.30, 0.10)
        p = Palpebras(cal, janela_mediana=1)
        p.atualizar(0.16, 0.16)  # 70 % fechado → fecha
        self.assertTrue(p.fechado["esq"])
        p.atualizar(0.20, 0.20)  # 50 %: ainda dentro da histerese, continua fechado
        self.assertTrue(p.fechado["esq"])
        p.atualizar(0.24, 0.24)  # 30 % → abre
        self.assertFalse(p.fechado["esq"])

    def test_mediana_tira_pico_de_reflexo(self):
        cal = CalibPalpebra(0.30, 0.10, 0.30, 0.10)
        p = Palpebras(cal, janela_mediana=5)
        for ear in (0.30, 0.30, 0.05, 0.30, 0.30):  # reflexo na lente em 1 quadro
            p.atualizar(ear, 0.30)
            self.assertFalse(p.fechado["esq"])


if __name__ == "__main__":
    unittest.main()
