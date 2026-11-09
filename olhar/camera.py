"""Câmera (do PC ou do celular) + detector de rosto do MediaPipe."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from .olhos import Medida, medir


def listar_cameras() -> list[str]:
    """Nomes das câmeras do Windows, na mesma ordem dos números do OpenCV (DirectShow).

    Inclui celular ligado como webcam USB (modo "Webcam" do Android 14+),
    DroidCam etc. (câmeras virtuais, como a do OBS, são filtradas na escolha).
    """
    if sys.platform != "win32":
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def abrir_camera(fonte, largura: int = 1280, altura: int = 720) -> cv2.VideoCapture:
    """fonte: número da webcam (0, 1…), nome da câmera ou URL de câmera IP.

    Celular: apps como "IP Webcam" (Android) dão um endereço tipo
    http://192.168.0.10:8080/video; o modo "Webcam" do Android 14+ (pelo cabo
    USB) e o DroidCam aparecem como câmeras com nome.
    """
    if isinstance(fonte, str) and fonte.strip().isdigit():
        fonte = int(fonte)
    elif isinstance(fonte, str) and "://" not in fonte:
        nomes = listar_cameras()
        if fonte not in nomes:
            raise RuntimeError(f'A câmera "{fonte}" não está conectada. Câmeras encontradas: '
                               + (", ".join(nomes) or "nenhuma"))
        fonte = nomes.index(fonte)
    if isinstance(fonte, int):
        cap = cv2.VideoCapture(fonte, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(fonte)
        if not cap.isOpened():
            cap = cv2.VideoCapture(fonte)
        # MJPG: em 720p o formato sem compressão derruba a taxa de quadros de muitas webcams
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
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
    def __init__(self, modelo: Path, realce: bool = False, zoom=None, remoto=None):
        """zoom: objeto Zoom. remoto: CameraCelular (o recorte é feito no próprio celular)."""
        self.zoom, self.remoto = zoom, remoto
        self.ocupacao = 0.0       # largura do rosto / largura do quadro analisado
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
        usado, dx, dy = (0.0, 0.0, 1.0, 1.0), 0, 0
        if self.zoom is not None:
            if self.remoto is not None:
                usado = self.remoto.recorte_do_quadro
            else:                 # webcam / câmera IP: recorta aqui
                usado = self.zoom.recorte
                H, W = bgr.shape[:2]
                dx, dy = int(usado[0] * W), int(usado[1] * H)
                bgr = bgr[dy:dy + max(2, int(usado[3] * H)), dx:dx + max(2, int(usado[2] * W))]
        if self._realce is not None:
            bgr = self._realce(bgr)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        ts = int((time.monotonic() - self._t0) * 1000)
        ts = max(ts, self._ult_ts + 1)  # o MediaPipe exige tempo sempre crescente
        self._ult_ts = ts
        res = self._lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        if not res.face_landmarks:
            self._atualizar_zoom(None, usado)
            return None
        h, w = bgr.shape[:2]
        pts = np.array([(p.x * w, p.y * h) for p in res.face_landmarks[0]], dtype=float)
        if len(pts) < 478:
            return None  # modelo sem íris
        minimo, maximo = pts.min(axis=0), pts.max(axis=0)
        self.ocupacao = float((maximo[0] - minimo[0]) / w)
        self._atualizar_zoom((minimo[0] / w, minimo[1] / h, maximo[0] / w, maximo[1] / h), usado)
        pts[:, 0] += dx           # pontos no quadro inteiro (a prévia desenha nele)
        pts[:, 1] += dy
        return medir(pts)

    def _atualizar_zoom(self, caixa, usado) -> None:
        if self.zoom is None:
            return
        if self.zoom.atualizar(caixa, usado, time.monotonic()):
            print(f"Zoom: {self.zoom.fator:.1f}x")
        if self.remoto is not None:
            self.remoto.recorte_pedido = self.zoom.recorte

    def fechar(self):
        self._lm.close()
