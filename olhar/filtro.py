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
