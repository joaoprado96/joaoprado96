import requests
import json
from typing import Union, Tuple
import time

class ExecucaoComandoRapido:
    def __init__(
        self, 
        base_url: str, 
        client_id: str = "default_client_id", 
        client_secret: str = "default_client_secret", 
        intervalo_consultas: int = 5, 
        proxies: dict = None
    ):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.intervalo_consultas = intervalo_consultas
        self.proxies = proxies or {
            # "http": "http://default_proxy",
            # "https": "https://default_proxy"
        }
        self.token_autorizacao = self.obter_token_autorizacao()
        self.headers = {
            "Authorization": f"Bearer {self.token_autorizacao}",
            "Content-Type": "application/json"
        }

    def obter_token_autorizacao(self) -> str:
        """
        Obtém o token de autorização usando o client_id e client_secret.

        :return: Token de autorização.
        """
        url = 'https://idm.stackspot.com/stackspot-freemium/oidc/oauth/token'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'client_id': self.client_id,
            'grant_type': 'client_credentials',
            'client_secret': self.client_secret
        }
        
        try:
            resposta = requests.post(url, headers=headers, data=data, proxies=self.proxies)
            resposta.raise_for_status()
            token_data = resposta.json()
            return token_data['access_token']
        except requests.exceptions.RequestException as e:
            raise Exception(f"Erro ao obter o token de autorização: {e}")

    def criar_execucao(self, slug: str, input_data: Union[str, dict] = None, conversation_id: str = None) -> Tuple[bool, dict]:
        """
        Inicia a execução de um Comando Rápido.

        :param slug: O slug do Comando Rápido a ser executado.
        :param input_data: Dados de entrada opcionais, seja uma string ou um objeto JSON.
        :param conversation_id: ID de conversa opcional para manter o contexto entre execuções.
        :return: Tupla (sucesso, resposta da API em formato JSON).
        """
        url = f"{self.base_url}/v1/quick-commands/create-execution/{slug}"
        params = {}
        if conversation_id:
            params['conversation_id'] = conversation_id
        
        payload = {}
        if input_data:
            payload['input_data'] = input_data
        
        try:
            resposta = requests.post(url, headers=self.headers, params=params, data=json.dumps(payload), proxies=self.proxies)
            resposta.raise_for_status()
            return True, resposta.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao criar a execução: {e}")
            return False, {"erro": str(e)}

    def obter_status_execucao(self, execution_id: str) -> Tuple[bool, dict]:
        """
        Verifica o status de uma execução de Comando Rápido em andamento.

        :param execution_id: O ID da execução a ser verificada.
        :return: Tupla (sucesso, resposta da API em formato JSON).
        """
        url = f"{self.base_url}/v1/quick-commands/callback/{execution_id}"
        
        try:
            resposta = requests.get(url, headers=self.headers, proxies=self.proxies)
            resposta.raise_for_status()
            return True, resposta.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter o status da execução: {e}")
            self.token_autorizacao = self.obter_token_autorizacao()
            print(f"Obtido um novo token de Autorizacao: {e}")
            self.headers = {
                "Authorization": f"Bearer {self.token_autorizacao}",
                "Content-Type": "application/json"
            }
            return False, {"erro": str(e)}

    def executar_comando_rapido(self, slug: str, input_data: Union[str, dict] = None) -> Tuple[bool, dict]:
        """
        Executa um Comando Rápido e aguarda sua conclusão.

        :param slug: O slug do Comando Rápido a ser executado.
        :param input_data: Dados de entrada opcionais, seja uma string ou um objeto JSON.
        :return: Tupla (sucesso, resultado final da execução do Comando Rápido).
        """
        sucesso, execucao_resposta = self.criar_execucao(slug, input_data)
        
        if not sucesso:
            return False, execucao_resposta

        execution_id = execucao_resposta
        if not execution_id:
            return False, {"erro": "Falha ao iniciar a execução do comando rápido"}

        while True:
            sucesso, status_resposta = self.obter_status_execucao(execution_id)
            if not sucesso:
                print(f"Erro ao obter o status da execução: {status_resposta.get('erro', 'Resposta inesperada da API')}")
                time.sleep(self.intervalo_consultas)
                continue
            
            status = status_resposta.get('progress', {}).get('status')
            print(status)
            if status == "RUNNING" or status == "CREATED":
                time.sleep(self.intervalo_consultas)
            else:
                if status == "COMPLETED":
                    return True, status_resposta.get('result', {"erro": "Resultado não encontrado"})
                else:
                    return False, {"erro": "Falha ao consultar o comando rápido"}
                

            
