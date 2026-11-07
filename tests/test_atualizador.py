"""Atualização automática e card de novidades (sem internet: tudo local)."""
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from olhar import atualizador, novidades


def zip_do_github(arquivos: dict) -> bytes:
    """Imita o ZIP do codeload: tudo dentro de "olhar-mouse-main/"."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr("olhar-mouse-main/" + nome, conteudo)
    return buf.getvalue()


class TestAplicarZip(unittest.TestCase):
    def test_troca_codigo_e_protege_dados_e_venv(self):
        raiz = Path(tempfile.mkdtemp())
        (raiz / "olhar").mkdir()
        (raiz / "olhar" / "app.py").write_text("velho")
        (raiz / "dados").mkdir()
        (raiz / "dados" / "calibracao.json").write_text("minha calibração")
        trocados = atualizador.aplicar_zip(zip_do_github({
            "olhar/app.py": "novo", "olhar/novo.py": "x", "README.md": "leia",
            "dados/calibracao.json": "NÃO PODE SOBRESCREVER", ".venv/lixo": "não",
        }), raiz)
        self.assertEqual((raiz / "olhar" / "app.py").read_text(), "novo")
        self.assertEqual((raiz / "dados" / "calibracao.json").read_text(), "minha calibração")
        self.assertFalse((raiz / ".venv").exists())
        self.assertEqual(sorted(trocados), ["README.md", "olhar/app.py", "olhar/novo.py"])

    def test_so_fim_de_linha_diferente_nao_conta(self):
        raiz = Path(tempfile.mkdtemp())
        (raiz / "requirements.txt").write_bytes(b"numpy\r\nqrcode\r\n")
        zipado = zip_do_github({"requirements.txt": "numpy\nqrcode\n"})
        self.assertEqual(atualizador.aplicar_zip(zipado, raiz), [])

    def test_arquivo_igual_nao_conta_como_trocado(self):
        raiz = Path(tempfile.mkdtemp())
        (raiz / "a.txt").write_bytes(b"igual")
        self.assertEqual(atualizador.aplicar_zip(zip_do_github({"a.txt": "igual"}), raiz), [])


class TestVersao(unittest.TestCase):
    def test_versao_do_zip_e_marcador_nao_expandido(self):
        raiz = Path(tempfile.mkdtemp())
        (raiz / "olhar").mkdir()
        arq = raiz / "olhar" / "versao.txt"
        arq.write_text("$Format:%H$\n")
        self.assertEqual(atualizador.versao_local(raiz), "")      # cópia sem git e sem export-subst
        arq.write_text("0123456789abcdef0123456789abcdef01234567\n")
        self.assertEqual(atualizador.versao_curta(raiz), "0123456")


class TestGit(unittest.TestCase):
    """Repositório "remoto" local: a cópia de trabalho fica para trás e se atualiza."""

    def git(self, pasta, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(pasta), *args],
                              capture_output=True, text=True, check=True).stdout

    def test_fast_forward_e_novidades(self):
        base = Path(tempfile.mkdtemp())
        remoto, copia = base / "remoto", base / "copia"
        remoto.mkdir()
        self.git(remoto, "init", "-q", "-b", "main")
        (remoto / "requirements.txt").write_text("numpy\n")
        (remoto / "a.py").write_text("1")
        self.git(remoto, "add", "-A")
        self.git(remoto, "commit", "-q", "-m", "feat: primeira versão")
        subprocess.run(["git", "clone", "-q", str(remoto), str(copia)], check=True)
        (remoto / "a.py").write_text("2")
        self.git(remoto, "commit", "-q", "-am", "fix: clique caía fora do lugar")
        (remoto / "a.py").write_text("3")
        self.git(remoto, "commit", "-q", "-am", "feat: card de novidades")
        self.git(remoto, "commit", "-q", "--allow-empty", "-m", "chore: arruma testes")

        atualizou, msg = atualizador.procurar_e_aplicar(copia)
        self.assertTrue(atualizou, msg)
        self.assertEqual((copia / "a.py").read_text(), "3")
        dados = novidades.pendentes(copia)
        self.assertIsNotNone(dados)
        self.assertEqual(novidades.classificar(dados["titulos"]),
                         (["Card de novidades"], ["Clique caía fora do lugar"]))
        self.assertIsNone(novidades.pendentes(copia))            # mostra uma vez só
        self.assertFalse(atualizador.procurar_e_aplicar(copia)[0])  # já está em dia

    def test_alteracao_local_nao_e_atropelada(self):
        base = Path(tempfile.mkdtemp())
        remoto, copia = base / "remoto", base / "copia"
        remoto.mkdir()
        self.git(remoto, "init", "-q", "-b", "main")
        (remoto / "requirements.txt").write_text("numpy\n")
        (remoto / "a.py").write_text("1")
        self.git(remoto, "add", "-A")
        self.git(remoto, "commit", "-q", "-m", "feat: v1")
        subprocess.run(["git", "clone", "-q", str(remoto), str(copia)], check=True)
        (remoto / "a.py").write_text("2")
        self.git(remoto, "commit", "-q", "-am", "feat: v2")
        (copia / "a.py").write_text("trabalho do dono")
        atualizou, msg = atualizador.procurar_e_aplicar(copia)
        self.assertFalse(atualizou)
        self.assertIn("alterações locais", msg)
        self.assertEqual((copia / "a.py").read_text(), "trabalho do dono")


class TestClassificar(unittest.TestCase):
    def test_prefixos(self):
        n, c = novidades.classificar([
            "feat: celular pelo cabo USB", "fix(bandeja): ícone sumia", "chore: limpeza",
            "docs: README", "mensagem sem prefixo", "feat!: muda o formato da config"])
        self.assertEqual(n, ["Celular pelo cabo USB", "Muda o formato da config"])
        self.assertEqual(c, ["Ícone sumia"])


if __name__ == "__main__":
    unittest.main()
