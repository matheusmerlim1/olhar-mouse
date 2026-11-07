"""Câmera (do PC ou do celular) + detector de rosto do MediaPipe."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from .olhos import Medida, medir


def abrir_camera(fonte, largura: int = 640, altura: int = 480) -> cv2.VideoCapture:
    """fonte: número da webcam (0, 1…) ou URL do celular.

    Celular: apps como "IP Webcam" (Android) dão um endereço tipo
    http://192.168.0.10:8080/video; o DroidCam cria uma webcam virtual (use o
    número dela, geralmente 1).
    """
    if isinstance(fonte, str) and fonte.strip().isdigit():
        fonte = int(fonte)
    if isinstance(fonte, int):
        cap = cv2.VideoCapture(fonte, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(fonte)
        if not cap.isOpened():
            cap = cv2.VideoCapture(fonte)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
        cap.set(cv2.CAP_PROP_FPS, 30)
    else:
        cap = cv2.VideoCapture(fonte)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # pega sempre o quadro mais novo
    if not cap.isOpened():
        raise RuntimeError(f"Não consegui abrir a câmera {fonte!r}. Veja o campo \"camera\" do config.json.")
    return cap


class RealceOculos:
    """Equaliza o contraste local (CLAHE) no canal de luminância.

    Ajuda quando a lente dos óculos escurece/clareia a região dos olhos ou
    quando o ambiente está com pouca luz. Não remove reflexo forte — para isso
    a dica é inclinar um pouco a armação ou mudar a luz de lugar.
    """

    def __init__(self):
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def __call__(self, bgr: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = self._clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


class Detector:
    def __init__(self, modelo: Path, realce: bool = False):
        # lê o modelo como bytes: o MediaPipe falha com acento no caminho
        # ("Informação") quando recebe o caminho do arquivo no Windows
        opcoes = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=Path(modelo).read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._lm = vision.FaceLandmarker.create_from_options(opcoes)
        self._realce = RealceOculos() if realce else None
        self._t0 = time.monotonic()
        self._ult_ts = -1

    def processar(self, bgr: np.ndarray) -> Medida | None:
        if self._realce is not None:
            bgr = self._realce(bgr)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        ts = int((time.monotonic() - self._t0) * 1000)
        ts = max(ts, self._ult_ts + 1)  # o MediaPipe exige tempo sempre crescente
        self._ult_ts = ts
        res = self._lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        if not res.face_landmarks:
            return None
        h, w = bgr.shape[:2]
        pts = np.array([(p.x * w, p.y * h) for p in res.face_landmarks[0]], dtype=float)
        if len(pts) < 478:
            return None  # modelo sem íris
        return medir(pts)

    def fechar(self):
        self._lm.close()
