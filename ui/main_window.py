import os
import sys
import queue
import tkinter as tk
import ctypes
import threading
import pystray
import webbrowser

from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from ctypes import wintypes
from datetime import datetime

from config import APP_TITLE, APP_GEOMETRY, APP_MIN_WIDTH, APP_MIN_HEIGHT, CORES
from services.cadastro_service import CadastroService
from ui.styles import aplicar_estilos
from ui.alerts import ativar_alerta_visual, parar_alerta, mostrar_alerta_canto
from ui.helpers import (
    traduzir_setor,
    copiar_texto,
    smartcard_valido,
    formatar_data_br,
    limpar_documento,
)
 
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def configurar_icone_janela(root):
    try:
        app_id = "controle.diversos.app"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

    try:
        ico_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(ico_path):
            root.iconbitmap(ico_path)
    except Exception as e:
        print("Erro ao aplicar iconbitmap:", e)

    try:
        png_path = resource_path(os.path.join("assets", "app.png"))
        if os.path.exists(png_path):
            imagem = Image.open(png_path)
            icone = ImageTk.PhotoImage(imagem)
            root.iconphoto(True, icone)
            root._icone_app = icone
    except Exception as e:
        print("Erro ao aplicar iconphoto:", e)


class SistemaCadastrosApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(APP_GEOMETRY)
        self.root.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)
        self.root.configure(bg=CORES["bg_app"])

        try:
            self.root.state("zoomed")
        except Exception:
            pass

        self.tray_icon = None
        self.tray_thread = None
        self.icone_tray_ativo = False
        self.janela_oculta = False

        self.service = CadastroService()

        self.pendentes_filtrados = []
        self.realizados_filtrados = []
        self.alerta_piscando = False
        self.cor_alerta = False
        self.cadastro_em_exibicao = None
        self.origem_em_exibicao = None
        self.logo_img = None

        self.card_pendente_selecionado = None
        self.card_realizado_selecionado = None

        self.var_busca = tk.StringVar()
        self.var_busca.trace_add("write", self.filtrar_listas)

        self.var_smartcard = tk.StringVar()
        self.alerta_after_id = None
        self.mensagem_alerta_atual = ""

        self.lbl_total_pendentes = None
        self.lbl_total_realizados = None

        self.fila_eventos_stream = queue.Queue()
        self.ids_pendentes_atuais = set()
        self._snapshot_listas = None

        aplicar_estilos()
        self.criar_interface()

        try:
            self.sincronizar_com_firebase(exibir_alertas=False)
        except Exception as e:
            print("Erro na carga inicial do Firebase:", repr(e))
        
        try:
            
            print("Stream do Firebase iniciado com sucesso.")
        except Exception as e:
            print("Erro ao iniciar stream do Firebase:", repr(e))
        
        self.root.protocol("WM_DELETE_WINDOW", self.ocultar_para_segundo_plano)
 
        # Mantém o ícone sempre ativo na bandeja,
        # mesmo com a janela principal aberta.
        self.criar_icone_bandeja()
 
        self.iniciar_sincronizacao_periodica()

    def iniciar_sincronizacao_periodica(self):
        try:
            visitantes, mudou = self.service.client.buscar_visitantes()
    
            excluidos = self.service.client.limpar_realizados_antigos(visitantes=visitantes, horas=24)
    
            if excluidos > 0:
                visitantes, mudou = self.service.client.buscar_visitantes()
    
            if mudou:
                self.sincronizar_com_firebase(
                    exibir_alertas=True,
                    visitantes=visitantes,
                )
            else:
                self.atualizar_status_alerta()
    
        except Exception as e:
            print("Erro sincronizacao:", repr(e))
    
        self.root.after(2500, self.iniciar_sincronizacao_periodica)

    def filtrar_listas(self, *args):
        self.pendentes_filtrados, self.realizados_filtrados = self.service.filtrar(self.var_busca.get())
        self.atualizar_listas()

    def atualizar_status_alerta(self):
        total_pendentes = len(self.service.cadastros_pendentes)

        if total_pendentes == 0:
            self.cor_alerta = False
            parar_alerta(self.lbl_alerta, self)
        else:
            self.lbl_alerta.config(
                text=f"{total_pendentes} pendência(s) no sistema",
                bg=CORES["amarelo"],
                fg="white",
            )

        if self.lbl_total_pendentes:
            self.lbl_total_pendentes.config(text=str(len(self.service.cadastros_pendentes)))

        if self.lbl_total_realizados:
            self.lbl_total_realizados.config(text=str(len(self.service.cadastros_realizados)))

    def atualizar_listas(self, force=False):
        snapshot_atual = (
            tuple(
                (
                    c.get("id", ""),
                    c.get("status", ""),
                    c.get("placa", ""),
                    c.get("motorista_nome", ""),
                    c.get("empresa_motorista", ""),
                    c.get("smartcard", ""),
                    c.get("concluido_em", ""),
                )
                for c in self.pendentes_filtrados
            ),
            tuple(
                (
                    c.get("id", ""),
                    c.get("status", ""),
                    c.get("placa", ""),
                    c.get("motorista_nome", ""),
                    c.get("empresa_motorista", ""),
                    c.get("smartcard", ""),
                    c.get("concluido_em", ""),
                )
                for c in self.realizados_filtrados
            ),
        )
    
        if not force and snapshot_atual == self._snapshot_listas:
            self.atualizar_status_alerta()
            return
    
        self._snapshot_listas = snapshot_atual
    
        cadastro_selecionado_id = None
        origem_selecionada = None
    
        if self.cadastro_em_exibicao:
            cadastro_selecionado_id = self.cadastro_em_exibicao.get("id")
            origem_selecionada = self.origem_em_exibicao
    
        for widget in self.lista_pendentes.winfo_children():
            widget.destroy()
    
        for widget in self.lista_realizados.winfo_children():
            widget.destroy()
    
        self.card_pendente_selecionado = None
        self.card_realizado_selecionado = None
    
        if not self.pendentes_filtrados:
            tk.Label(
                self.lista_pendentes,
                text="Nenhum cadastro pendente encontrado.",
                bg=CORES["bg_card"],
                fg=CORES["texto_secundario"],
                font=("Segoe UI", 10),
                pady=10,
            ).pack(fill="x")
        else:
            for cadastro in self.pendentes_filtrados:
                self.criar_card_ficha(self.lista_pendentes, cadastro, origem="pendente")
    
        if not self.realizados_filtrados:
            tk.Label(
                self.lista_realizados,
                text="Nenhum cadastro realizado encontrado.",
                bg=CORES["bg_card"],
                fg=CORES["texto_secundario"],
                font=("Segoe UI", 10),
                pady=10,
            ).pack(fill="x")
        else:
            for cadastro in self.realizados_filtrados:
                self.criar_card_ficha(self.lista_realizados, cadastro, origem="realizado")
    
        self.atualizar_status_alerta()
    
        if cadastro_selecionado_id and origem_selecionada:
            lista_origem = self.pendentes_filtrados if origem_selecionada == "pendente" else self.realizados_filtrados
    
            for cadastro in lista_origem:
                if cadastro.get("id") == cadastro_selecionado_id:
                    self.cadastro_em_exibicao = cadastro
                    self.origem_em_exibicao = origem_selecionada
                    break

    def criar_icone_bandeja(self):
        if self.tray_icon is not None or self.icone_tray_ativo:
            return

        try:
            caminho_ico = resource_path(os.path.join("assets", "app.ico"))
            caminho_png = resource_path(os.path.join("assets", "app.png"))

            if os.path.exists(caminho_png):
                imagem = Image.open(caminho_png).copy()
            elif os.path.exists(caminho_ico):
                imagem = Image.open(caminho_ico).copy()
            else:
                print("Nenhum ícone encontrado para a bandeja.")
                return

            menu = pystray.Menu(
                pystray.MenuItem("Abrir", self.abrir_pelo_tray, default=True),
                pystray.MenuItem("Sair", self.sair_pelo_tray),
            )

            self.tray_icon = pystray.Icon(
                "ControleDiversosTray",
                imagem,
                "Controle Diversos",
                menu,
            )

            self.icone_tray_ativo = True

            def run_tray():
                try:
                    self.tray_icon.run()
                except Exception as e:
                    print("Erro na thread do tray:", e)
                finally:
                    self.icone_tray_ativo = False
                    self.tray_icon = None
                    self.tray_thread = None

            self.tray_thread = threading.Thread(target=run_tray, daemon=True)
            self.tray_thread.start()

        except Exception as e:
            print("Erro ao criar ícone da bandeja:", e)
            self.icone_tray_ativo = False
            self.tray_icon = None
            self.tray_thread = None

    def remover_icone_bandeja(self):
        icon = self.tray_icon

        if not icon:
            self.icone_tray_ativo = False
            self.tray_thread = None
            self.tray_icon = None
            return

        try:
            icon.visible = False
        except Exception:
            pass

        try:
            icon.stop()
        except Exception as e:
            print("Erro ao remover ícone da bandeja:", e)
        finally:
            self.icone_tray_ativo = False
            self.tray_icon = None
            self.tray_thread = None

    def abrir_pelo_tray(self, icon=None, item=None):
        self.root.after(0, self.restaurar_janela_principal)

    def sair_pelo_tray(self, icon=None, item=None):
        self.root.after(0, self.fechar_aplicacao_de_verdade)

    def ocultar_para_segundo_plano(self):
        try:
            if self.janela_oculta:
                return
    
            self.janela_oculta = True
            self.root.withdraw()
    
            # Garante que o ícone exista na bandeja.
            # Como criar_icone_bandeja já evita duplicação,
            # pode ser chamado com segurança.
            self.criar_icone_bandeja()
        except Exception as e:
            self.janela_oculta = False
            print("Erro ao ocultar para segundo plano:", e)

    def fechar_aplicacao_de_verdade(self):
        try:
            self.janela_oculta = False
            self.remover_icone_bandeja()
            self.parar_piscar_barra_tarefas()
        except Exception:
            pass

        try:
            liberar_instancia_unica()
        except Exception:
            pass

        try:
            self.root.quit()
            self.root.destroy()
        except Exception as e:
            print("Erro ao fechar aplicação:", e)

    def sincronizar_com_firebase(self, exibir_alertas=False, visitantes=None):
        try:
            ids_anteriores = set(self.ids_pendentes_atuais)
    
            novos_cadastros = self.service.atualizar_fichas_api(visitantes)
            self.filtrar_listas()
    
            self.ids_pendentes_atuais = {
                cadastro.get("id")
                for cadastro in self.service.cadastros_pendentes
                if cadastro.get("id")
            }
    
            if self.cadastro_em_exibicao:
                id_atual = self.cadastro_em_exibicao.get("id")
                todos_ids = {
                    cadastro.get("id")
                    for cadastro in (self.service.cadastros_pendentes + self.service.cadastros_realizados)
                }
                if id_atual not in todos_ids:
                    self.limpar_painel_central()
    
            if exibir_alertas:
                novos_ids = self.ids_pendentes_atuais - ids_anteriores
    
                if novos_ids:
                    novos_pendentes = [
                        cadastro
                        for cadastro in self.service.cadastros_pendentes
                        if cadastro.get("id") in novos_ids
                    ]
    
                    if not novos_pendentes and novos_cadastros:
                        novos_pendentes = [
                            cadastro
                            for cadastro in novos_cadastros
                            if cadastro.get("status") == "pendente"
                        ]
    
                    if novos_pendentes:
                        self.piscar_barra_tarefas()
    
                        mensagem_topo = (
                            f"{len(novos_pendentes)} novo(s) cadastro(s) pendente(s)"
                            if len(novos_pendentes) > 1
                            else f"Novo cadastro recebido: {novos_pendentes[0].get('motorista_nome', '')}"
                        )
    
                        ativar_alerta_visual(self.lbl_alerta, self, mensagem_topo)
    
                        for cadastro in novos_pendentes:
                            self.mostrar_popup_alerta(
                                f"{cadastro.get('motorista_nome', '')} | Placa: {cadastro.get('placa', '')}"
                            )
    
        except Exception as e:
            print("Erro em sincronizar_com_firebase:", repr(e))
            
    def criar_interface(self):
        topo = tk.Frame(self.root, bg=CORES["bg_app"])
        topo.pack(fill="x", padx=20, pady=18)

        bloco_topo_esquerda = tk.Frame(topo, bg=CORES["bg_app"])
        bloco_topo_esquerda.pack(side="left", fill="x", expand=True)

        self.criar_logo(bloco_topo_esquerda)

        area_titulos = tk.Frame(bloco_topo_esquerda, bg=CORES["bg_app"])
        area_titulos.pack(side="left", padx=(18, 0))

        ttk.Label(area_titulos, text="Painel de Cadastros", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            area_titulos,
            text="Acompanhe pendências de diversos, e registre-os para acessarem a balança.",
            style="Subtitulo.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        painel_topo_direita = tk.Frame(topo, bg=CORES["bg_app"])
        painel_topo_direita.pack(side="right")

        cards_resumo = tk.Frame(painel_topo_direita, bg=CORES["bg_app"])
        cards_resumo.pack(anchor="e", pady=(0, 8))

        card_pendentes = tk.Frame(
            cards_resumo,
            bg=CORES["card_info"],
            highlightthickness=1,
            highlightbackground=CORES["borda"],
            padx=14,
            pady=8,
        )
        card_pendentes.pack(side="left", padx=(0, 8))

        tk.Label(
            card_pendentes,
            text="Pendentes",
            bg=CORES["card_info"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        self.lbl_total_pendentes = tk.Label(
            card_pendentes,
            text="0",
            bg=CORES["card_info"],
            fg=CORES["amarelo"],
            font=("Segoe UI", 16, "bold"),
        )
        self.lbl_total_pendentes.pack(anchor="w")

        card_realizados = tk.Frame(
            cards_resumo,
            bg=CORES["card_info"],
            highlightthickness=1,
            highlightbackground=CORES["borda"],
            padx=14,
            pady=8,
        )
        card_realizados.pack(side="left")

        tk.Label(
            card_realizados,
            text="Realizados",
            bg=CORES["card_info"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        self.lbl_total_realizados = tk.Label(
            card_realizados,
            text="0",
            bg=CORES["card_info"],
            fg=CORES["verde"],
            font=("Segoe UI", 16, "bold"),
        )
        self.lbl_total_realizados.pack(anchor="w")

        self.lbl_alerta = tk.Label(
            painel_topo_direita,
            text="Sem novos alertas",
            bg=CORES["verde"],
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=8,
            relief="flat",
            cursor="hand2",
        )
        self.lbl_alerta.pack(anchor="e")
        self.lbl_alerta.bind("<Button-1>", lambda e: self.restaurar_janela_principal())

        barra_busca = tk.Frame(self.root, bg=CORES["bg_app"])
        barra_busca.pack(fill="x", padx=20, pady=(0, 14))

        busca_card = tk.Frame(
            barra_busca,
            bg=CORES["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=CORES["borda"],
        )
        busca_card.pack(fill="x")

        tk.Label(
            busca_card,
            text="Buscar por nome ou placa:",
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=12,
        ).pack(side="left")

        self.entry_busca = tk.Entry(
            busca_card,
            textvariable=self.var_busca,
            font=("Segoe UI", 11),
            bg=CORES["bg_input"],
            fg=CORES["texto"],
            insertbackground=CORES["texto"],
            relief="flat",
            bd=0,
        )
        self.entry_busca.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=12, ipady=6)

        tk.Button(
            busca_card,
            text="Limpar",
            command=self.limpar_busca,
            bg="#243041",
            fg=CORES["texto"],
            activebackground="#334155",
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(side="right", padx=12, pady=8)

        principal = tk.Frame(self.root, bg=CORES["bg_app"])
        principal.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.card_esquerda = self.criar_card_container(principal)
        self.card_esquerda.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.criar_cabecalho_card(self.card_esquerda, "Cadastros Pendentes", "Fichas aguardando ação")

        self.area_scroll_pendentes = tk.Frame(self.card_esquerda, bg=CORES["bg_card"])
        self.area_scroll_pendentes.pack(fill="both", expand=True, padx=10, pady=(2, 8))

        self.canvas_pendentes = tk.Canvas(
            self.area_scroll_pendentes,
            bg=CORES["bg_card"],
            highlightthickness=0,
            bd=0,
        )
        self.scroll_pendentes = tk.Scrollbar(
            self.area_scroll_pendentes,
            orient="vertical",
            command=self.canvas_pendentes.yview,
            bg="#1f2937",
            activebackground="#334155",
            troughcolor="#0b1220",
            highlightthickness=0,
            bd=0,
            relief="flat",
            width=12,
        )
        self.lista_pendentes = tk.Frame(self.canvas_pendentes, bg=CORES["bg_card"])

        self.lista_pendentes.bind(
            "<Configure>",
            lambda e: self.canvas_pendentes.configure(scrollregion=self.canvas_pendentes.bbox("all"))
        )
        self.canvas_pendentes.bind(
            "<Configure>",
            lambda e: self.canvas_pendentes.itemconfigure(self.canvas_window_pendentes, width=e.width)
        )

        self.canvas_window_pendentes = self.canvas_pendentes.create_window(
            (0, 0), window=self.lista_pendentes, anchor="nw"
        )
        self.canvas_pendentes.configure(yscrollcommand=self.scroll_pendentes.set)

        self.canvas_pendentes.pack(side="left", fill="both", expand=True)
        self.scroll_pendentes.pack(side="right", fill="y")
        self.canvas_pendentes.bind("<Enter>", self.ativar_scroll_pendentes)
        self.canvas_pendentes.bind("<Leave>", self.desativar_scroll_pendentes)

        self.card_central = self.criar_card_container(principal)
        self.card_central.pack(side="left", fill="both", expand=True, padx=10)

        self.criar_cabecalho_card(self.card_central, "Detalhes da Ficha", "Visualize dados e conclua o atendimento")

        self.area_scroll_central = tk.Frame(self.card_central, bg=CORES["bg_card"])
        self.area_scroll_central.pack(fill="both", expand=True, padx=14, pady=(4, 14))

        self.canvas_central = tk.Canvas(
            self.area_scroll_central,
            bg=CORES["bg_card"],
            highlightthickness=0,
            bd=0,
        )
        self.scroll_central = tk.Scrollbar(
            self.area_scroll_central,
            orient="vertical",
            command=self.canvas_central.yview,
            bg="#1f2937",
            activebackground="#334155",
            troughcolor="#0b1220",
            highlightthickness=0,
            bd=0,
            relief="flat",
            width=12,
        )
        self.conteudo_central = tk.Frame(self.canvas_central, bg=CORES["bg_card"])

        self.conteudo_central.bind(
            "<Configure>",
            lambda e: self.canvas_central.configure(scrollregion=self.canvas_central.bbox("all"))
        )
        self.canvas_central.bind(
            "<Configure>",
            lambda e: self.canvas_central.itemconfigure(self.canvas_window_central, width=e.width)
        )

        self.canvas_window_central = self.canvas_central.create_window(
            (0, 0), window=self.conteudo_central, anchor="nw"
        )
        self.canvas_central.configure(yscrollcommand=self.scroll_central.set)

        self.canvas_central.pack(side="left", fill="both", expand=True)
        self.scroll_central.pack(side="right", fill="y")
        self.canvas_central.bind("<Enter>", self.ativar_scroll_painel)
        self.canvas_central.bind("<Leave>", self.desativar_scroll_painel)

        self.texto_vazio = tk.Label(
            self.conteudo_central,
            text="Selecione um cadastro para visualizar a ficha.",
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 11),
            pady=20,
        )
        self.texto_vazio.pack(anchor="center")

        self.card_direita = self.criar_card_container(principal)
        self.card_direita.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.criar_cabecalho_card(self.card_direita, "Cadastros Realizados", "Fichas já concluídas")

        self.area_scroll_realizados = tk.Frame(self.card_direita, bg=CORES["bg_card"])
        self.area_scroll_realizados.pack(fill="both", expand=True, padx=10, pady=(2, 8))

        self.canvas_realizados = tk.Canvas(
            self.area_scroll_realizados,
            bg=CORES["bg_card"],
            highlightthickness=0,
            bd=0,
        )
        self.scroll_realizados = tk.Scrollbar(
            self.area_scroll_realizados,
            orient="vertical",
            command=self.canvas_realizados.yview,
            bg="#1f2937",
            activebackground="#334155",
            troughcolor="#0b1220",
            highlightthickness=0,
            bd=0,
            relief="flat",
            width=12,
        )
        self.lista_realizados = tk.Frame(self.canvas_realizados, bg=CORES["bg_card"])

        self.lista_realizados.bind(
            "<Configure>",
            lambda e: self.canvas_realizados.configure(scrollregion=self.canvas_realizados.bbox("all"))
        )
        self.canvas_realizados.bind(
            "<Configure>",
            lambda e: self.canvas_realizados.itemconfigure(self.canvas_window_realizados, width=e.width)
        )

        self.canvas_window_realizados = self.canvas_realizados.create_window(
            (0, 0), window=self.lista_realizados, anchor="nw"
        )
        self.canvas_realizados.configure(yscrollcommand=self.scroll_realizados.set)

        self.canvas_realizados.pack(side="left", fill="both", expand=True)
        self.scroll_realizados.pack(side="right", fill="y")
        self.canvas_realizados.bind("<Enter>", self.ativar_scroll_realizados)
        self.canvas_realizados.bind("<Leave>", self.desativar_scroll_realizados)

        rodape = tk.Frame(self.root, bg=CORES["bg_app"])
        rodape.pack(fill="x", side="bottom", padx=20, pady=(0, 10))

        self.lbl_empresa = tk.Label(
            rodape,
            text="BALTECH 2026 - TODOS OS DIREITOS RESERVADOS",
            bg=CORES["bg_app"],
            fg="#7dd3fc",
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        self.lbl_empresa.pack(anchor="center")
        self.lbl_empresa.bind("<Button-1>", self.abrir_site_baltech)
        self.lbl_empresa.bind("<Enter>", lambda e: self.lbl_empresa.config(fg="white"))
        self.lbl_empresa.bind("<Leave>", lambda e: self.lbl_empresa.config(fg=CORES["azul_claro"]))

    def criar_logo(self, parent):
        logo_path = resource_path(os.path.join("assets", "teg_teag.png"))
        if not os.path.exists(logo_path):
            return

        try:
            imagem = Image.open(logo_path)
            imagem.thumbnail((180, 80))
            self.logo_img = ImageTk.PhotoImage(imagem)

            tk.Label(
                parent,
                image=self.logo_img,
                bg=CORES["bg_app"],
            ).pack(side="left")
        except Exception as e:
            print(f"Erro ao carregar logo: {e}")

    def criar_card_container(self, parent):
        return tk.Frame(
            parent,
            bg=CORES["bg_card"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=CORES["borda"],
        )

    def criar_cabecalho_card(self, parent, titulo, subtitulo):
        cabecalho = tk.Frame(parent, bg=CORES["bg_card"])
        cabecalho.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            cabecalho,
            text=titulo,
            bg=CORES["bg_card"],
            fg=CORES["texto"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        tk.Label(
            cabecalho,
            text=subtitulo,
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

    def ativar_scroll_painel(self, event=None):
        self.canvas_central.bind_all("<MouseWheel>", self.rolar_painel_central)

    def desativar_scroll_painel(self, event=None):
        self.canvas_central.unbind_all("<MouseWheel>")

    def rolar_painel_central(self, event):
        try:
            self.canvas_central.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def piscar_barra_tarefas(self):
        try:
            self.root.update_idletasks()

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]

            FLASHW_TRAY = 0x00000002
            FLASHW_TIMERNOFG = 0x0000000C

            info = FLASHWINFO(
                ctypes.sizeof(FLASHWINFO),
                hwnd,
                FLASHW_TRAY | FLASHW_TIMERNOFG,
                0,
                0,
            )

            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception as e:
            print("Erro ao piscar barra de tarefas:", e)

    def parar_piscar_barra_tarefas(self):
        try:
            self.root.update_idletasks()

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]

            FLASHW_STOP = 0

            info = FLASHWINFO(
                ctypes.sizeof(FLASHWINFO),
                hwnd,
                FLASHW_STOP,
                0,
                0,
            )

            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception as e:
            print("Erro ao parar piscar barra de tarefas:", e)

    def mostrar_popup_alerta(self, mensagem):
        try:
            mostrar_alerta_canto(
                self.root,
                mensagem,
                on_click=self.restaurar_janela_principal,
            )
        except TypeError:
            mostrar_alerta_canto(self.root, mensagem)

    def restaurar_janela_principal(self):
        try:
            self.janela_oculta = False
    
            self.root.deiconify()
            self.root.state("normal")
            self.root.update_idletasks()
    
            try:
                self.root.state("zoomed")
            except Exception:
                pass
    
            self.root.lift()
            self.root.focus_force()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
    
            self.parar_piscar_barra_tarefas()
            parar_alerta(self.lbl_alerta, self)
        except Exception as e:
            print("Erro ao restaurar janela:", e)

    def ao_fechar_aplicacao(self):
        self.fechar_aplicacao_de_verdade()

    def limpar_busca(self):
        self.var_busca.set("")
        self.entry_busca.focus_set()

    def criar_campo_formulario(
        self,
        parent,
        rotulo,
        valor,
        linha,
        coluna,
        destaque=False,
        botao_copiar=False,
        callback_copiar=None,
        columnspan=1,
    ):
        card = tk.Frame(
            parent,
            bg=CORES["card_info"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=CORES["borda"],
            padx=12,
            pady=10,
        )
        card.grid(row=linha, column=coluna, columnspan=columnspan, sticky="nsew", padx=6, pady=6)

        tk.Label(
            card,
            text=rotulo,
            bg=CORES["card_info"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(anchor="w")

        linha_valor = tk.Frame(card, bg=CORES["card_info"])
        linha_valor.pack(fill="x", pady=(6, 0))

        tk.Label(
            linha_valor,
            text=str(valor),
            bg=CORES["card_info"],
            fg=CORES["azul_claro"] if destaque else CORES["texto"],
            font=("Segoe UI", 11, "bold" if destaque else "normal"),
            anchor="w",
            justify="left",
            wraplength=520 if columnspan > 1 else 230,
        ).pack(side="left", fill="x", expand=True)

        if botao_copiar:
            def ao_copiar():
                if callback_copiar:
                    callback_copiar()
                self.animar_botao_copiado(botao)

            botao = tk.Button(
                linha_valor,
                text="Copiar",
                bg=CORES["bg_hover"],
                fg=CORES["texto"],
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                padx=8,
                pady=4,
                cursor="hand2",
                command=ao_copiar,
            )
            botao.pack(side="right", padx=(8, 0))

    def limpar_painel_central(self):
        for widget in self.conteudo_central.winfo_children():
            widget.destroy()

        self.texto_vazio = tk.Label(
            self.conteudo_central,
            text="Selecione um cadastro para visualizar a ficha.",
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 11),
            pady=20,
        )
        self.texto_vazio.pack(anchor="center")
        self.cadastro_em_exibicao = None
        self.origem_em_exibicao = None
        self.var_smartcard.set("")
        self.canvas_central.yview_moveto(0)

    def confirmar_smartcard(self, event=None):
        valor = self.var_smartcard.get().strip().upper()[:10]
        self.var_smartcard.set(valor)

        if not valor:
            return

        self.entry_smartcard.configure(
            bg="#374151",
            fg="white",
            relief="solid",
            bd=1,
        )

    def editar_smartcard(self, event=None):
        valor_atual = self.var_smartcard.get()
        valor_tratado = valor_atual.upper()[:10]

        if valor_atual != valor_tratado:
            posicao = self.entry_smartcard.index(tk.INSERT)
            self.var_smartcard.set(valor_tratado)

            try:
                if posicao > len(valor_tratado):
                    posicao = len(valor_tratado)
                self.entry_smartcard.icursor(posicao)
            except Exception:
                pass

        self.entry_smartcard.configure(
            bg=CORES["bg_input"],
            fg=CORES["texto"],
            relief="solid",
            bd=1,
        )

    def animar_botao_copiado(self, botao):
        texto_original = botao.cget("text")
        bg_original = botao.cget("bg")
        fg_original = botao.cget("fg")

        botao.config(
            text="Copiado",
            bg=CORES["verde"],
            fg="white",
            state="disabled",
        )

        self.root.after(
            1200,
            lambda: botao.config(
                text=texto_original,
                bg=bg_original,
                fg=fg_original,
                state="normal",
            )
        )

    def copiar_smartcard_digitado(self):
        copiar_texto(self.root, self.var_smartcard.get().strip().upper(), "SmartCard")

    def selecionar_card_lista(self, origem, cadastro, card_widget):
        cor_normal = CORES["card_info"]
        cor_selecionado = CORES["card_info_2"]

        def resetar_card(card):
            if not card or not card.winfo_exists():
                return
            try:
                card.configure(bg=cor_normal, highlightbackground=CORES["borda"])
                for filho in card.winfo_children():
                    if isinstance(filho, (tk.Frame, tk.Label)):
                        try:
                            if filho.cget("bg") not in (CORES["amarelo"], CORES["verde"]):
                                filho.configure(bg=cor_normal)
                        except Exception:
                            pass
                        for neto in getattr(filho, "winfo_children", lambda: [])():
                            try:
                                if isinstance(neto, (tk.Frame, tk.Label)) and neto.cget("bg") not in (CORES["amarelo"], CORES["verde"]):
                                    neto.configure(bg=cor_normal)
                            except Exception:
                                pass
            except Exception:
                pass

        def destacar_card(card):
            if not card or not card.winfo_exists():
                return
            try:
                card.configure(bg=cor_selecionado, highlightbackground=CORES["azul"])
                for filho in card.winfo_children():
                    if isinstance(filho, (tk.Frame, tk.Label)):
                        try:
                            if filho.cget("bg") not in (CORES["amarelo"], CORES["verde"]):
                                filho.configure(bg=cor_selecionado)
                        except Exception:
                            pass
                        for neto in getattr(filho, "winfo_children", lambda: [])():
                            try:
                                if isinstance(neto, (tk.Frame, tk.Label)) and neto.cget("bg") not in (CORES["amarelo"], CORES["verde"]):
                                    neto.configure(bg=cor_selecionado)
                            except Exception:
                                pass
            except Exception:
                pass

        if origem == "pendente":
            resetar_card(self.card_pendente_selecionado)
            self.card_pendente_selecionado = card_widget
        else:
            resetar_card(self.card_realizado_selecionado)
            self.card_realizado_selecionado = card_widget

        destacar_card(card_widget)
        self.exibir_detalhes(cadastro, origem=origem)

    def criar_card_ficha(self, parent, cadastro, origem="pendente"):
        status_cor = CORES["amarelo"] if origem == "pendente" else CORES["verde"]
        titulo_status = "PENDENTE" if origem == "pendente" else "REALIZADO"
        placa = cadastro.get("placa", "Sem placa") or "Sem placa"
        motorista = cadastro.get("motorista_nome", "Motorista não informado") or "Motorista não informado"
        empresa = cadastro.get("empresa_motorista", "Empresa não informada") or "Empresa não informada"

        cor_normal = CORES["card_info"]
        cor_hover = "#1a2438"

        card = tk.Frame(
            parent,
            bg=cor_normal,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=CORES["borda"],
            padx=9,
            pady=7,
            cursor="hand2",
        )
        card.pack(fill="x", padx=1, pady=4)

        topo = tk.Frame(card, bg=cor_normal)
        topo.pack(fill="x")

        lbl_placa = tk.Label(
            topo,
            text=f"🪪 {placa}",
            bg=cor_normal,
            fg=CORES["azul_claro"],
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        lbl_placa.pack(side="left")

        lbl_status = tk.Label(
            topo,
            text=titulo_status,
            bg=status_cor,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=2,
            cursor="hand2",
        )
        lbl_status.pack(side="right")

        corpo = tk.Frame(card, bg=cor_normal)
        corpo.pack(fill="x", pady=(5, 0))

        lbl_motorista = tk.Label(
            corpo,
            text=motorista,
            bg=cor_normal,
            fg=CORES["texto"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            cursor="hand2",
        )
        lbl_motorista.pack(fill="x")

        lbl_empresa = tk.Label(
            corpo,
            text=f"🏢 {empresa}",
            bg=cor_normal,
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9),
            anchor="w",
            cursor="hand2",
        )
        lbl_empresa.pack(fill="x", pady=(1, 0))

        rodape = tk.Frame(card, bg=cor_normal)
        rodape.pack(anchor="e", pady=(5, 0))

        btn_ver = tk.Button(
            rodape,
            text="Ver ficha",
            bg="#243041",
            fg=CORES["texto"],
            activebackground="#334155",
            activeforeground="white",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self.exibir_janela_ficha(cadastro, origem),
        )
        btn_ver.pack(side="right")

        def aplicar_cores(bg):
            try:
                card.configure(bg=bg)
                topo.configure(bg=bg)
                corpo.configure(bg=bg)
                rodape.configure(bg=bg)
                lbl_placa.configure(bg=bg)
                lbl_motorista.configure(bg=bg)
                lbl_empresa.configure(bg=bg)
            except Exception:
                pass

        def hover_on(event=None):
            if card not in (self.card_pendente_selecionado, self.card_realizado_selecionado):
                aplicar_cores(cor_hover)

        def hover_off(event=None):
            if card not in (self.card_pendente_selecionado, self.card_realizado_selecionado):
                aplicar_cores(cor_normal)

        def clique_card(event=None):
            self.selecionar_card_lista(origem, cadastro, card)

        widgets_clicaveis = [card, topo, corpo, lbl_placa, lbl_status, lbl_motorista, lbl_empresa]

        for widget in widgets_clicaveis:
            widget.bind("<Button-1>", clique_card)
            widget.bind("<Enter>", hover_on)
            widget.bind("<Leave>", hover_off)

        return card

    def exibir_detalhes(self, cadastro, origem="pendente"):
        self.cadastro_em_exibicao = cadastro
        self.origem_em_exibicao = origem
        self.var_smartcard.set(cadastro.get("smartcard", ""))
    
        for widget in self.conteudo_central.winfo_children():
            widget.destroy()
    
        nota_fiscal = cadastro.get("nota_fiscal") or "N/A"
        concluido_em = cadastro.get("concluido_em", "Ainda não concluído")
    
        topo_ficha = tk.Frame(self.conteudo_central, bg=CORES["bg_card"])
        topo_ficha.pack(fill="x", pady=(0, 10))
    
        status_cor = CORES["amarelo"] if origem == "pendente" else CORES["verde"]
        tk.Label(
            topo_ficha,
            text=origem.upper(),
            bg=status_cor,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
        ).pack(side="right")
    
        grade_dados = tk.Frame(self.conteudo_central, bg=CORES["bg_card"])
        grade_dados.pack(fill="x")
        grade_dados.grid_columnconfigure(0, weight=1)
        grade_dados.grid_columnconfigure(1, weight=1)
    
        self.criar_campo_formulario(
            grade_dados,
            "🚚 Placa do veículo",
            cadastro.get("placa", "N/A"),
            0,
            0,
            destaque=True,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, cadastro.get("placa", ""), "Placa"),
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "🏢 Empresa do motorista",
            cadastro.get("empresa_motorista", "N/A"),
            0,
            1,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                cadastro.get("empresa_motorista", ""),
                "Empresa do motorista",
            ),
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "🪪 CNH",
            cadastro.get("motorista_cnh", "N/A"),
            1,
            0,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, cadastro.get("motorista_cnh", ""), "CNH"),
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "Nota fiscal",
            nota_fiscal,
            1,
            1,
            botao_copiar=nota_fiscal != "N/A",
            callback_copiar=lambda: copiar_texto(self.root, nota_fiscal, "Nota fiscal"),
        )
    
        card_motorista = tk.Frame(
            grade_dados,
            bg=CORES["card_info_2"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=CORES["borda"],
            padx=12,
            pady=10,
        )
        card_motorista.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
    
        topo_motorista = tk.Frame(card_motorista, bg=CORES["card_info_2"])
        topo_motorista.pack(fill="x")
    
        tk.Label(
            topo_motorista,
            text="👤 Motorista",
            bg=CORES["card_info_2"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
    
        tk.Button(
            topo_motorista,
            text="Mais informações",
            command=self.mostrar_info_motorista,
            bg="#243b53",
            fg="white",
            activebackground="#2f4c6e",
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="right")
    
        nome_linha = tk.Frame(card_motorista, bg=CORES["card_info_2"])
        nome_linha.pack(fill="x", pady=(8, 0))
    
        tk.Label(
            nome_linha,
            text=cadastro.get("motorista_nome", "N/A"),
            bg=CORES["card_info_2"],
            fg=CORES["texto"],
            font=("Segoe UI", 11),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
    
        botao_copiar_motorista = tk.Button(
            nome_linha,
            text="Copiar",
            bg=CORES["bg_hover"],
            fg=CORES["texto"],
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
        )
        botao_copiar_motorista.config(
            command=lambda: [
                copiar_texto(self.root, cadastro.get("motorista_nome", ""), "Motorista"),
                self.animar_botao_copiado(botao_copiar_motorista),
            ]
        )
        botao_copiar_motorista.pack(side="right", padx=(8, 0))
    
        self.criar_campo_formulario(
            grade_dados,
            "Serviço no terminal",
            cadastro.get("servico_terminal", "N/A"),
            3,
            0,
            columnspan=2,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                cadastro.get("servico_terminal", ""),
                "Serviço no terminal",
            ),
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "Data de recebimento",
            formatar_data_br(cadastro.get("data", "N/A")),
            4,
            0,
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "CPF",
            limpar_documento(cadastro.get("motorista_cpf", "N/A")),
            4,
            1,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                limpar_documento(cadastro.get("motorista_cpf", "")),
                "CPF",
            ),
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "Data de conclusão",
            formatar_data_br(concluido_em),
            5,
            0,
        )
    
        self.criar_campo_formulario(
            grade_dados,
            "SmartCard atual",
            cadastro.get("smartcard", "Não informado") or "Não informado",
            5,
            1,
            destaque=True,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                cadastro.get("smartcard", "Não informado") or "Não informado",
                "SmartCard atual",
            ),
        )
    
        separador = tk.Frame(self.conteudo_central, bg=CORES["borda"], height=1)
        separador.pack(fill="x", pady=12)
    
        bloco_smartcard = tk.Frame(self.conteudo_central, bg=CORES["bg_card"])
        bloco_smartcard.pack(fill="x", pady=(0, 12))
    
        tk.Label(
            bloco_smartcard,
            text="SmartCard:",
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 10, "bold"),
            width=20,
            anchor="w",
        ).pack(side="left")
    
        self.entry_smartcard = tk.Entry(
            bloco_smartcard,
            textvariable=self.var_smartcard,
            font=("Segoe UI", 11),
            bg=CORES["bg_input"],
            fg=CORES["texto"],
            insertbackground=CORES["texto"],
            relief="solid",
            bd=1,
            width=24,
        )
        self.entry_smartcard.pack(side="left", padx=(0, 10), ipady=6)
        self.entry_smartcard.bind("<Return>", self.confirmar_smartcard)
        self.entry_smartcard.bind("<KeyRelease>", self.editar_smartcard)
        self.entry_smartcard.bind("<Button-1>", self.editar_smartcard)
    
        botao_copiar_smartcard = tk.Button(
            bloco_smartcard,
            text="Copiar",
            bg=CORES["bg_hover"],
            fg=CORES["texto"],
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        )
        botao_copiar_smartcard.config(
            command=lambda: [
                self.copiar_smartcard_digitado(),
                self.animar_botao_copiado(botao_copiar_smartcard),
            ]
        )
        botao_copiar_smartcard.pack(side="left")
    
        tk.Label(
            self.conteudo_central,
            text="Para concluir a ficha, o usuário deve informar um SmartCard válido.",
            bg=CORES["bg_card"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 12))
    
        bloco_acoes = tk.Frame(self.conteudo_central, bg=CORES["bg_card"])
        bloco_acoes.pack(fill="x", pady=(12, 0))
    
        if origem == "pendente":
            tk.Button(
                bloco_acoes,
                text="Marcar como concluído",
                command=self.marcar_como_concluido,
                bg=CORES["verde"],
                fg="white",
                activebackground="#16a34a",
                activeforeground="white",
                font=("Segoe UI", 10, "bold"),
                relief="flat",
                padx=16,
                pady=8,
                cursor="hand2",
            ).pack(side="right")
        else:
            tk.Label(
                bloco_acoes,
                text="Ficha já concluída.",
                bg=CORES["bg_card"],
                fg=CORES["verde"],
                font=("Segoe UI", 10, "bold"),
            ).pack(side="right")
    
        self.canvas_central.yview_moveto(0)
        
    def mostrar_info_motorista(self):
        cadastro = self.cadastro_em_exibicao
        if not cadastro:
            return

        janela = tk.Toplevel(self.root)
        janela.title("Informações do Motorista")
        janela.geometry("700x520")
        janela.minsize(700, 520)
        janela.configure(bg=CORES["bg_card"])
        janela.transient(self.root)
        janela.grab_set()

        topo = tk.Frame(janela, bg=CORES["bg_top"])
        topo.pack(fill="x", padx=16, pady=12)

        tk.Label(
            topo,
            text=cadastro.get("placa", "N/A"),
            bg=CORES["bg_top"],
            fg=CORES["texto"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        corpo = tk.Frame(janela, bg=CORES["bg_card"], padx=16, pady=16)
        corpo.pack(fill="both", expand=True)
        corpo.grid_columnconfigure(0, weight=1)
        corpo.grid_columnconfigure(1, weight=1)

        self.criar_campo_formulario(
            corpo,
            "Nome",
            cadastro.get("motorista_nome", "N/A"),
            0,
            0,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, cadastro.get("motorista_nome", ""), "Nome"),
        )
        self.criar_campo_formulario(
            corpo,
            "CPF",
            limpar_documento(cadastro.get("motorista_cpf", "")),
            0,
            1,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, limpar_documento(cadastro.get("motorista_cpf", "")), "CPF"),
        )
        self.criar_campo_formulario(
            corpo,
            "RG",
            limpar_documento(cadastro.get("motorista_rg", "")),
            1,
            0,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, limpar_documento(cadastro.get("motorista_rg", "")), "RG"),
        )
        self.criar_campo_formulario(
            corpo,
            "CNH",
            cadastro.get("motorista_cnh", "N/A"),
            1,
            1,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(self.root, cadastro.get("motorista_cnh", ""), "CNH"),
        )
        self.criar_campo_formulario(
            corpo,
            "Validade CNH",
            formatar_data_br(cadastro.get("motorista_validade_cnh", "")),
            2,
            0,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                formatar_data_br(cadastro.get("motorista_validade_cnh", "")),
                "Validade CNH",
            ),
        )
        self.criar_campo_formulario(
            corpo,
            "Data de nascimento",
            formatar_data_br(cadastro.get("motorista_data_nascimento", "")),
            2,
            1,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                formatar_data_br(cadastro.get("motorista_data_nascimento", "")),
                "Data de nascimento",
            ),
        )
        self.criar_campo_formulario(
            corpo,
            "Telefone",
            cadastro.get("motorista_telefone", "N/A"),
            3,
            0,
            botao_copiar=True,
            callback_copiar=lambda: copiar_texto(
                self.root,
                cadastro.get("motorista_telefone", ""),
                "Telefone",
            ),
            columnspan=2,
        )

        rodape = tk.Frame(janela, bg=CORES["bg_card"], padx=16, pady=12)
        rodape.pack(fill="x")

        tk.Button(
            rodape,
            text="Fechar",
            command=janela.destroy,
            bg=CORES["azul"],
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

    def smartcard_valido(self, valor):
        return smartcard_valido(valor)

    def obter_pendente_selecionado(self):
        if self.origem_em_exibicao == "pendente" and self.cadastro_em_exibicao:
            return self.cadastro_em_exibicao
        return None

    def obter_realizado_selecionado(self):
        if self.origem_em_exibicao == "realizado" and self.cadastro_em_exibicao:
            return self.cadastro_em_exibicao
        return None

    def ao_selecionar_pendente(self, event=None):
        cadastro = self.obter_pendente_selecionado()
        if cadastro:
            self.exibir_detalhes(cadastro, origem="pendente")

    def ao_selecionar_realizado(self, event=None):
        cadastro = self.obter_realizado_selecionado()
        if cadastro:
            self.exibir_detalhes(cadastro, origem="realizado")

    def abrir_ficha_pendente(self, event=None):
        cadastro = self.obter_pendente_selecionado()
        if not cadastro:
            messagebox.showwarning("Aviso", "Selecione um cadastro pendente para abrir a ficha.")
            return
        self.exibir_janela_ficha(cadastro, "pendente")
        parar_alerta(self.lbl_alerta, self)

    def abrir_ficha_realizado(self, event=None):
        cadastro = self.obter_realizado_selecionado()
        if not cadastro:
            messagebox.showwarning("Aviso", "Selecione um cadastro realizado para abrir a ficha.")
            return
        self.exibir_janela_ficha(cadastro, "realizado")

    def exibir_janela_ficha(self, cadastro, origem):
        janela = tk.Toplevel(self.root)
        janela.title(f"Ficha do Cadastro - {cadastro.get('motorista_nome', 'N/A')}")
        janela.geometry("860x720")
        janela.minsize(820, 680)
        janela.configure(bg=CORES["bg_card"])
        janela.transient(self.root)
        janela.grab_set()

        topo = tk.Frame(janela, bg=CORES["bg_top"])
        topo.pack(fill="x", pady=12, padx=14)

        tk.Label(
            topo,
            text="Ficha do Cadastro",
            bg=CORES["bg_top"],
            fg=CORES["texto"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        tk.Label(
            topo,
            text=f"Status: {origem.title()} | Setor: {traduzir_setor(cadastro.get('tipo_operacao', ''))}",
            bg=CORES["bg_top"],
            fg=CORES["texto_secundario"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        corpo = tk.Frame(janela, bg=CORES["bg_card"], padx=18, pady=18)
        corpo.pack(fill="both", expand=True)

        campos = [
            ("Setor", traduzir_setor(cadastro.get("tipo_operacao", ""))),
            ("Placa", cadastro.get("placa", "N/A")),
            ("Motorista", cadastro.get("motorista_nome", "N/A")),
            ("Empresa do motorista", cadastro.get("empresa_motorista", "N/A")),
            ("CNH", cadastro.get("motorista_cnh", "N/A")),
            ("Validade CNH", formatar_data_br(cadastro.get("motorista_validade_cnh", "N/A"))),
            ("Data de nascimento", formatar_data_br(cadastro.get("motorista_data_nascimento", "N/A"))),
            ("CPF", limpar_documento(cadastro.get("motorista_cpf", "N/A"))),
            ("RG", limpar_documento(cadastro.get("motorista_rg", "N/A"))),
            ("Telefone", cadastro.get("motorista_telefone", "N/A")),
            ("Nota Fiscal", cadastro.get("nota_fiscal", "N/A") or "N/A"),
            ("Serviço", cadastro.get("servico_terminal", "N/A")),
            ("Empresa solicitante", cadastro.get("empresa_solicitante", "N/A")),
            ("Data de recebimento", formatar_data_br(cadastro.get("data", "N/A"))),
            ("Data de conclusão", formatar_data_br(cadastro.get("concluido_em", "Ainda não concluído"))),
            ("SmartCard", cadastro.get("smartcard", "Não informado")),
        ]

        for rotulo, valor in campos:
            bloco = tk.Frame(corpo, bg=CORES["bg_card"])
            bloco.pack(fill="x", pady=4)

            tk.Label(
                bloco,
                text=f"{rotulo}:",
                bg=CORES["bg_card"],
                fg=CORES["texto_secundario"],
                font=("Segoe UI", 10, "bold"),
                width=18,
                anchor="w",
            ).pack(side="left")

            tk.Label(
                bloco,
                text=str(valor),
                bg=CORES["bg_card"],
                fg=CORES["texto"],
                font=("Segoe UI", 10),
                anchor="w",
                justify="left",
                wraplength=420,
            ).pack(side="left", fill="x", expand=True)

        rodape = tk.Frame(janela, bg=CORES["bg_card"], padx=18, pady=14)
        rodape.pack(fill="x")

        tk.Button(
            rodape,
            text="Mais informações do motorista",
            command=lambda: self.mostrar_info_motorista_externo(cadastro),
            bg="#1e3a8a",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            rodape,
            text="Fechar",
            command=janela.destroy,
            bg=CORES["azul"],
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
        ).pack(side="right")

    def mostrar_info_motorista_externo(self, cadastro):
        self.cadastro_em_exibicao = cadastro
        self.mostrar_info_motorista()

    def marcar_como_concluido(self):
        if not self.cadastro_em_exibicao or self.origem_em_exibicao != "pendente":
            messagebox.showwarning("Aviso", "Selecione uma ficha pendente para concluir.")
            return
    
        smartcard_digitado = self.var_smartcard.get().strip()
    
        if not smartcard_valido(smartcard_digitado):
            messagebox.showerror(
                "SmartCard inválido",
                "Informe um SmartCard válido para concluir a ficha.",
            )
            self.entry_smartcard.focus_set()
            return
    
        visitante_id = self.cadastro_em_exibicao.get("id")
        if not visitante_id:
            messagebox.showerror("Erro", "Não foi possível identificar o cadastro selecionado.")
            return
    
        payload = {
            "status": "realizado",
            "smartcard": smartcard_digitado,
            "concluido_em": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
    
        try:
            sucesso = self.service.client.atualizar_visitante(visitante_id, payload)
    
            if not sucesso:
                messagebox.showerror(
                    "Erro",
                    "Não foi possível concluir a ficha no Firebase.",
                )
                return
    
            self.cadastro_em_exibicao["status"] = "realizado"
            self.cadastro_em_exibicao["smartcard"] = smartcard_digitado
            self.cadastro_em_exibicao["concluido_em"] = payload["concluido_em"]
    
            self.sincronizar_com_firebase(exibir_alertas=False)
    
            messagebox.showinfo("Sucesso", "Ficha marcada como concluída com sucesso.")
    
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao concluir ficha: {e}")

    def ativar_scroll_pendentes(self, event=None):
        self.canvas_pendentes.bind_all("<MouseWheel>", self.rolar_pendentes)

    def desativar_scroll_pendentes(self, event=None):
        self.canvas_pendentes.unbind_all("<MouseWheel>")

    def rolar_pendentes(self, event):
        try:
            self.canvas_pendentes.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def ativar_scroll_realizados(self, event=None):
        self.canvas_realizados.bind_all("<MouseWheel>", self.rolar_realizados)

    def desativar_scroll_realizados(self, event=None):
        self.canvas_realizados.unbind_all("<MouseWheel>")

    def rolar_realizados(self, event):
        try:
            self.canvas_realizados.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def abrir_site_baltech(self, event=None):
        try:
            webbrowser.open("https://baltech-tau.vercel.app/")
        except Exception as e:
            print("Erro ao abrir site da BalTech:", e)
            messagebox.showerror(
                "Erro",
                "Não foi possível abrir o site da BalTech."
            )


def main():
    if not garantir_instancia_unica():
        ativar_janela_existente()

        aviso_root = tk.Tk()
        aviso_root.withdraw()
        messagebox.showwarning(
            "Aplicativo já aberto",
            "O Controle Diversos já está em execução."
        )
        aviso_root.destroy()
        return

    root = tk.Tk()
    configurar_icone_janela(root)
    SistemaCadastrosApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()