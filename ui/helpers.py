from datetime import datetime
from tkinter import messagebox


def traduzir_setor(tipo_operacao):
    if tipo_operacao == "ENTREGA":
        return "RECEPÇÃO"
    if tipo_operacao == "RETIRADA":
        return "EXPEDIÇÃO"
    return "N/A"


def copiar_texto(root, valor, rotulo="Conteúdo"):
    texto = str(valor).strip()
    if not texto or texto == "N/A":
        messagebox.showwarning("Aviso", f"Não há {rotulo.lower()} disponível para copiar.")
        return

    root.clipboard_clear()
    root.clipboard_append(texto)
    root.update()


def smartcard_valido(valor):
    valor = valor.strip()
    return valor.isalnum() and len(valor) == 10


def formatar_data_br(valor):
    if not valor or valor == "Ainda não concluído":
        return valor

    formatos = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for formato in formatos:
        try:
            dt = datetime.strptime(str(valor), formato)
            if formato == "%Y-%m-%d":
                return dt.strftime("%d/%m/%Y")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue

    return valor


def limpar_documento(valor):
    if valor is None:
        return ""
    return "".join(ch for ch in str(valor) if ch.isalnum())