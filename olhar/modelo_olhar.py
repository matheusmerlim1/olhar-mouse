"""Regressão: vetor do olhar (íris + pose da cabeça) → ponto na tela.

Polinômio de 2º grau nos termos da íris + linear na pose da cabeça, com
regularização (ridge) sobre características padronizadas. Com 13 pontos de
calibração isso dá folga suficiente sem decorar o ruído.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _termos(f: np.ndarray) -> np.ndarray:
    """f: (N, 4) = u, v, yaw, pitch → matriz de projeto (N, 9)."""
    u, v, yaw, pitch = f.T
    return np.column_stack([np.ones_like(u), u, v, yaw, pitch, u * u, v * v, u * v, yaw * pitch])


class ModeloOlhar:
    def __init__(self):
        self.media = None
        self.desvio = None
        self.coef = None  # (9, 2)
        self.erro_px = None

    @property
    def pronto(self) -> bool:
        return self.coef is not None

    def ajustar(self, feats: np.ndarray, alvos: np.ndarray, ridge: float = 1e-2) -> float:
        """feats (N,4), alvos (N,2) em pixels. Devolve o erro médio (px) nos próprios dados."""
        feats = np.asarray(feats, float)
        alvos = np.asarray(alvos, float)
        self.media = feats.mean(axis=0)
        self.desvio = feats.std(axis=0) + 1e-9
        X = _termos((feats - self.media) / self.desvio)
        reg = ridge * np.eye(X.shape[1])
        reg[0, 0] = 0.0  # não penaliza o termo constante
        self.coef = np.linalg.solve(X.T @ X + reg, X.T @ alvos)
        self.erro_px = float(np.linalg.norm(X @ self.coef - alvos, axis=1).mean())
        return self.erro_px

    def prever(self, f: np.ndarray) -> np.ndarray:
        z = (np.asarray(f, float).reshape(1, -1) - self.media) / self.desvio
        return (_termos(z) @ self.coef)[0]

    def para_dict(self) -> dict:
        return {"media": self.media.tolist(), "desvio": self.desvio.tolist(),
                "coef": self.coef.tolist(), "erro_px": self.erro_px}

    @classmethod
    def de_dict(cls, d: dict) -> "ModeloOlhar":
        m = cls()
        m.media = np.array(d["media"])
        m.desvio = np.array(d["desvio"])
        m.coef = np.array(d["coef"])
        m.erro_px = d.get("erro_px")
        return m


def salvar(caminho: Path, modelo: ModeloOlhar, palpebra, extra: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"olhar": modelo.para_dict(), "palpebra": vars(palpebra), **extra}
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def carregar(caminho: Path):
    from .gestos import CalibPalpebra
    d = json.loads(caminho.read_text(encoding="utf-8"))
    return ModeloOlhar.de_dict(d["olhar"]), CalibPalpebra(**d["palpebra"]), d
