"""Segundo ponteiro: um anel na tela que segue o olhar sem tocar no cursor do Windows.

O Windows só tem um cursor, então olhar e mouse sempre disputariam o mesmo. O anel é uma
janelinha transparente, sempre por cima, que não recebe clique nem foco. O cursor só sai do
lugar por uma fração de segundo na hora do clique por piscada (mouse.clicar_em).

O tkinter roda numa thread só dele; as outras threads só escrevem nos atributos.
"""
from __future__ import annotations

import gc
import threading
import time

RAIO = 24
LADO = RAIO * 2 + 8
CHAVE = "#ff00fe"          # cor tratada como transparente
COR = "#22d3ee"
COR_CLIQUE = "#facc15"


class PonteiroOlhar:
    def __init__(self):
        self._alvo = None
        self._clique_ate = 0.0
        self._fim = False
        self.falhou = False
        self.hwnd = None
        self._pronto = threading.Event()
        self._thread = threading.Thread(target=self._rodar, daemon=True, name="ponteiro")
        self._thread.start()
        self._pronto.wait(5)

    # ----- chamados pelo laço principal
    def mostrar(self, x: int, y: int) -> None:
        self._alvo = (x, y)

    def esconder(self) -> None:
        self._alvo = None

    def marcar_clique(self) -> None:
        self._clique_ate = time.monotonic() + 0.3

    def fechar(self) -> None:
        self._fim = True
        self._thread.join(2)

    # ----- thread do tkinter
    def _rodar(self) -> None:
        try:
            self._laco()
        except Exception as e:
            self.falhou = True
            print(f"ponteiro do olhar: {e!r}")
        finally:
            self._pronto.set()

    def _laco(self) -> None:
        import ctypes
        import tkinter as tk
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32")     # instância própria: argtypes não afetam mouse.py
        u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetAncestor.restype = wintypes.HWND
        u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]

        raiz = tk.Tk()
        raiz.overrideredirect(True)
        raiz.geometry(f"{LADO}x{LADO}+0+0")
        raiz.configure(bg=CHAVE)
        raiz.attributes("-topmost", True)
        raiz.attributes("-transparentcolor", CHAVE)
        tela = tk.Canvas(raiz, width=LADO, height=LADO, bg=CHAVE, highlightthickness=0)
        tela.pack()
        c, r = LADO // 2, RAIO
        tela.create_oval(c - r, c - r, c + r, c + r, outline="#0f172a", width=6)
        anel = tela.create_oval(c - r, c - r, c + r, c + r, outline=COR, width=3)
        tela.create_oval(c - 3, c - 3, c + 3, c + 3, fill="#0f172a", outline=COR)
        raiz.update()

        hwnd = u32.GetAncestor(tela.winfo_id(), 2)     # GA_ROOT
        GWL_EXSTYLE = -20
        # LAYERED | TRANSPARENT (clique atravessa) | NOACTIVATE | TOOLWINDOW (fora do Alt+Tab)
        estilo = u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) | 0x80000 | 0x20 | 0x08000000 | 0x80
        u32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, estilo)
        u32.ShowWindow(hwnd, 0)
        self.hwnd = hwnd
        self._pronto.set()

        visivel, px, py, cor_atual = False, None, None, COR

        def tique():
            nonlocal visivel, px, py, cor_atual
            if self._fim:
                raiz.destroy()
                return
            alvo = self._alvo
            if alvo is None:
                if visivel:
                    u32.ShowWindow(hwnd, 0)
                    visivel = False
                    px = None
            else:
                if px is None:
                    px, py = float(alvo[0]), float(alvo[1])
                else:                       # desliza: o anel não pula de um ponto a outro
                    px += (alvo[0] - px) * 0.35
                    py += (alvo[1] - py) * 0.35
                # HWND_TOPMOST | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                u32.SetWindowPos(hwnd, wintypes.HWND(-1), int(px) - c, int(py) - c, 0, 0, 0x1 | 0x10 | 0x40)
                visivel = True
            cor = COR_CLIQUE if time.monotonic() < self._clique_ate else COR
            if cor != cor_atual:
                tela.itemconfig(anel, outline=cor)
                cor_atual = cor
            raiz.after(15, tique)

        tique()
        raiz.mainloop()
        # o interpretador Tcl tem de ser liberado NESTA thread; se o coletor de lixo o
        # liberar em outra, o processo morre com "Tcl_AsyncDelete"
        tique = raiz = tela = None
        gc.collect()
