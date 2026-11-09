"""Mover o cursor e clicar. No Windows usa a API nativa (ctypes); fora dele, pyautogui."""
from __future__ import annotations

import sys
import time

if sys.platform == "win32":
    import ctypes

    _u32 = ctypes.windll.user32
    try:  # coordenadas em pixels reais mesmo com escala de tela 125 %/150 %
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _u32.SetProcessDPIAware()
        except Exception:
            pass

    _EVENTOS = {"esquerdo": (0x0002, 0x0004), "direito": (0x0008, 0x0010)}

    def tamanho_tela() -> tuple[int, int]:
        """Largura e altura da área que cobre TODAS as telas."""
        return _u32.GetSystemMetrics(78), _u32.GetSystemMetrics(79)

    def origem() -> tuple[int, int]:
        """Canto superior esquerdo dessa área (pode ser negativo)."""
        return _u32.GetSystemMetrics(76), _u32.GetSystemMetrics(77)

    class _Ret(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    def monitores_relativos() -> list[tuple[int, int, int, int]]:
        """(x, y, largura, altura) de cada tela, relativos à origem; a principal primeiro."""
        ox, oy = origem()
        achados = []

        def anotar(_h, _d, r, _x):
            achados.append((r.contents.l, r.contents.t, r.contents.r - r.contents.l, r.contents.b - r.contents.t))
            return 1

        tipo = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_Ret), ctypes.c_void_p)
        _u32.EnumDisplayMonitors(None, None, tipo(anotar), None)
        achados.sort(key=lambda m: not (m[0] == 0 and m[1] == 0))   # a principal fica em (0, 0)
        return [(x - ox, y - oy, w, h) for x, y, w, h in achados]

    def mover(x: int, y: int) -> None:
        _u32.SetCursorPos(int(x), int(y))

    class _Ponto(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def posicao() -> tuple[int, int]:
        """Onde o cursor está agora (para perceber o mouse físico)."""
        p = _Ponto()
        _u32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def clicar(botao: str, x: int | None = None, y: int | None = None) -> None:
        if x is not None:
            mover(x, y)
        desce, sobe = _EVENTOS[botao]
        _u32.mouse_event(desce, 0, 0, 0, 0)
        _u32.mouse_event(sobe, 0, 0, 0, 0)

    def tecla_apertada(vk: int) -> bool:
        """Lê o teclado mesmo com outra janela em foco (para as teclas F9/F10)."""
        return bool(_u32.GetAsyncKeyState(vk) & 0x8000)

else:  # pragma: no cover - só para rodar em Linux/macOS
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    def tamanho_tela() -> tuple[int, int]:
        return pyautogui.size()

    def origem() -> tuple[int, int]:
        return 0, 0

    def monitores_relativos() -> list[tuple[int, int, int, int]]:
        w, h = pyautogui.size()
        return [(0, 0, w, h)]

    def mover(x: int, y: int) -> None:
        pyautogui.moveTo(int(x), int(y))

    def posicao() -> tuple[int, int]:
        return tuple(pyautogui.position())

    def clicar(botao: str, x: int | None = None, y: int | None = None) -> None:
        pyautogui.click(x=x, y=y, button="left" if botao == "esquerdo" else "right")

    def tecla_apertada(vk: int) -> bool:
        return False

VK_ESC, VK_F8, VK_F9, VK_F10 = 0x1B, 0x77, 0x78, 0x79


def prender(x: int, y: int, monitores) -> tuple[int, int]:
    """Leva o ponto para a tela mais próxima (entre telas de tamanhos diferentes há área morta)."""
    melhor, dist = (x, y), None
    for mx, my, mw, mh in monitores:
        px, py = min(max(x, mx), mx + mw - 1), min(max(y, my), my + mh - 1)
        d = (px - x) ** 2 + (py - y) ** 2
        if dist is None or d < dist:
            melhor, dist = (px, py), d
    return melhor


def botao_fisico_apertado() -> bool:
    """Botão do mouse de verdade pressionado (arrastando algo)."""
    return tecla_apertada(0x01) or tecla_apertada(0x02)


def clicar_em(botao: str, x: int, y: int) -> None:
    """Clica em (x, y) e devolve o cursor para onde a pessoa o deixou."""
    original = posicao()
    mover(x, y)
    time.sleep(0.02)      # o programa alvo precisa ver o cursor chegar antes do clique
    clicar(botao)
    time.sleep(0.03)
    mover(*original)
