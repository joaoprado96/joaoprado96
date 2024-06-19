
# Aula sobre StackSpot IA e utilização com CodeRunner

## O que é StackSpot IA?
StackSpot IA é uma plataforma que oferece ferramentas e serviços para facilitar a criação, execução e monitoramento de comandos rápidos e automações. Ele permite que desenvolvedores e equipes de TI integrem e automatizem processos de forma eficiente, utilizando APIs e serviços inteligentes.

## Utilizando StackSpot IA com CodeRunner
Para demonstrar como utilizar o StackSpot IA, vamos usar uma classe Python chamada `ExecucaoComandoRapido` que integra a API do StackSpot IA com a aplicação CodeRunner. Esta classe facilita a autenticação, criação de execuções e verificação do status dos comandos rápidos.

### Código da Classe `ExecucaoComandoRapido`
```python
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
            "http": "http://default_proxy",
            "https": "https://default_proxy"
        }
        self.token_autorizacao = self.obter_token_autorizacao()
        self.headers = {
            "Authorization": f"Bearer {self.token_autorizacao}",
            "Content-Type": "application/json"
        }

    def obter_token_autorizacao(self) -> str:
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
        url = f"{self.base_url}/v1/quick-commands/callback/{execution_id}"
        
        try:
            resposta = requests.get(url, headers=self.headers, proxies=self.proxies)
            resposta.raise_for_status()
            return True, resposta.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter o status da execução: {e}")
            return False, {"erro": str(e)}

    def executar_comando_rapido(self, slug: str, input_data: Union[str, dict] = None) -> Tuple[bool, dict]:
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
            
            print(status_resposta)
            status = status_resposta.get('progress', {}).get('status')
            if status == "COMPLETED":
                return True, status_resposta.get('result', {"erro": "Resultado não encontrado"})

            time.sleep(self.intervalo_consultas)

# Exemplo de uso:
if __name__ == "__main__":
    executor = ExecucaoComandoRapido(
        base_url="https://genai-code-buddy-api.stackspot.com",
        client_id="119d6c80-5ad7-4815-8d6a-79523db69158",
        client_secret="BbGRM3a8d255o7W6dw4bp87oGCAIaNuB6eYxgFVW11Kv75h35UOa4Xe4bzsZE0ft",
        intervalo_consultas=5,  # tempo em segundos entre as consultas
        proxies={
            # "http": "http://seu_proxy_aqui",
            # "https": "https://seu_proxy_aqui"
        }
    )
    sucesso, resultado = executor.executar_comando_rapido(slug="teste-api", input_data={"chave": "valor"})
    if sucesso:
        print("Execução bem-sucedida:", resultado)
    else:
        print("Falha na execução:", resultado)
```

### Passos para utilizar o StackSpot IA com CodeRunner

1. **Configuração Inicial**: Crie uma instância da classe `ExecucaoComandoRapido` fornecendo a URL base da API, `client_id`, `client_secret`, e opções de proxy se necessário.

2. **Autenticação**: Utilize o método `obter_token_autorizacao` para autenticar-se e obter o token de acesso necessário para fazer chamadas à API.

3. **Criação de Execução**: Utilize o método `criar_execucao` para iniciar um comando rápido fornecendo o `slug` do comando e dados de entrada opcionais.

4. **Verificação de Status**: Use o método `obter_status_execucao` para verificar o status de um comando em execução até que ele seja concluído.

5. **Execução Completa**: Combine os métodos anteriores no método `executar_comando_rapido` para iniciar um comando rápido e aguardar sua conclusão.

### Demonstração Prática
No exemplo de uso fornecido, o código cria uma instância de `ExecucaoComandoRapido`, executa um comando rápido com o `slug` "teste-api" e imprime o resultado da execução.

Essa abordagem facilita a integração com o StackSpot IA e permite automações eficientes dentro do CodeRunner, aumentando a produtividade e eficiência dos desenvolvedores.
