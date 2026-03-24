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
            session = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
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
            session = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
            session.SetAutoLogonPolicy(0)
            session.Open("GET", url, False)
            session.Send()
            return session.ResponseText
        except Exception as e:
            print("Erro GET (WinHTTP):", e)
            return None
 
    def _http_patch(self, url, data_dict):
        try:
            payload = json.dumps(data_dict)
            session = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
            session.SetAutoLogonPolicy(0)
            session.Open("PATCH", url, False)
            session.SetRequestHeader("Content-Type", "application/json")
            session.Send(payload)
            return session.Status == 200
        except Exception as e:
            print("Erro PATCH (WinHTTP):", e)
            return False
 
    def _http_delete(self, url):
        try:
            session = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
            session.SetAutoLogonPolicy(0)
            session.Open("DELETE", url, False)
            session.Send()
            return session.Status in (200, 204)
        except Exception as e:
            print("Erro DELETE (WinHTTP):", e)
            return False
 
    # -------------------------------------------------------------
    # BUSCAR VISITANTES
    # -------------------------------------------------------------
    def buscar_visitantes(self):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return [], False
 
        url = f"{self.base_url}/visitantes.json?auth={self.id_token}"
        resposta = self._http_get(url)
 
        if not resposta:
            return [], False
 
        try:
            dados = json.loads(resposta)
        except Exception:
            print("Erro ao interpretar JSON.")
            return [], False
 
        visitantes = []
        for key, visitante in (dados or {}).items():
            if isinstance(visitante, dict):
                item = dict(visitante)
                item["id"] = key
 
                if item.get("diversos") is True:
                    visitantes.append(item)
 
        visitantes_ordenados = sorted(
            visitantes,
            key=lambda v: (
                str(v.get("id", "")),
                str(v.get("status", "")),
                str(v.get("concluido_em", "")),
                str(v.get("smartcard", "")),
            ),
        )
 
        hash_atual = hashlib.md5(
            json.dumps(
                visitantes_ordenados,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
 
        mudou = hash_atual != self._last_hash
        self._last_hash = hash_atual
 
        return visitantes_ordenados, mudou
 
    # -------------------------------------------------------------
    # ATUALIZAR VISITANTE
    # -------------------------------------------------------------
    def atualizar_visitante(self, visitante_id, payload):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return False
 
        url = f"{self.base_url}/visitantes/{visitante_id}.json?auth={self.id_token}"
        return self._http_patch(url, payload)
 
    # -------------------------------------------------------------
    # EXCLUIR VISITANTE
    # -------------------------------------------------------------
    def excluir_visitante(self, visitante_id):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return False
 
        url = f"{self.base_url}/visitantes/{visitante_id}.json?auth={self.id_token}"
        return self._http_delete(url)
 
    # -------------------------------------------------------------
    # LIMPAR REALIZADOS COM MAIS DE 24H
    # -------------------------------------------------------------
    def limpar_realizados_antigos(self, visitantes=None, horas=24):
        if not self.id_token:
            print("⚠ Erro: sistema não autenticado!")
            return 0
 
        if visitantes is None:
            visitantes, _ = self.buscar_visitantes()
 
        agora = datetime.now()
        limite = agora - timedelta(hours=horas)
        total_excluidos = 0
 
        for visitante in visitantes:
            try:
                status = str(visitante.get("status", "")).strip().lower()
                concluido_em = visitante.get("concluido_em")
 
                if status not in ("realizado", "concluido", "concluído"):
                    continue
 
                if not concluido_em:
                    continue
 
                data_conclusao = self._parse_datetime(concluido_em)
                if not data_conclusao:
                    continue
 
                if data_conclusao <= limite:
                    visitante_id = visitante.get("id")
                    if visitante_id and self.excluir_visitante(visitante_id):
                        total_excluidos += 1
 
            except Exception as e:
                print("Erro ao avaliar exclusão automática:", e)
 
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
