"""Segundo ponteiro (clique devolve o cursor) e zoom automático."""
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from olhar import mouse
from olhar.celular import CameraCelular
from olhar.zoom import INTEIRA, Zoom


class TestCliqueDevolveCursor(unittest.TestCase):
    def test_clica_no_anel_e_volta(self):
        ordem = []
        with mock.patch.object(mouse, "posicao", return_value=(10, 20)), \
                mock.patch.object(mouse, "mover", side_effect=lambda x, y: ordem.append(("mover", x, y))), \
                mock.patch.object(mouse, "clicar", side_effect=lambda b: ordem.append(("clicar", b))):
            mouse.clicar_em("esquerdo", 800, 600)
        self.assertEqual(ordem, [("mover", 800, 600), ("clicar", "esquerdo"), ("mover", 10, 20)])


class TestZoom(unittest.TestCase):
    ROSTO_PEQUENO = (0.40, 0.35, 0.60, 0.65)     # 20 % da largura da imagem

    def test_amplia_rosto_pequeno_e_centraliza(self):
        z = Zoom()
        self.assertTrue(z.atualizar(self.ROSTO_PEQUENO, INTEIRA, 0.0))
        x, y, l, a = z.recorte
        self.assertAlmostEqual(0.20 / l, 0.42, places=2)         # rosto passa a ocupar 42 %
        self.assertAlmostEqual(x + l / 2, 0.50, places=2)
        self.assertAlmostEqual(y + a / 2, 0.50, places=2)

    def test_quadro_ja_recortado_nao_muda_o_recorte(self):
        z = Zoom()
        z.atualizar(self.ROSTO_PEQUENO, INTEIRA, 0.0)
        usado = z.recorte
        # o mesmo rosto visto dentro do recorte
        caixa = ((0.40 - usado[0]) / usado[2], (0.35 - usado[1]) / usado[3],
                 (0.60 - usado[0]) / usado[2], (0.65 - usado[1]) / usado[3])
        self.assertFalse(z.atualizar(caixa, usado, 0.1))

    def test_tremido_pequeno_nao_mexe_e_saida_do_centro_mexe(self):
        z = Zoom()
        z.atualizar(self.ROSTO_PEQUENO, INTEIRA, 0.0)
        self.assertFalse(z.atualizar((0.41, 0.35, 0.61, 0.65), INTEIRA, 0.1))
        self.assertTrue(z.atualizar((0.60, 0.35, 0.80, 0.65), INTEIRA, 0.2))

    def test_recorte_nunca_sai_da_imagem(self):
        z = Zoom()
        z.atualizar((0.0, 0.0, 0.15, 0.2), INTEIRA, 0.0)
        x, y, l, a = z.recorte
        self.assertGreaterEqual(min(x, y), 0.0)
        self.assertLessEqual(x + l, 1.0)
        self.assertLessEqual(y + a, 1.0)

    def test_sem_rosto_abre_a_imagem_depois_de_um_tempo(self):
        z = Zoom()
        z.atualizar(self.ROSTO_PEQUENO, INTEIRA, 0.0)
        self.assertFalse(z.atualizar(None, z.recorte, 0.2))      # perdeu por um instante: mantém
        self.assertTrue(z.atualizar(None, z.recorte, 2.0))
        self.assertEqual(z.recorte, INTEIRA)

    def test_desligado_usa_imagem_inteira(self):
        z = Zoom(ligado=False)
        z.atualizar(self.ROSTO_PEQUENO, INTEIRA, 0.0)
        self.assertEqual(z.recorte, INTEIRA)


class TestRecorteNoServidor(unittest.TestCase):
    def enviar(self, cam, recorte=None):
        jpg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))[1].tobytes()
        cab = {"X-Sessao": "aba"}
        if recorte:
            cab["X-Recorte"] = recorte
        return urllib.request.urlopen(urllib.request.Request(cam.url + "/quadro", data=jpg, headers=cab), timeout=5)

    def test_ida_e_volta_do_recorte(self):
        cam = CameraCelular(Path(tempfile.mkdtemp()), porta=8500, usb=True)
        try:
            cam.recorte_pedido = (0.25, 0.1, 0.5, 0.5)
            r = self.enviar(cam, "0.1,0.2,0.6,0.6")
            self.assertEqual(r.headers["X-Recorte"], "0.2500,0.1000,0.5000,0.5000")
            self.assertTrue(cam.read()[0])
            self.assertEqual(cam.recorte_do_quadro, (0.1, 0.2, 0.6, 0.6))
            self.enviar(cam)                      # página antiga, sem o cabeçalho
            cam.read()
            self.assertEqual(cam.recorte_do_quadro, (0.0, 0.0, 1.0, 1.0))
        finally:
            cam.release()


class TestEnquadramento(unittest.TestCase):
    def test_diz_o_que_ajustar(self):
        from olhar.camera import aviso_enquadramento
        self.assertIn("para baixo", aviso_enquadramento([0.36, 0.93, 0.39]))   # o caso medido
        self.assertIn("para cima", aviso_enquadramento([0.5, 0.1, 0.3]))
        self.assertIn("meio", aviso_enquadramento([0.92, 0.5, 0.3]))
        self.assertIsNone(aviso_enquadramento([0.5, 0.5, 0.38]))

