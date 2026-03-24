from dataclasses import dataclass, asdict


@dataclass
class Cadastro:
    id: int
    tipo_operacao: str
    placa: str
    motorista_nome: str
    motorista_cpf: str
    motorista_rg: str
    motorista_cnh: str
    motorista_validade_cnh: str
    motorista_telefone: str
    empresa_motorista: str
    nota_fiscal: str
    servico_terminal: str
    empresa_solicitante: str
    dados_site: str
    data: str
    smartcard: str = ""
    concluido_em: str = ""

    def to_dict(self):
        return asdict(self)
