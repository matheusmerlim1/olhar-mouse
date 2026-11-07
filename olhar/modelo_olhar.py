"""Regressão: vetor do olhar (íris + pose da cabeça) → ponto na tela.

Ridge sobre características padronizadas. A forma do modelo (linear ou com termos de 2º
grau) e a força da regularização são escolhidas NA CALIBRAÇÃO de cada pessoa, pelo erro em
pontos deixados de fora (validação cruzada por ponto): com sinal fraco — rosto pequeno na
imagem, íris com poucos pixels — o modelo simples treme bem menos; com sinal bom, o de
2º grau acerta melhor os cantos.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _termos(f: np.ndarray, forma: str = "quadratico") -> np.ndarray:
    """f: (N, 4) = u, v, yaw, pitch → matriz de projeto."""
    u, v, yaw, pitch = f.T
    base = [np.ones_like(u), u, v, yaw, pitch]
    if forma == "linear":
        return np.column_stack(base)
    return np.column_stack(base + [u * u, v * v, u * v, yaw * pitch])


FORMAS = ("linear", "quadratico")
RIDGES = (0.01, 1.0, 10.0, 50.0, 200.0)


def _resolver(X: np.ndarray, y: np.ndarray, ridge: float) -> np.ndarray:
    reg = ridge * np.eye(X.shape[1])
    reg[0, 0] = 0.0  # não penaliza o termo constante
    return np.linalg.solve(X.T @ X + reg, X.T @ y)


class ModeloOlhar:
    def __init__(self):
        self.media = None
        self.desvio = None
        self.coef = None
        self.forma = "quadratico"
        self.ridge = 0.01
        self.erro_px = None       # erro nos próprios dados da calibração
        self.erro_cv_px = None    # erro em pontos deixados de fora (o que vale na prática)

    @property
    def pronto(self) -> bool:
        return self.coef is not None

    def ajustar(self, feats: np.ndarray, alvos: np.ndarray, ridge: float | None = None,
                forma: str | None = None) -> float:
        """feats (N,4), alvos (N,2) em pixels. Devolve o erro médio (px) nos próprios dados.

        Sem `forma`/`ridge`, escolhe os dois pela validação cruzada deixando um ponto de
        calibração de fora por vez (precisa de pelo menos 4 pontos diferentes).
        """
        feats = np.asarray(feats, float)
        alvos = np.asarray(alvos, float)
        self.media = feats.mean(axis=0)
        self.desvio = feats.std(axis=0) + 1e-9
        z = (feats - self.media) / self.desvio
        if forma is None or ridge is None:
            forma, ridge, self.erro_cv_px = self._escolher(z, alvos, forma, ridge)
        self.forma, self.ridge = forma, ridge
        X = _termos(z, forma)
        self.coef = _resolver(X, alvos, ridge)
        self.erro_px = float(np.linalg.norm(X @ self.coef - alvos, axis=1).mean())
        return self.erro_px

    @staticmethod
    def _escolher(z, alvos, forma=None, ridge=None):
        pontos, grupo = np.unique(alvos, axis=0, return_inverse=True)
        grupo = np.asarray(grupo).ravel()
        formas = (forma,) if forma else FORMAS
        ridges = (ridge,) if ridge is not None else RIDGES
        if len(pontos) < 4:
            return formas[-1], ridges[0], None
        melhor = None
        for fm in formas:
            X = _termos(z, fm)
            for r in ridges:
                erros = []
                for g in range(len(pontos)):
                    treino, teste = grupo != g, grupo == g
                    c = _resolver(X[treino], alvos[treino], r)
                    erros.append(np.linalg.norm(X[teste] @ c - alvos[teste], axis=1))
                e = float(np.concatenate(erros).mean())
                if melhor is None or e < melhor[2]:
                    melhor = (fm, r, e)
        return melhor

    # além disso (em desvios-padrão da calibração) o olhar está fora da área calibrada:
    # cabeça virada, olhando para o teclado ou para fora da tela
    LIMITE_FORA = 3.5

    def afastamento(self, f: np.ndarray) -> float:
        """Quanto o vetor está fora do que foi visto na calibração (maior |z|)."""
        z = (np.asarray(f, float) - self.media) / self.desvio
        return float(np.abs(z).max())

    def fora(self, f: np.ndarray) -> bool:
        return self.afastamento(f) > self.LIMITE_FORA

    def prever(self, f: np.ndarray) -> np.ndarray:
        z = (np.asarray(f, float).reshape(1, -1) - self.media) / self.desvio
        # o polinômio de 2º grau explode fora da faixa calibrada (o cursor ia parar a
        # milhares de pixels): limita cada característica a ±3 desvios
        z = np.clip(z, -3.0, 3.0)
        return (_termos(z, self.forma) @ self.coef)[0]

    def para_dict(self) -> dict:
        return {"media": self.media.tolist(), "desvio": self.desvio.tolist(),
                "coef": self.coef.tolist(), "forma": self.forma, "ridge": self.ridge,
                "erro_px": self.erro_px, "erro_cv_px": self.erro_cv_px}

    @classmethod
    def de_dict(cls, d: dict) -> "ModeloOlhar":
        m = cls()
        m.media = np.array(d["media"])
        m.desvio = np.array(d["desvio"])
        m.coef = np.array(d["coef"])
        m.forma = d.get("forma", "quadratico")   # calibrações antigas eram de 2º grau
        m.ridge = d.get("ridge", 0.01)
        m.erro_px = d.get("erro_px")
        m.erro_cv_px = d.get("erro_cv_px")
        return m


def salvar(caminho: Path, modelo: ModeloOlhar, palpebra, extra: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"olhar": modelo.para_dict(), "palpebra": vars(palpebra), **extra}
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def carregar(caminho: Path):
    from .gestos import CalibPalpebra
    d = json.loads(caminho.read_text(encoding="utf-8"))
    return ModeloOlhar.de_dict(d["olhar"]), CalibPalpebra(**d["palpebra"]), d
