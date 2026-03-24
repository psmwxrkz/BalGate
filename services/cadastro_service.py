from datetime import datetime
from api.client import FirebaseClient

class CadastroService:
    def __init__(self):
        self.client = FirebaseClient()

        # ✅ LOGIN AUTOMÁTICO NO FIREBASE
        # Configure aqui o email/senha do usuário de serviço criado no Firebase Authentication
        self.client.autenticar(
            "paulo_matos@tegporto.com.br",
            "qwerty12"
        )

        self.cadastros_pendentes = []
        self.cadastros_realizados = []

    # ------------------------------------------------------------------
    #  Atualiza cadastros com base na lista de visitantes do Firebase
    # ------------------------------------------------------------------
    def atualizar_fichas_api(self, visitantes=None):
        if visitantes is None:
            visitantes, _ = self.client.buscar_visitantes()

        novos_pendentes = []
        novos_realizados = []

        ids_anteriores = {c.get("id") for c in self.cadastros_pendentes}
        novos_cadastros = []

        for visitante in visitantes:
            cadastro = self.converter_visitante_para_cadastro(visitante)

            if cadastro["status"] == "realizado":
                novos_realizados.append(cadastro)
            else:
                novos_pendentes.append(cadastro)
                if cadastro["id"] not in ids_anteriores:
                    novos_cadastros.append(cadastro)

        self.cadastros_pendentes = novos_pendentes
        self.cadastros_realizados = novos_realizados

        return novos_cadastros

    # ------------------------------------------------------------------
    #  FILTRO DE BUSCA
    # ------------------------------------------------------------------
    def filtrar(self, termo):
        termo = (termo or "").strip().lower()

        if not termo:
            return self.cadastros_pendentes, self.cadastros_realizados

        def match(c):
            return (
                termo in str(c.get("placa", "")).lower()
                or termo in str(c.get("motorista_nome", "")).lower()
                or termo in str(c.get("empresa_motorista", "")).lower()
            )

        return (
            [c for c in self.cadastros_pendentes if match(c)],
            [c for c in self.cadastros_realizados if match(c)],
        )

    # ------------------------------------------------------------------
    #  CONVERTE DADOS DO FIREBASE PARA O PADRÃO DO SISTEMA
    # ------------------------------------------------------------------
    def converter_visitante_para_cadastro(self, v):

        def pick(*keys, default=""):
            for k in keys:
                if v.get(k) not in (None, "", []):
                    valor = v.get(k)
                    return valor.upper() if isinstance(valor, str) else valor
            return default.upper() if isinstance(default, str) else default

        status_raw = str(v.get("status", "")).lower()

        cadastro = {
            "id": v.get("id", ""),

            # ✅ PLACA
            "placa": pick("placa"),

            # ✅ MOTORISTA
            "motorista_nome": pick("motorista_nome", "nome"),
            "motorista_cnh": pick("motorista_cnh", "cnh"),
            "motorista_validade_cnh": pick("motorista_validade_cnh", "validadeCnh"),
            "motorista_categoria_cnh": pick("categoriaCnh"),
            "motorista_data_nascimento": pick("dataNascimento"),
            "motorista_cpf": pick("motorista_cpf", "documento"),
            "motorista_rg": pick("motorista_rg", "rg"),
            "motorista_telefone": pick("motorista_telefone", "telefone"),

            # ✅ EMPRESA
            "empresa_motorista": pick("empresa_motorista", "empresa"),

            # ✅ SETOR / OPERAÇÃO
            "tipo_operacao": pick("tipo_operacao", "destino"),

            # ✅ SERVIÇO NO TERMINAL
            "servico_terminal": pick("servico_terminal", "motivo"),

            # ✅ NOTA FISCAL
            "nota_fiscal": pick("nota_fiscal", "notaFiscal"),

            # ✅ DATAS
            "data": pick("data", "dataEntrada"),
            "concluido_em": pick("concluido_em", "concluidoEm"),

            # ✅ SMARTCARD
            "smartcard": pick("smartcard"),

            # ✅ STATUS PADRONIZADO
            "status": "realizado" if status_raw in ("realizado", "concluido", "saiu") else "pendente",
        }

        return cadastro

    # ------------------------------------------------------------------
    #  MARCAR CADASTRO COMO CONCLUÍDO
    # ------------------------------------------------------------------
    def concluir_cadastro(self, cadastro, smartcard):
        visitante_id = cadastro.get("id")
        if not visitante_id:
            return cadastro

        atualizacao = {
            "status": "realizado",
            "smartcard": smartcard,
            "concluidoEm": datetime.now().isoformat()
        }

        sucesso = self.client.atualizar_visitante(visitante_id, atualizacao)

        if sucesso:
            cadastro["status"] = "realizado"
            cadastro["smartcard"] = smartcard
            cadastro["concluido_em"] = atualizacao["concluidoEm"]

        return cadastro
