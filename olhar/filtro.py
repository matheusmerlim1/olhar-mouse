"""Filtro One Euro (Casiez, Roussel e Vogel, CHI 2012).

Suaviza muito quando o ponto está parado (tira o tremor da íris — e o dos
reflexos dos óculos) e pouco quando ele se move rápido (não deixa o cursor
"atrasado"). `min_cutoff` menor = mais estável; `beta` maior = menos atraso.
"""
from __future__ import annotations

import math


class _Passa:
    def __init__(self):
        self.y = None

    def __call__(self, x: float, alfa: float) -> float:
        self.y = x if self.y is None else alfa * x + (1 - alfa) * self.y
        return self.y


class OneEuro:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self._x, self._dx = _Passa(), _Passa()
        self._t = None

    @staticmethod
    def _alfa(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._t is None:
            self._t = t
            self._dx(0.0, 1.0)
            return self._x(x, 1.0)
        dt = max(t - self._t, 1e-3)
        self._t = t
        dx = (x - self._x.y) / dt
        edx = self._dx(dx, self._alfa(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self._x(x, self._alfa(cutoff, dt))

    def reiniciar(self):
        self._x, self._dx, self._t = _Passa(), _Passa(), None


class OneEuro2D:
    def __init__(self, **kw):
        self.fx, self.fy = OneEuro(**kw), OneEuro(**kw)

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        return self.fx(x, t), self.fy(y, t)

    def reiniciar(self):
        self.fx.reiniciar()
        self.fy.reiniciar()


class MedianaVetor:
    """Mediana, coordenada a coordenada, dos últimos N vetores do olhar.

    Tira os picos de um quadro só (pálpebra tremendo, reflexo, imagem borrada) antes da
    regressão; a mediana não "puxa" o ponto como a média faria.
    """

    def __init__(self, n: int = 5):
        from collections import deque
        self.hist = deque(maxlen=max(1, n))

    def __call__(self, v):
        import numpy as np
        self.hist.append(np.asarray(v, float))
        return np.median(np.stack(self.hist), axis=0)

    def reiniciar(self):
        self.hist.clear()


class Estabilizador:
    """Zona de repouso por fixação: olhando para um ponto, o cursor fica parado.

    Trabalha com o CENTRO das amostras dos últimos `janela` segundos (e não com cada
    quadro, porque o ruído da íris sozinho já parece movimento):
    - parado: só sai do lugar quando esse centro se afasta mais que `raio` px;
    - movendo: acompanha o alvo e volta a parar quando as amostras recentes cabem num
      círculo pequeno (fixação) — e para no centro delas.
    raio = 0 desliga (o cursor segue o alvo sempre).
    """

    def __init__(self, raio: float = 40, janela: float = 0.25):
        from collections import deque
        self.raio, self.janela = raio, janela
        self._amostras = deque()
        self.reiniciar()

    def reiniciar(self):
        self.pos = None
        self.movendo = True      # começa seguindo: só para quando a janela encher
        self._amostras.clear()

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self.raio <= 0:
            self.pos = (x, y)
            return self.pos
        am = self._amostras
        am.append((t, x, y))
        while am and t - am[0][0] > self.janela:
            am.popleft()
        cx = sum(a[1] for a in am) / len(am)
        cy = sum(a[2] for a in am) / len(am)
        if not self.movendo:
            if math.hypot(cx - self.pos[0], cy - self.pos[1]) <= self.raio:
                return self.pos
            self.movendo = True
        # movendo: segue o alvo; parou de mexer quando a janela inteira cabe no raio
        cheia = t - am[0][0] >= self.janela * 0.8
        dispersao = max(math.hypot(a[1] - cx, a[2] - cy) for a in am)
        if cheia and dispersao <= self.raio * 0.8:
            self.movendo = False
            self.pos = (cx, cy)
        else:
            self.pos = (x, y)
        return self.pos


# predefinições do menu "Estabilidade do cursor"
ESTABILIDADE = {
    "baixa": {"min_cutoff": 0.6, "beta": 0.004, "raio": 0, "mediana": 1},    # mais rápido
    "media": {"min_cutoff": 0.3, "beta": 0.003, "raio": 40, "mediana": 5},
    "alta": {"min_cutoff": 0.15, "beta": 0.002, "raio": 70, "mediana": 7},   # mais firme
}
