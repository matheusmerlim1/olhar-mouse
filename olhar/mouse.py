"""Mover o cursor e clicar. No Windows usa a API nativa (ctypes); fora dele, pyautogui."""
from __future__ import annotations

import sys

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
        return _u32.GetSystemMetrics(0), _u32.GetSystemMetrics(1)

    def mover(x: int, y: int) -> None:
        _u32.SetCursorPos(int(x), int(y))

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

    def mover(x: int, y: int) -> None:
        pyautogui.moveTo(int(x), int(y))

    def clicar(botao: str, x: int | None = None, y: int | None = None) -> None:
        pyautogui.click(x=x, y=y, button="left" if botao == "esquerdo" else "right")

    def tecla_apertada(vk: int) -> bool:
        return False

VK_F9, VK_F10 = 0x78, 0x79
