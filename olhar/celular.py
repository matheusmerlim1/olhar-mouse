"""Câmera do celular pelo navegador, via QR code (sem instalar app).

O PC abre um servidor HTTPS na rede local e mostra um QR code com o endereço.
O celular abre a página, liga a câmera frontal e manda quadros JPEG para o PC.

- HTTPS é obrigatório: navegador de celular só libera a câmera em página
  segura. O certificado é gerado aqui (autoassinado), então na primeira vez o
  celular avisa "conexão não particular" → Avançado → continuar.
- O endereço tem um código aleatório: outro aparelho da rede não consegue
  mandar imagem sem ter lido o QR.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import secrets
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Olhar-mouse: câmera</title>
<style>
 body{margin:0;font:16px system-ui,sans-serif;background:#111;color:#eee;text-align:center}
 main{padding:16px}
 video{width:100%;max-width:420px;border-radius:12px;transform:scaleX(-1);background:#000}
 button{font-size:18px;padding:14px 22px;border:0;border-radius:10px;background:#3b82f6;color:#fff;margin:12px}
 #st{min-height:3em}
 .ok{color:#7ee787}.erro{color:#ff7b72}
</style></head><body><main>
<h1>Olhar-mouse</h1>
<p id="st">Toque no botão para usar a câmera frontal.</p>
<button id="ir">Usar câmera</button>
<video id="v" playsinline muted autoplay></video>
<p>Deixe o celular parado, em pé, perto da tela do computador e virado para o seu rosto.
Mantenha esta página aberta (a tela do celular não pode apagar).</p>
</main>
<script>
const st = document.getElementById('st'), v = document.getElementById('v');
const destino = location.pathname.replace(/\\/$/, '') + '/quadro';
// cada aba tem uma sessão; o PC só aceita a aba mais nova e manda as antigas pararem
// (várias abas abertas ao mesmo tempo travavam o Chrome do celular)
const sessao = Math.random().toString(36).slice(2) + Date.now().toString(36);
const QPS = 20;                                  // quadros por segundo (poupa o celular)
let rodando = false, enviados = 0, t0 = performance.now();
const dormir = ms => new Promise(r => setTimeout(r, ms));
function msg(t, c){ st.textContent = t; st.className = c || ''; }
async function manterAcesa(){
  try { if ('wakeLock' in navigator && !document.hidden) await navigator.wakeLock.request('screen'); } catch(e) {}
}
function parar(t){
  rodando = false;
  if (v.srcObject) v.srcObject.getTracks().forEach(tr => tr.stop());
  v.srcObject = null;
  msg(t, 'erro');
  try { window.close(); } catch(e) {}
}
async function iniciar(){
  if (!window.isSecureContext){ msg('A página não está em HTTPS: a câmera fica bloqueada.', 'erro'); return; }
  try {
    const s = await navigator.mediaDevices.getUserMedia({audio:false,
      video:{facingMode:'user', width:{ideal:640}, height:{ideal:480}, frameRate:{ideal:QPS, max:30}}});
    v.srcObject = s; await v.play();
  } catch(e){
    if (e.name === 'NotAllowedError'){ msg('Permita o uso da câmera e toque em “Usar câmera”.', 'erro'); return; }
    // câmera ocupada (desbloqueio facial, outro app) ou celular bloqueado: tenta de novo sozinho
    msg('Câmera ocupada ou celular bloqueado — tentando de novo… (' + e.message + ')', 'erro');
    setTimeout(iniciar, 3000);
    return;
  }
  document.getElementById('ir').hidden = true;
  manterAcesa(); document.addEventListener('visibilitychange', manterAcesa);
  if (!rodando){ rodando = true; enviar(); }
}
async function enviar(){
  const c = document.createElement('canvas'), ctx = c.getContext('2d');
  while (rodando){
    if (document.hidden){ await dormir(500); continue; }   // aba escondida não envia nada
    if (!v.videoWidth){ await dormir(100); continue; }
    const inicio = performance.now();
    const k = Math.min(1, 640 / Math.max(v.videoWidth, v.videoHeight));
    c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
    ctx.drawImage(v, 0, 0, c.width, c.height);
    const b = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.7));
    try {
      const r = await fetch(destino, {method:'POST', body:b, cache:'no-store', headers:{'X-Sessao': sessao}});
      if (r.status === 409){ parar('Esta aba foi substituída por outra mais nova. Pode fechá-la.'); return; }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      enviados++;
      const s = (performance.now() - t0) / 1000;
      if (s > 1){ msg('Enviando para o computador: ' + (enviados / s).toFixed(0) + ' quadros/s', 'ok'); enviados = 0; t0 = performance.now(); }
    } catch(e){ msg('Sem conexão com o computador (' + e.message + '). Tentando de novo…', 'erro');
      await dormir(1000); continue; }
    const resto = 1000 / QPS - (performance.now() - inicio);
    if (resto > 0) await dormir(resto);
  }
}
document.getElementById('ir').onclick = iniciar;
iniciar();
</script></body></html>
"""


class _Servidor(ThreadingHTTPServer):
    # no Windows, SO_REUSEADDR deixa DOIS programas abrirem a mesma porta;
    # sem ele, uma segunda cópia do olhar-mouse pula para a próxima porta livre
    allow_reuse_address = False
    daemon_threads = True


def ip_local() -> str:
    """IP do PC na rede Wi-Fi/cabo (não manda pacote nenhum; só consulta a rota)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def garantir_certificado(pasta: Path, ip: str) -> tuple[Path, Path]:
    """Cria (ou reaproveita) um certificado autoassinado válido para este IP."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    pasta.mkdir(parents=True, exist_ok=True)
    crt, chave = pasta / "celular_cert.pem", pasta / "celular_chave.pem"
    if crt.exists() and chave.exists():
        try:
            atual = x509.load_pem_x509_certificate(crt.read_bytes())
            ips = atual.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            if ipaddress.ip_address(ip) in ips.get_values_for_type(x509.IPAddress) \
                    and atual.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7):
                return crt, chave
        except Exception:
            pass
    k = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"olhar-mouse {ip}")])
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome)
            .public_key(k.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(days=1))
            .not_valid_after(agora + dt.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]), critical=False)
            .sign(k, hashes.SHA256()))
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    chave.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    return crt, chave


def _token(pasta: Path) -> str:
    """Código do endereço; fica salvo para o link do celular continuar valendo."""
    arq = pasta / "celular_codigo.txt"
    if arq.exists() and len(t := arq.read_text().strip()) >= 8:
        return t
    pasta.mkdir(parents=True, exist_ok=True)
    t = secrets.token_urlsafe(9)
    arq.write_text(t)
    return t


class CameraCelular:
    """Imita o cv2.VideoCapture: `read()` devolve o quadro mais novo do celular."""

    def __init__(self, pasta_dados: Path, porta: int = 8443, ip: str | None = None, usb: bool = False):
        """usb=True: HTTP só no 127.0.0.1, para o túnel do `adb reverse`.

        Pelo cabo o celular abre http://127.0.0.1, que o navegador já trata
        como página segura (libera a câmera sem certificado), e o servidor
        não fica visível na rede.
        """
        self.usb = usb
        # 127.0.0.1 e não "localhost": localhost tenta o IPv6 (::1) antes e cada
        # envio esperava ~2 s; 127.0.0.1 também conta como página segura
        self.ip = "127.0.0.1" if usb else (ip or ip_local())
        self.codigo = _token(pasta_dados)
        if not usb:
            crt, chave = garantir_certificado(pasta_dados, self.ip)
        self._jpeg = None
        self._n = 0          # quadros recebidos
        self._lido = 0       # último quadro entregue pelo read()
        self._cond = threading.Condition()
        self.ultimo_quadro_t = 0.0
        self._sessao = ""            # aba do celular que está valendo
        self._antigas: set[str] = set()

        cam = self

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _rota(self):
                return self.path.split("?")[0].rstrip("/")

            def do_GET(self):
                if self._rota() != f"/{cam.codigo}":
                    self.send_error(404)
                    return
                corpo = PAGINA.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    n = -1
                if not 0 < n < 5_000_000:
                    self.send_error(400)
                    return
                # lê o corpo antes de responder, mesmo para recusar: responder
                # com dados ainda chegando derruba a conexão (WinError 10054)
                dados = self.rfile.read(n)
                if self._rota() != f"/{cam.codigo}/quadro":
                    self.send_error(404)
                    return
                # só a aba mais nova manda imagem: as antigas recebem 409 e desligam a
                # câmera. Com várias abas, quadros velhos se misturavam com os atuais
                # (cursor pulando) e o Chrome do celular travava.
                sessao = self.headers.get("X-Sessao", "")
                with cam._cond:
                    recusar = not sessao or sessao in cam._antigas
                    if not recusar and sessao != cam._sessao:
                        if cam._sessao:
                            cam._antigas.add(cam._sessao)
                        cam._sessao = sessao
                if recusar:
                    self.send_response(409)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                with cam._cond:
                    cam._jpeg = dados
                    cam._n += 1
                    cam.ultimo_quadro_t = time.monotonic()
                    cam._cond.notify_all()
                self.send_response(204)
                self.end_headers()

        ultimo_erro = None
        endereco = "127.0.0.1" if usb else "0.0.0.0"
        for p in range(porta, porta + 10):
            try:
                self._srv = _Servidor((endereco, p), _H)
                self.porta = p
                break
            except OSError as e:
                ultimo_erro = e
        else:
            raise RuntimeError(f"Nenhuma porta livre entre {porta} e {porta + 9}: {ultimo_erro}")
        if not usb:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(crt), str(chave))
            self._srv.socket = ctx.wrap_socket(self._srv.socket, server_side=True)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"{'http' if self.usb else 'https'}://{self.ip}:{self.porta}/{self.codigo}"

    @property
    def recebidos(self) -> int:
        return self._n

    def conectado(self, ate: float = 1.5) -> bool:
        return self._n > 0 and time.monotonic() - self.ultimo_quadro_t < ate

    # --- interface do cv2.VideoCapture usada pelo resto do programa
    def isOpened(self) -> bool:
        return True

    def set(self, *a) -> bool:
        return True

    def read(self, espera: float = 0.5):
        with self._cond:
            if self._n == self._lido:
                self._cond.wait(espera)
            if self._n == self._lido or self._jpeg is None:
                return False, None
            self._lido, jpeg = self._n, self._jpeg
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        return (img is not None), img

    def release(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()


def imagem_qr(texto: str, lado: int) -> np.ndarray:
    """QR code em BGR (preto no branco), quadrado de `lado` pixels."""
    import qrcode
    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(texto)
    qr.make(fit=True)
    m = np.array(qr.get_matrix(), dtype=bool)
    img = np.where(m, 0, 255).astype(np.uint8)
    escala = max(1, lado // img.shape[0])
    img = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def aguardar_celular(cam: CameraCelular, tela_wh: tuple[int, int], janela: str,
                     tela_cheia: bool = True, deve_parar=lambda: False) -> bool:
    """Mostra o QR code até o celular começar a mandar imagem.

    Devolve True quando conectou, False se `deve_parar()` ficou verdadeiro
    (Sair/trocar câmera pelo menu). Esc levanta `Cancelado`.
    """
    from .calibracao import Cancelado

    w, h = tela_wh if tela_cheia else (900, 900)
    lado = int(min(w, h) * (0.55 if tela_cheia else 0.6))
    qr = imagem_qr(cam.url, lado)
    cv2.namedWindow(janela, cv2.WINDOW_NORMAL)
    if tela_cheia:
        cv2.setWindowProperty(janela, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(janela, w, h)
        cv2.setWindowProperty(janela, cv2.WND_PROP_TOPMOST, 1)
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    esc = 1.0 if tela_cheia else 0.75

    def linha(img, txt, y, k=0.8, cor=(235, 235, 235)):
        (tw, _), _ = cv2.getTextSize(txt, fonte, k * esc, 2)
        cv2.putText(img, txt, ((w - tw) // 2, y), fonte, k * esc, cor, 2 if k >= 0.7 else 1, cv2.LINE_AA)

    inicio = None
    n_antes = cam.recebidos
    try:
        while True:
            if deve_parar():
                return False
            img = np.full((h, w, 3), 24, np.uint8)
            y0, x0 = int(h * 0.12), (w - qr.shape[1]) // 2
            img[y0:y0 + qr.shape[0], x0:x0 + qr.shape[1]] = qr
            linha(img, "Aponte a camera do celular para o QR code", y0 - int(30 * esc), 1.0)
            yb = y0 + qr.shape[0] + int(40 * esc)
            passo = int(30 * esc)
            linha(img, cam.url, yb, 0.75, (120, 200, 255))
            linha(img, "'Conexao nao particular' no celular: Avancado > Continuar", yb + passo, 0.55, (190, 190, 190))
            linha(img, "Celular no mesmo Wi-Fi do PC. Pagina nao abre? Menu do icone > Liberar firewall",
                  yb + 2 * passo, 0.55, (190, 190, 190))
            if cam.recebidos > n_antes:
                inicio = inicio or time.monotonic()
                linha(img, "Celular conectado!", yb + 4 * passo, 0.9, (120, 230, 120))
            else:
                linha(img, "Aguardando o celular...", yb + 4 * passo, 0.9, (80, 200, 255))
            linha(img, "Esc fecha esta janela" if not tela_cheia else "Esc cancela", h - 25, 0.55, (150, 150, 150))
            cv2.imshow(janela, img)
            if (cv2.waitKey(50) & 0xFF) in (27, ord("q")):
                raise Cancelado
            if inicio and time.monotonic() - inicio > 1.0:
                return True
    finally:
        try:
            cv2.destroyWindow(janela)
        except cv2.error:
            pass
