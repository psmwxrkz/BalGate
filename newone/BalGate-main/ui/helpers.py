from datetime import datetime
from tkinter import messagebox


def traduzir_setor(tipo_operacao):
    texto = str(tipo_operacao or "").strip().upper()

    mapa = {
        "ENTREGA": "RECEPÇÃO",
        "RETIRADA": "EXPEDIÇÃO",
        "RECEPCAO": "RECEPÇÃO",
        "RECEPÇÃO": "RECEPÇÃO",
        "EXPEDICAO": "EXPEDIÇÃO",
        "EXPEDIÇÃO": "EXPEDIÇÃO",
    }

    if texto in mapa:
        return mapa[texto]

    if not texto:
        return "N/A"

    return texto


def copiar_texto(root, valor, rotulo="Conteúdo"):
    texto = str(valor).strip()

    if not texto or texto.upper() == "N/A":
        messagebox.showwarning("Aviso", f"Não há {rotulo.lower()} disponível para copiar.")
        return

    root.clipboard_clear()
    root.clipboard_append(texto)
    root.update()


def smartcard_valido(valor):
    valor = str(valor or "").strip()
    return valor.isalnum() and len(valor) == 10


def formatar_data_br(valor):
    if not valor:
        return valor

    texto = str(valor).strip()

    if texto in ("Ainda não concluído", "N/A", ""):
        return texto

    texto_iso = texto.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(texto_iso)
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%d/%m/%Y")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass

    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]

    for formato in formatos:
        try:
            dt = datetime.strptime(texto, formato)
            if formato in ("%Y-%m-%d", "%d/%m/%Y"):
                return dt.strftime("%d/%m/%Y")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue

    return texto


def limpar_documento(valor):
    if valor is None:
        return ""
    return "".join(ch for ch in str(valor) if ch.isalnum())