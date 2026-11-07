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

    - movendo: acompanha o alvo; quando as amostras dos últimos `janela` s se juntam
      (dispersão média menor que o raio), PARA — no centro das amostras dos últimos
      `janela_parada` s (mais amostras = ponto mais certo, sem ficar deslizando depois);
    - parado: não mexe no cursor; só volta a seguir quando o centro recente se afasta mais
      que o raio.
    O raio se adapta: vira 2,5× o tremido medido, se isso for maior (até RAIO_MAX).
    ceder(): o mouse físico foi usado; não puxa o cursor de volta até um olhar novo.
    raio = 0 desliga (o cursor segue o alvo sempre).
    """

    RAIO_MAX = 250.0

    def __init__(self, raio: float = 40, janela: float = 0.25, janela_parada: float = 0.6,
                 adaptativo: bool = True):
        from collections import deque
        self.raio, self.janela, self.janela_parada, self.adaptativo = raio, janela, janela_parada, adaptativo
        self._amostras = deque()
        self.ruido = 0.0          # tremido medido (px, média móvel)
        self.reiniciar()

    def reiniciar(self):
        self.pos = None
        self.movendo = True       # começa seguindo: só para quando a janela encher
        self.cedido = False
        self._ref = None
        self._amostras.clear()

    def ceder(self):
        """O mouse físico foi usado: o olhar não puxa o cursor de volta. Só retoma quando
        o ponto de fixação se afasta bem de onde estava (a pessoa olhou para outro lugar)."""
        self.cedido = True
        self._ref = None

    @property
    def raio_efetivo(self) -> float:
        if not self.adaptativo or self.raio <= 0:
            return self.raio
        return max(self.raio, min(self.RAIO_MAX, 2.5 * self.ruido))

    @property
    def raio_retomar(self) -> float:
        return max(150.0, 3 * self.raio_efetivo)

    def _centro(self, t: float, janela: float):
        sel = [a for a in self._amostras if t - a[0] <= janela]
        n = len(sel)
        cx = sum(a[1] for a in sel) / n
        cy = sum(a[2] for a in sel) / n
        rms = math.sqrt(sum((a[1] - cx) ** 2 + (a[2] - cy) ** 2 for a in sel) / n)
        return cx, cy, rms, sel

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float] | None:
        am = self._amostras
        am.append((t, x, y))
        while am and t - am[0][0] > max(self.janela, self.janela_parada):
            am.popleft()
        cx, cy, rms, sel = self._centro(t, self.janela)
        cheia = t - sel[0][0] >= self.janela * 0.8

        if self.cedido:
            if self._ref is None:
                self._ref = (cx, cy)
            if math.hypot(cx - self._ref[0], cy - self._ref[1]) <= self.raio_retomar:
                return None          # devolve None: não mexer no cursor
            self.cedido, self.movendo = False, True
        if self.raio <= 0:
            self.pos = (x, y)
            return self.pos

        if cheia:  # tremido medido o tempo todo (pesa mais com o cursor parado)
            peso = 0.05 if not self.movendo else 0.02
            self.ruido = (1 - peso) * self.ruido + peso * rms if self.ruido else rms
        raio = self.raio_efetivo
        if not self.movendo:
            if math.hypot(cx - self.pos[0], cy - self.pos[1]) <= raio:
                return self.pos
            self.movendo = True

        # movendo: segue o alvo; para quando as amostras recentes se juntam
        if cheia and rms <= raio * 0.6:
            self.movendo = False
            px, py, _, _ = self._centro(t, self.janela_parada)
            # só usa a janela longa se ela também é da mesma fixação (perto do centro curto)
            self.pos = (px, py) if math.hypot(px - cx, py - cy) <= raio * 0.5 else (cx, cy)
        else:
            self.pos = (x, y)
        return self.pos


# predefinições do menu "Estabilidade do cursor"
ESTABILIDADE = {
    "baixa": {"min_cutoff": 0.6, "beta": 0.004, "raio": 0, "mediana": 1},    # mais rápido
    "media": {"min_cutoff": 0.3, "beta": 0.003, "raio": 40, "mediana": 5},
    "alta": {"min_cutoff": 0.15, "beta": 0.002, "raio": 70, "mediana": 7},   # mais firme
}
