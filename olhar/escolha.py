"""Tela inicial: escolher a câmera entre as três opções.

1. Câmera do computador (webcam ou outra câmera que o Windows enxergue)
2. Celular pelo QR code (Wi-Fi)
3. Celular pelo cabo USB (Android)

Clique no botão ou tecle 1, 2 ou 3. Enter repete a última escolha; Esc sai.
"""
from __future__ import annotations

import cv2
import numpy as np

JANELA = "Olhar-mouse - escolha a camera"
# câmeras que existem no Windows mas não filmam o rosto de ninguém
VIRTUAIS = ("obs virtual", "virtual camera", "snap camera", "xsplit", "manycam", "nvidia broadcast")


def eh_virtual(nome: str) -> bool:
    n = nome.lower()
    return any(v in n for v in VIRTUAIS)


def camera_do_computador(nomes: list[str], atual) -> str | int | None:
    """Que câmera usar na opção 1: a atual se for do computador, senão a primeira não virtual."""
    if isinstance(atual, str) and atual in nomes:
        return atual
    if isinstance(atual, int) and 0 <= atual < len(nomes):
        return nomes[atual]
    reais = [n for n in nomes if not eh_virtual(n)]
    if reais:
        return reais[0]
    return nomes[0] if nomes else None


def opcao_de(camera) -> int:
    c = str(camera).strip().lower()
    return 3 if c == "usb" else 2 if c == "celular" else 1


def _sem_acento(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def escolher_camera(nomes: list[str], atual):
    """Mostra a tela e devolve o valor para cfg["camera"], ou None se a pessoa saiu (Esc)."""
    from .calibracao import Cancelado

    w, h = 960, 560
    pc = camera_do_computador(nomes, atual)
    if pc is None:
        sub_pc, aviso_pc = "nenhuma camera encontrada no Windows", True
    elif eh_virtual(pc) and all(eh_virtual(n) for n in nomes):
        sub_pc, aviso_pc = f"so ha '{pc}' (camera virtual, nao filma o rosto)", True
    else:
        sub_pc, aviso_pc = pc, False
    opcoes = [
        ("1", "Camera do computador", _sem_acento(sub_pc), aviso_pc),
        ("2", "Celular pelo QR code", "Wi-Fi: o celular le o QR e abre a pagina", False),
        ("3", "Celular pelo cabo USB", "Android: sem Wi-Fi e sem internet", False),
    ]
    marcada = opcao_de(atual)
    botoes = [(40, 120 + i * 130, w - 40, 120 + i * 130 + 110) for i in range(3)]
    escolha = {"valor": None, "sobre": None}

    def ao_mouse(evento, x, y, *_):
        dentro = next((i for i, (x0, y0, x1, y1) in enumerate(botoes) if x0 <= x <= x1 and y0 <= y <= y1), None)
        escolha["sobre"] = dentro
        if evento == cv2.EVENT_LBUTTONUP and dentro is not None:
            escolha["valor"] = dentro + 1

    cv2.namedWindow(JANELA, cv2.WINDOW_AUTOSIZE)
    cv2.setWindowProperty(JANELA, cv2.WND_PROP_TOPMOST, 1)
    cv2.setMouseCallback(JANELA, ao_mouse)
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    try:
        while escolha["valor"] is None:
            img = np.full((h, w, 3), 24, np.uint8)
            cv2.putText(img, "Qual camera usar?", (40, 70), fonte, 1.1, (240, 240, 240), 2, cv2.LINE_AA)
            for i, ((tecla, titulo, sub, aviso), (x0, y0, x1, y1)) in enumerate(zip(opcoes, botoes)):
                destaque = escolha["sobre"] == i
                fundo = (70, 60, 40) if destaque else (45, 45, 45)
                cv2.rectangle(img, (x0, y0), (x1, y1), fundo, -1)
                borda = (255, 170, 60) if i + 1 == marcada else (90, 90, 90)
                cv2.rectangle(img, (x0, y0), (x1, y1), borda, 2)
                cv2.circle(img, (x0 + 55, y0 + 55), 30, (255, 170, 60), -1, cv2.LINE_AA)
                cv2.putText(img, tecla, (x0 + 44, y0 + 68), fonte, 1.1, (20, 20, 20), 3, cv2.LINE_AA)
                cv2.putText(img, titulo, (x0 + 110, y0 + 48), fonte, 0.95, (245, 245, 245), 2, cv2.LINE_AA)
                cv2.putText(img, sub, (x0 + 110, y0 + 85), fonte, 0.6,
                            (90, 160, 255) if aviso else (190, 190, 190), 1, cv2.LINE_AA)
            cv2.putText(img, "Clique ou tecle 1, 2 ou 3.  Enter: a ultima usada (destacada).  Esc: sair",
                        (40, h - 25), fonte, 0.55, (150, 150, 150), 1, cv2.LINE_AA)
            cv2.imshow(JANELA, img)
            k = cv2.waitKey(30) & 0xFF
            if k in (ord("1"), ord("2"), ord("3")):
                escolha["valor"] = k - ord("0")
            elif k in (13, 10):
                escolha["valor"] = marcada
            elif k == 27 or cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                raise Cancelado
    finally:
        try:
            cv2.destroyWindow(JANELA)
        except cv2.error:
            pass
    v = escolha["valor"]
    if v == 2:
        return "celular"
    if v == 3:
        return "usb"
    return pc if pc is not None else 0
