"""Câmera do celular: servidor (Wi-Fi/HTTPS e cabo/HTTP local) e leitura do `adb devices`."""
import ssl
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from olhar.celular import CameraCelular, imagem_qr
from olhar.usb import ler_aparelhos

JPEG = cv2.imencode(".jpg", np.full((48, 64, 3), 128, np.uint8))[1].tobytes()
SEM_VERIFICAR = ssl.create_default_context()
SEM_VERIFICAR.check_hostname = False
SEM_VERIFICAR.verify_mode = ssl.CERT_NONE


def enviar(url, dados=JPEG, ctx=None, sessao="aba-teste"):
    cab = {"Content-Type": "image/jpeg"}
    if sessao:
        cab["X-Sessao"] = sessao
    req = urllib.request.Request(url, data=dados, headers=cab)
    return urllib.request.urlopen(req, context=ctx, timeout=5).status


class TestCameraUsb(unittest.TestCase):
    def setUp(self):
        self.cam = CameraCelular(Path(tempfile.mkdtemp()), porta=8470, usb=True)

    def tearDown(self):
        self.cam.release()

    def test_endereco_http_local(self):
        self.assertTrue(self.cam.url.startswith(f"http://127.0.0.1:{self.cam.porta}/"))

    def test_so_escuta_no_proprio_pc(self):
        self.assertEqual(self.cam._srv.server_address[0], "127.0.0.1")

    def test_recebe_quadro(self):
        self.assertEqual(enviar(self.cam.url + "/quadro"), 204)
        ok, img = self.cam.read()
        self.assertTrue(ok)
        self.assertEqual(img.shape, (48, 64, 3))
        self.assertTrue(self.cam.conectado())

    def test_codigo_errado_recusado(self):
        base = self.cam.url.rsplit("/", 1)[0]
        with self.assertRaises(urllib.error.HTTPError) as e:
            enviar(base + "/errado/quadro")
        self.assertEqual(e.exception.code, 404)

    def test_so_a_aba_mais_nova_vale(self):
        url = self.cam.url + "/quadro"
        self.assertEqual(enviar(url, sessao="aba1"), 204)
        self.assertEqual(enviar(url, sessao="aba2"), 204)      # abriu outra aba: ela passa a valer
        with self.assertRaises(urllib.error.HTTPError) as e:
            enviar(url, sessao="aba1")                           # a antiga é mandada parar
        self.assertEqual(e.exception.code, 409)
        self.assertEqual(enviar(url, sessao="aba2"), 204)
        with self.assertRaises(urllib.error.HTTPError) as e:
            enviar(url, sessao="")                               # página antiga, sem sessão
        self.assertEqual(e.exception.code, 409)
        self.assertEqual(self.cam.recebidos, 3)

    def test_pagina_pede_camera(self):
        pag = urllib.request.urlopen(self.cam.url, timeout=5).read().decode("utf-8")
        self.assertIn("getUserMedia", pag)
        self.assertIn("X-Sessao", pag)
        self.assertIn("document.hidden", pag)


class TestCameraWifi(unittest.TestCase):
    def test_https_e_qr(self):
        cam = CameraCelular(Path(tempfile.mkdtemp()), porta=8480, ip="127.0.0.1")
        try:
            self.assertTrue(cam.url.startswith("https://127.0.0.1:"))
            self.assertEqual(enviar(cam.url + "/quadro", ctx=SEM_VERIFICAR), 204)
            self.assertTrue(cam.read()[0])
            txt, *_ = cv2.QRCodeDetector().detectAndDecode(imagem_qr(cam.url, 500))
            self.assertEqual(txt, cam.url)
        finally:
            cam.release()

    def test_duas_copias_nao_dividem_a_porta(self):
        d = Path(tempfile.mkdtemp())
        a = CameraCelular(d, porta=8490, ip="127.0.0.1")
        b = CameraCelular(d, porta=8490, ip="127.0.0.1")
        try:
            self.assertNotEqual(a.porta, b.porta)
        finally:
            a.release()
            b.release()


class TestAdb(unittest.TestCase):
    def test_aparelho_pronto(self):
        saida = ("List of devices attached\n"
                 "R58M123ABC       device usb:1-1 product:a52qnsxx model:SM_A525M device:a52q transport_id:3\n")
        (a,) = ler_aparelhos(saida)
        self.assertEqual(a["serial"], "R58M123ABC")
        self.assertEqual(a["estado"], "device")
        self.assertEqual(a["model"], "SM_A525M")

    def test_nao_autorizado_e_vazio(self):
        self.assertEqual(ler_aparelhos("List of devices attached\nXYZ unauthorized usb:1-2 transport_id:4\n")[0]["estado"],
                         "unauthorized")
        self.assertEqual(ler_aparelhos("* daemon started successfully\nList of devices attached\n\n"), [])


if __name__ == "__main__":
    unittest.main()
