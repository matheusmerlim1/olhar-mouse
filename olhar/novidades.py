"""Card "O que mudou" mostrado uma vez depois de cada atualização.

Lê dados/novidades.json (gravado pelo atualizador) e separa os títulos dos commits pelo
padrão do githubGuia: `feat:` → Novidades, `fix:` → Correções. `chore:`, `docs:`, `test:`,
`style:` e `refactor:` não interessam a quem usa e ficam de fora.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_PREFIXO = re.compile(r"^(\w+)(\([^)]*\))?!?:\s*(.+)$")


def classificar(titulos: list[str]) -> tuple[list[str], list[str]]:
    novidades, correcoes = [], []
    for t in titulos:
        m = _PREFIXO.match(t.strip())
        if not m:
            continue
        tipo, texto = m.group(1).lower(), m.group(3).strip()
        texto = texto[:1].upper() + texto[1:]
        if tipo == "feat":
            novidades.append(texto)
        elif tipo == "fix":
            correcoes.append(texto)
    return novidades, correcoes


def pendentes(raiz: Path) -> dict | None:
    """Novidades ainda não mostradas (e apaga o arquivo: o card aparece uma vez só)."""
    arq = raiz / "dados" / "novidades.json"
    if not arq.exists():
        return None
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = None
    try:
        arq.unlink()
    except OSError:
        pass
    return dados


def mostrar_card(dados: dict, fechar_sozinho_ms: int = 0) -> None:
    """Janela pequena e centralizada com o que foi atualizado e corrigido."""
    import tkinter as tk
    from tkinter import font

    novidades, correcoes = classificar(dados.get("titulos", []))
    if not novidades and not correcoes:
        correcoes = ["Melhorias internas."]

    raiz = tk.Tk()
    raiz.title("Olhar-mouse atualizado")
    raiz.configure(bg="#ffffff")
    raiz.resizable(False, False)
    raiz.attributes("-topmost", True)
    base = font.nametofont("TkDefaultFont").actual()["family"]
    f_titulo = (base, 15, "bold")
    f_secao = (base, 11, "bold")
    f_texto = (base, 10)

    quadro = tk.Frame(raiz, bg="#ffffff", padx=26, pady=22)
    quadro.pack(fill="both", expand=True)
    tk.Label(quadro, text="Olhar-mouse foi atualizado", font=f_titulo, bg="#ffffff",
             fg="#1c2230").pack(anchor="w")
    versao = f"versão {dados.get('de') or '?'}  →  {dados.get('para') or '?'}"
    tk.Label(quadro, text=versao, font=f_texto, bg="#ffffff", fg="#5b6474").pack(anchor="w", pady=(2, 12))

    for titulo, itens, cor in (("Novidades", novidades, "#1a7f37"), ("Correções", correcoes, "#0b6bcb")):
        if not itens:
            continue
        tk.Label(quadro, text=titulo, font=f_secao, bg="#ffffff", fg=cor).pack(anchor="w", pady=(6, 2))
        for item in itens[:12]:
            tk.Label(quadro, text="•  " + item, font=f_texto, bg="#ffffff", fg="#1c2230",
                     wraplength=460, justify="left").pack(anchor="w", padx=(6, 0))
        if len(itens) > 12:
            tk.Label(quadro, text=f"… e mais {len(itens) - 12}", font=f_texto, bg="#ffffff",
                     fg="#5b6474").pack(anchor="w", padx=(6, 0))

    botao = tk.Button(quadro, text="OK, continuar", font=f_secao, bg="#0b6bcb", fg="#ffffff",
                      activebackground="#0a5db0", activeforeground="#ffffff", relief="flat",
                      padx=18, pady=6, command=raiz.destroy)
    botao.pack(anchor="e", pady=(18, 0))
    botao.focus_set()
    raiz.bind("<Return>", lambda _: raiz.destroy())
    raiz.bind("<Escape>", lambda _: raiz.destroy())

    raiz.update_idletasks()
    w, h = raiz.winfo_reqwidth(), raiz.winfo_reqheight()
    raiz.geometry(f"+{(raiz.winfo_screenwidth() - w) // 2}+{(raiz.winfo_screenheight() - h) // 3}")
    if fechar_sozinho_ms:
        raiz.after(fechar_sozinho_ms, raiz.destroy)
    raiz.mainloop()
