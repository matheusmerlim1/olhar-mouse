"""As três opções de câmera: computador, QR code (Wi-Fi) e cabo USB."""
import unittest
from unittest import mock

import cv2

from olhar import escolha
from olhar.calibracao import Cancelado


class TestRegras(unittest.TestCase):
    def test_virtual(self):
        self.assertTrue(escolha.eh_virtual("OBS Virtual Camera"))
        self.assertFalse(escolha.eh_virtual("HD Webcam C270"))

    def test_camera_do_computador_prefere_real(self):
        self.assertEqual(escolha.camera_do_computador(["OBS Virtual Camera", "HD Webcam"], "usb"), "HD Webcam")

    def test_respeita_a_atual(self):
        nomes = ["HD Webcam", "Pixel 8"]
        self.assertEqual(escolha.camera_do_computador(nomes, "Pixel 8"), "Pixel 8")
        self.assertEqual(escolha.camera_do_computador(nomes, 1), "Pixel 8")

    def test_virtual_nunca_e_oferecida(self):
        self.assertIsNone(escolha.camera_do_computador(["OBS Virtual Camera"], 0))
        self.assertIsNone(escolha.camera_do_computador(["OBS Virtual Camera"], "OBS Virtual Camera"))
        self.assertIsNone(escolha.camera_do_computador([], 0))
        self.assertEqual(escolha.cameras_reais(["OBS Virtual Camera", "HD Webcam"]), ["HD Webcam"])

    def test_opcao_destacada(self):
        self.assertEqual(escolha.opcao_de(0), 1)
        self.assertEqual(escolha.opcao_de("HD Webcam"), 1)
        self.assertEqual(escolha.opcao_de("celular"), 2)
        self.assertEqual(escolha.opcao_de("usb"), 3)


class TestTela(unittest.TestCase):
    """A tela em si, com as teclas simuladas e sem abrir janela."""

    def rodar(self, teclas, nomes=("HD Webcam",), atual=0):
        fila = list(teclas)
        with mock.patch.multiple(cv2, imshow=mock.DEFAULT, namedWindow=mock.DEFAULT,
                                 setWindowProperty=mock.DEFAULT, setMouseCallback=mock.DEFAULT,
                                 destroyWindow=mock.DEFAULT, getWindowProperty=mock.Mock(return_value=1),
                                 waitKey=mock.Mock(side_effect=lambda *_: fila.pop(0) if fila else -1)):
            return escolha.escolher_camera(list(nomes), atual)

    def test_teclas(self):
        self.assertEqual(self.rodar([ord("1")]), "HD Webcam")
        self.assertEqual(self.rodar([ord("2")]), "celular")
        self.assertEqual(self.rodar([-1, -1, ord("3")]), "usb")

    def test_enter_repete_a_ultima(self):
        self.assertEqual(self.rodar([13], atual="usb"), "usb")
        self.assertEqual(self.rodar([13], atual="celular"), "celular")

    def test_sem_camera_real_opcao_1_bloqueada(self):
        # só a câmera do OBS: tecla 1 e Enter (última era o computador) são ignorados
        self.assertEqual(self.rodar([ord("1"), 13, ord("2")], nomes=("OBS Virtual Camera",), atual=0), "celular")

    def test_esc_sai(self):
        with self.assertRaises(Cancelado):
            self.rodar([27])


if __name__ == "__main__":
    unittest.main()
