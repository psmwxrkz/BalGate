import json
import hashlib
from datetime import datetime, timedelta

import win32com.client


FIREBASE_URL = "https://controle-diversos-default-rtdb.firebaseio.com"
API_KEY = "AIzaSyA8DbMSU96gaxqFYKDfC0fhakhwly6Iv78"


class FirebaseClient:
    def __init__(self):
        self.base_url = FIREBASE_URL
        self.api_key = API_KEY
        self.id_token = None
        self._last_hash = None

    def _criar_sessao_http(self):
        session = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
        session.SetAutoLogonPolicy(0)

        # timeouts em milissegundos:
        # resolve, connect, send, receive
        session.SetTimeouts(3000, 3000, 5000, 5000)

        return session

    # -------------------------------------------------------------
    # LOGIN NO FIREBASE AUTH
    # -------------------------------------------------------------
    def autenticar(self, email, senha):
        url = (
            "https://identitytoolkit.googleapis.com/v1/"
            f"accounts:signInWithPassword?key={self.api_key}"
        )

        payload = json.dumps(
            {
                "email": email,
                "password": senha,
                "returnSecureToken": True,
            }
        )

        try:
            session = self._criar_sessao_http()
            session.Open("POST", url, False)
            session.SetRequestHeader("Content-Type", "application/json")
            session.Send(payload)

            resp = json.loads(session.ResponseText or "{}")
            self.id_token = resp.get("idToken")
            return self.id_token is not None

        except Exception as e:
            print("Erro ao autenticar:", e)
            return False
            
    # -------------------------------------------------------------
    # MÉTODOS HTTP AUXILIARES
    # -------------------------------------------------------------
    def _http_get(self, url):
        try:
            session = self._criar_sessao_http()
            session.Open("GET", url, False)
            session.Send()
            return session.ResponseText
        except Exception as e:
            print("Erro GET (WinHTTP):", e)
            return None

    def _http_patch(self, url, data_dict):
        try:
            payload = json.dumps(data_dict)
            session = self._criar_sessao_http()
            session.Open("PATCH", url, False)
            session.SetRequestHeader("Content-Type", "application/json")
            session.Send(payload)
            return session.Status == 200
        except Exception as e:
            print("Erro PATCH (WinHTTP):", e)
            return False

    def _http_delete(self, url):
        try:
            session = self._criar_sessao_http()
            session.Open("DELETE", url, False)
            session.Send()
            return session.Status in (200, 204) 
        except Exception as e:
            print("Erro DELETE (WinHTTP):", e)
            return False

    def _normalizar_bool(self, valor):
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str):
            return valor.strip().lower() == "true"
        return False

    def _garantir_lista(self, valor):
        if isinstance(valor, list):
            return valor
        if isinstance(valor, dict):
            itens = []
            for chave in sorted(valor.keys(), key=lambda x: str(x)):
                item = valor.get(chave)
                if isinstance(item, dict):
                    item = dict(item)
                    if "id" not in item:
                        item["id"] = chave
                    itens.append(item)
            return itens
        return []

    def _ordenar_registros(self, registros):
        return sorted(
            registros,
            key=lambda v: (
                str(v.get("origem", "")),
                str(v.get("id", "")),
                str(v.get("status", "")),
                str(v.get("concluido_em", "")),
                str(v.get("smartcard", "")),
            ),
        )

    def _calcular_hash(self, registros):
        return hashlib.md5(
            json.dumps(
                registros,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    # -------------------------------------------------------------
    # LEITURA GENÉRICA DE UMA COLEÇÃO
    # -------------------------------------------------------------
    def _buscar_colecao(self, colecao):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return []

        url = f"{self.base_url}/{colecao}.json?auth={self.id_token}"
        resposta = self._http_get(url)

        if not resposta:
            return []

        try:
            dados = json.loads(resposta)
        except Exception:
            print(f"Erro ao interpretar JSON de '{colecao}'.")
            return []

        registros = []

        for key, registro in (dados or {}).items():
            if not isinstance(registro, dict):
                continue

            item = dict(registro)
            item["id"] = key
            item["origem"] = colecao

            if colecao == "visitantes":
                if self._normalizar_bool(item.get("diversos")):
                    registros.append(item)

            elif colecao == "consumos":
                individuos = self._garantir_lista(item.get("individuos"))
                item["individuos"] = individuos

                tem_diversos = any(
                    self._normalizar_bool(individuo.get("diversos"))
                    for individuo in individuos
                    if isinstance(individuo, dict)
                )

                if tem_diversos:
                    registros.append(item)

            else:
                registros.append(item)

        return registros

    # -------------------------------------------------------------
    # BUSCA ESPECÍFICA
    # -------------------------------------------------------------
    def buscar_visitantes_somente(self):
        return self._buscar_colecao("visitantes")

    def buscar_consumos(self):
        return self._buscar_colecao("consumos")

    def buscar_todos_registros(self):
        visitantes = self.buscar_visitantes_somente()
        consumos = self.buscar_consumos()

        todos = self._ordenar_registros(visitantes + consumos)

        hash_atual = self._calcular_hash(todos)
        mudou = hash_atual != self._last_hash
        self._last_hash = hash_atual

        return todos, mudou

    # -------------------------------------------------------------
    # COMPATIBILIDADE COM O CÓDIGO ATUAL DA UI
    # OBS.: mantém o nome buscar_visitantes, mas agora traz
    # visitantes + consumos para não quebrar o main_window.py atual.
    # -------------------------------------------------------------
    def buscar_visitantes(self):
        return self.buscar_todos_registros()

    # -------------------------------------------------------------
    # ATUALIZAR REGISTRO
    # -------------------------------------------------------------
    def atualizar_registro(self, colecao, registro_id, payload):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return False

        url = f"{self.base_url}/{colecao}/{registro_id}.json?auth={self.id_token}"
        sucesso = self._http_patch(url, payload)

        if sucesso:
            self._last_hash = None

        return sucesso

    def atualizar_visitante(self, visitante_id, payload):
        return self.atualizar_registro("visitantes", visitante_id, payload)

    def atualizar_consumo(self, consumo_id, payload):
        return self.atualizar_registro("consumos", consumo_id, payload)

    # -------------------------------------------------------------
    # EXCLUIR REGISTRO
    # -------------------------------------------------------------
    def excluir_registro(self, colecao, registro_id):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return False

        url = f"{self.base_url}/{colecao}/{registro_id}.json?auth={self.id_token}"
        sucesso = self._http_delete(url)

        if sucesso:
            self._last_hash = None

        return sucesso

    def excluir_visitante(self, visitante_id):
        return self.excluir_registro("visitantes", visitante_id)

    def excluir_consumo(self, consumo_id):
        return self.excluir_registro("consumos", consumo_id)

    # -------------------------------------------------------------
    # LIMPAR REALIZADOS COM MAIS DE 24H
    # -------------------------------------------------------------
    def limpar_realizados_antigos(self, visitantes=None, horas=72, limite_exclusoes=20):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return 0

        if visitantes is None:
            visitantes, _ = self.buscar_todos_registros()

        agora = datetime.now()
        limite_data = agora - timedelta(hours=horas)
        total_excluidos = 0

        candidatos = []

        for registro in visitantes:
            try:
                status = str(registro.get("status", "")).strip().lower()
                concluido_em = registro.get("concluido_em") or registro.get("concluidoEm")
                origem = registro.get("origem", "visitantes")
                registro_id = registro.get("id")

                if status not in ("realizado", "concluido", "concluído", "finalizado"):
                    continue

                if not concluido_em or not registro_id:
                    continue

                data_conclusao = self._parse_datetime(concluido_em)
                if not data_conclusao:
                    continue

                if data_conclusao <= limite_data:
                    candidatos.append(
                        {
                            "origem": origem,
                            "id": registro_id,
                            "status": status,
                            "concluido_em": concluido_em,
                        }
                    )

            except Exception as e:
                print("Erro ao avaliar exclusão automática:", e)

        if not candidatos:
            return 0

        # Ordena os mais antigos primeiro
        candidatos.sort(key=lambda item: str(item.get("concluido_em", "")))

        for item in candidatos[:limite_exclusoes]:
            try:
                print(
                    "[LIMPEZA AUTO] Excluindo registro:",
                    f"origem={item['origem']}",
                    f"id={item['id']}",
                    f"status={item['status']}",
                    f"concluido_em={item['concluido_em']}",
                )

                if self.excluir_registro(item["origem"], item["id"]):
                    total_excluidos += 1

            except Exception as e:
                print("Erro ao excluir registro automaticamente:", e)

        if total_excluidos > 0:
            self._last_hash = None

        return total_excluidos
        
    # -------------------------------------------------------------
    # AUXILIAR PARA CONVERTER DATA/HORA
    # -------------------------------------------------------------
    def _parse_datetime(self, valor):
        if not valor:
            return None

        if isinstance(valor, datetime):
            return valor

        if not isinstance(valor, str):
            return None

        texto = valor.strip()
        if not texto:
            return None

        formatos = [
            None,  # tenta fromisoformat primeiro
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ]

        for formato in formatos:
            try:
                if formato is None:
                    return datetime.fromisoformat(texto)
                return datetime.strptime(texto, formato)
            except Exception:
                continue

        return None