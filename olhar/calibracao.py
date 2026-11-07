"""Calibração em tela cheia.

1. Pálpebras: mede o EAR de olhos abertos e fechados DESTE usuário (com ou sem
   óculos). Com os olhos fechados a pessoa não vê a tela, então o fim da etapa
   é avisado com um bipe.
2. Olhar: mostra 13 pontos; para cada um a pessoa olha, o ponto encolhe e o
   programa junta amostras da íris e da pose da cabeça.

Textos sem acento porque o desenho de texto do OpenCV só tem ASCII.
"""
from __future__ import annotations

import sys
import time

import cv2
import numpy as np

from .gestos import CalibPalpebra
from .modelo_olhar import ModeloOlhar
from .olhos import vetor_olhar

JANELA = "Calibracao - olhar-mouse"


def bipe(freq: int = 880, ms: int = 180) -> None:
    if sys.platform == "win32":
        import winsound
        winsound.Beep(freq, ms)
    else:
        print("\a", end="", flush=True)


def pontos_calibracao(w: int, h: int, n: int = 13) -> list[tuple[int, int]]:
    """Grade 3×3 nas bordas (8 % de margem) + 4 pontos intermediários."""
    mx, my = 0.08, 0.08
    xs = [mx, 0.5, 1 - mx]
    ys = [my, 0.5, 1 - my]
    pts = [(x, y) for y in ys for x in xs]
    if n >= 13:
        pts += [(0.29, 0.29), (0.71, 0.29), (0.29, 0.71), (0.71, 0.71)]
    # ordem que evita saltos grandes: começa no centro
    pts.sort(key=lambda p: (abs(p[0] - 0.5) + abs(p[1] - 0.5)))
    return [(int(x * w), int(y * h)) for x, y in pts]


class _Tela:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(JANELA, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def desenhar(self, texto: str = "", ponto=None, raio: int = 0, sub: str = "") -> int:
        img = np.full((self.h, self.w, 3), 24, np.uint8)
        if texto:
            self._centralizado(img, texto, self.h // 2 - 60 if ponto else self.h // 2, 1.0)
        if sub:
            self._centralizado(img, sub, self.h - 60, 0.7, (170, 170, 170))
        if ponto is not None:
            cv2.circle(img, ponto, max(raio, 4), (60, 200, 255), -1, cv2.LINE_AA)
            cv2.circle(img, ponto, 3, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.imshow(JANELA, img)
        return cv2.waitKey(1) & 0xFF

    def _centralizado(self, img, texto, y, escala, cor=(235, 235, 235)):
        fonte = cv2.FONT_HERSHEY_SIMPLEX
        (tw, _), _ = cv2.getTextSize(texto, fonte, escala, 2)
        cv2.putText(img, texto, ((self.w - tw) // 2, y), fonte, escala, cor, 2, cv2.LINE_AA)

    def fechar(self):
        cv2.destroyWindow(JANELA)


class Cancelado(Exception):
    pass


def _coletar(cap, detector, tela: _Tela, dur: float, texto: str, sub: str = "",
             ponto=None, raio_ini: int = 0, encolher: bool = False):
    """Lê quadros por `dur` segundos e devolve a lista de medidas com rosto."""
    medidas = []
    t0 = time.monotonic()
    while (t := time.monotonic() - t0) < dur:
        ok, frame = cap.read()
        if not ok:
            continue
        m = detector.processar(frame)
        raio = int(raio_ini * (1 - t / dur)) + 6 if encolher else raio_ini
        aviso = sub if m is not None else "Rosto nao encontrado - fique de frente para a camera"
        if tela.desenhar(texto, ponto, raio, aviso) in (27, ord("q")):
            raise Cancelado
        if m is not None:
            medidas.append(m)
    return medidas


def calibrar(cap, detector, tela_wh: tuple[int, int], usar_olho: str = "ambos",
             n_pontos: int = 13) -> tuple[ModeloOlhar, CalibPalpebra]:
    w, h = tela_wh
    tela = _Tela(w, h)
    try:
        centro = (w // 2, h // 2)
        _coletar(cap, detector, tela, 3.0, "Calibracao: sente como vai usar e olhe para o ponto",
                 "Esc cancela", centro, 14)

        abertos = _coletar(cap, detector, tela, 2.0, "Olhos ABERTOS, olhando o ponto", "", centro, 14)
        txt = "Agora FECHE os olhos e so abra quando ouvir o bipe"
        _coletar(cap, detector, tela, 1.5, txt, "", centro, 14)        # tempo para fechar
        fechados = _coletar(cap, detector, tela, 2.0, txt, "", centro, 14)
        bipe(990)
        palp = _calib_palpebra(abertos, fechados)

        alvos, feats = [], []
        for i, p in enumerate(pontos_calibracao(w, h, n_pontos), 1):
            txt = f"Siga o ponto com o olhar ({i}/{n_pontos})"
            _coletar(cap, detector, tela, 0.9, txt, "", p, 30, encolher=True)  # olho chegando
            ms = _coletar(cap, detector, tela, 1.0, txt, "", p, 8)
            for m in ms:
                if palp.fechamento(m.ear_e, "esq") > 0.5 or palp.fechamento(m.ear_d, "dir") > 0.5:
                    continue  # piscou durante a coleta
                feats.append(vetor_olhar(m, usar_olho))
                alvos.append(p)
        if len(feats) < 4 * n_pontos:
            raise RuntimeError("Poucas amostras com o rosto visível. Melhore a luz e tente de novo.")
        modelo = ModeloOlhar()
        erro = modelo.ajustar(np.array(feats), np.array(alvos, float))
        tela.desenhar(f"Pronto! Erro medio: {erro:.0f} px", None, 0, "comecando...")
        cv2.waitKey(900)
        return modelo, palp
    finally:
        tela.fechar()


def _calib_palpebra(abertos, fechados) -> CalibPalpebra:
    if len(abertos) < 10 or len(fechados) < 10:
        raise RuntimeError("Não vi o rosto o bastante para medir as pálpebras. Melhore a luz e tente de novo.")
    ae = float(np.median([m.ear_e for m in abertos]))
    ad = float(np.median([m.ear_d for m in abertos]))
    fe = float(np.median([m.ear_e for m in fechados]))
    fd = float(np.median([m.ear_d for m in fechados]))
    # se a pessoa não fechou de verdade (ou os óculos atrapalharam muito), a
    # diferença fica pequena: usa uma faixa mínima proporcional ao aberto
    fe = min(fe, ae * 0.6)
    fd = min(fd, ad * 0.6)
    return CalibPalpebra(aberto_e=ae, fechado_e=fe, aberto_d=ad, fechado_d=fd)
