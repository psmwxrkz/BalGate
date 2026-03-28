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
    # Atualiza cadastros com base na lista combinada do Firebase
    # (visitantes + consumos)
    # ------------------------------------------------------------------
    def atualizar_fichas_api(self, visitantes=None):
        # compatibilidade com o nome antigo do parâmetro
        # agora "visitantes" pode ser a lista combinada inteira
        if visitantes is None:
            visitantes, _ = self.client.buscar_visitantes()

        novos_pendentes = []
        novos_realizados = []

        ids_anteriores = {
            (c.get("origem"), c.get("id"))
            for c in self.cadastros_pendentes
        }
        novos_cadastros = []

        for registro in visitantes:
            origem = registro.get("origem", "visitantes")

            if origem == "consumos":
                cadastro = self.converter_consumo_para_cadastro(registro)
            else:
                cadastro = self.converter_visitante_para_cadastro(registro)

            if cadastro["status"] == "realizado":
                novos_realizados.append(cadastro)
            else:
                novos_pendentes.append(cadastro)

                chave = (cadastro.get("origem"), cadastro.get("id"))
                if chave not in ids_anteriores:
                    novos_cadastros.append(cadastro)

        self.cadastros_pendentes = novos_pendentes
        self.cadastros_realizados = novos_realizados

        return novos_cadastros

    # ------------------------------------------------------------------
    # FILTRO DE BUSCA
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
    # AUXILIARES
    # ------------------------------------------------------------------
    def _pick(self, origem, *keys, default=""):
        for k in keys:
            if origem.get(k) not in (None, "", []):
                valor = origem.get(k)
                return valor.upper() if isinstance(valor, str) else valor
        return default.upper() if isinstance(default, str) else default

    def _normalizar_status(self, status_raw):
        status = str(status_raw or "").strip().lower()

        if status in (
            "realizado",
            "concluido",
            "concluído",
            "saiu",
            "finalizado",
            "liberado",
        ):
            return "realizado"

        return "pendente"

    def _obter_primeiro_individuo(self, consumo):
        individuos = consumo.get("individuos") or []

        if isinstance(individuos, list):
            for item in individuos:
                if isinstance(item, dict):
                    return item

        if isinstance(individuos, dict):
            for chave in sorted(individuos.keys(), key=lambda x: str(x)):
                item = individuos.get(chave)
                if isinstance(item, dict):
                    return item

        return {}

    # ------------------------------------------------------------------
    # CONVERTE VISITANTE PARA O PADRÃO DO SISTEMA
    # ------------------------------------------------------------------
        
    def converter_visitante_para_cadastro(self, v):
        status_balgate = v.get("status_balgate", "")
        status_base = v.get("status", "")

        status_normalizado = (
            self._normalizar_status(status_balgate)
            if str(status_balgate).strip()
            else self._normalizar_status(status_base)
        )

        concluido_em = self._pick(v, "concluido_em", "concluidoEm")

        if status_normalizado == "realizado" and not concluido_em:
            concluido_em = datetime.now().isoformat()

        cadastro = {
            "id": v.get("id", ""),
            "origem": "visitantes",

            "placa": self._pick(v, "placa"),

            "motorista_nome": self._pick(v, "motorista_nome", "nome"),
            "motorista_cnh": self._pick(v, "motorista_cnh", "cnh"),
            "motorista_validade_cnh": self._pick(v, "motorista_validade_cnh", "validadeCnh"),
            "motorista_categoria_cnh": self._pick(v, "categoriaCnh"),
            "motorista_data_nascimento": self._pick(v, "dataNascimento"),
            "motorista_cpf": self._pick(v, "motorista_cpf", "documento"),
            "motorista_rg": self._pick(v, "motorista_rg", "rg"),
            "motorista_telefone": self._pick(v, "motorista_telefone", "telefone"),

            "empresa_motorista": self._pick(v, "empresa_motorista", "empresa"),
            "empresa_solicitante": self._pick(v, "empresa_solicitante", "destino"),

            "tipo_operacao": self._pick(v, "tipo_operacao"),

            "servico_terminal": self._pick(v, "servico_terminal", "motivo"),

            "nota_fiscal": self._pick(v, "nota_fiscal", "notaFiscal"),

            "data": self._pick(v, "data", "dataEntrada"),
            "concluido_em": concluido_em,

            "smartcard": self._pick(v, "smartcard"),

            "status": status_normalizado,
            "status_balgate": self._pick(v, "status_balgate"),
        }

        return cadastro
                        
    # ------------------------------------------------------------------
    # CONVERTE CONSUMO PARA O PADRÃO DO SISTEMA
    # ------------------------------------------------------------------
    def converter_consumo_para_cadastro(self, c):
        individuo = self._obter_primeiro_individuo(c)

        status_balgate = c.get("status_balgate", "")
        status_base = (
            c.get("status")
            or individuo.get("status")
            or ""
        )

        status_normalizado = (
            self._normalizar_status(status_balgate)
            if str(status_balgate).strip()
            else self._normalizar_status(status_base)
        )

        empresa_motorista = (
            self._pick(individuo, "empresa_motorista", "empresa")
            or self._pick(c, "empresa_motorista", "empresa")
        )

        tipo_operacao = (
            self._pick(c, "tipo_operacao", "destino", "tipoServico")
            or self._pick(individuo, "tipo_operacao", "destino")
        )

        servico_terminal = (
            self._pick(c, "servico_terminal", "motivo", "tipoServico", "produto", "terminal")
            or self._pick(individuo, "servico_terminal", "motivo")
        )

        data_recebimento = (
            self._pick(c, "dataEntrada", "data")
            or self._pick(individuo, "dataEntrada", "data")
        )

        concluido_em = self._pick(c, "concluido_em", "concluidoEm")

        if status_normalizado == "realizado" and not concluido_em:
            concluido_em = datetime.now().isoformat()

        cadastro = {
            "id": c.get("id", ""),
            "origem": "consumos",

            "placa": self._pick(c, "placa"),

            "motorista_nome": self._pick(individuo, "motorista_nome", "nome"),
            "motorista_cnh": self._pick(individuo, "motorista_cnh", "cnh"),
            "motorista_validade_cnh": self._pick(individuo, "motorista_validade_cnh", "validadeCnh"),
            "motorista_categoria_cnh": self._pick(individuo, "motorista_categoria_cnh", "categoriaCnh"),
            "motorista_data_nascimento": self._pick(individuo, "motorista_data_nascimento", "dataNascimento"),
            "motorista_cpf": self._pick(individuo, "motorista_cpf", "documento"),
            "motorista_rg": self._pick(individuo, "motorista_rg", "rg"),
            "motorista_telefone": self._pick(individuo, "motorista_telefone", "telefone"),

            "empresa_motorista": empresa_motorista,

            "tipo_operacao": tipo_operacao,

            "servico_terminal": servico_terminal,

            "nota_fiscal": self._pick(c, "nota_fiscal", "notaFiscal"),

            "data": data_recebimento,
            "concluido_em": concluido_em,

            "smartcard": self._pick(c, "smartcard"),

            "status": status_normalizado,
            "status_balgate": self._pick(c, "status_balgate"),

            "navio": self._pick(c, "navio"),
            "produto": self._pick(c, "produto"),
            "terminal": self._pick(c, "terminal"),
            "veiculo": self._pick(c, "veiculo"),
            "vigilante": self._pick(c, "vigilante"),
            "credencial": self._pick(individuo, "credencial"),
        }

        return cadastro
        
    # ------------------------------------------------------------------
    # MARCAR CADASTRO COMO CONCLUÍDO
    # ------------------------------------------------------------------
    def concluir_cadastro(self, cadastro, smartcard):
        registro_id = cadastro.get("id")
        origem = cadastro.get("origem", "visitantes")

        if not registro_id:
            return cadastro

        agora = datetime.now().isoformat()

        atualizacao = {
            "status_balgate": "realizado",
            "smartcard": smartcard,
            "concluidoEm": agora,
            "concluido_no_sistema": True,
        }

        sucesso = self.client.atualizar_registro(origem, registro_id, atualizacao)

        if sucesso:
            cadastro["status"] = "realizado"
            cadastro["smartcard"] = smartcard
            cadastro["concluido_em"] = agora
            cadastro["status_balgate"] = "realizado"
            cadastro["concluido_no_sistema"] = True

        return cadastro