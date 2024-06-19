### Aula sobre StackSpot IA e utilização com CodeRunner

## O que é StackSpot IA?
StackSpot IA é uma plataforma que oferece ferramentas e serviços para facilitar a criação, execução e monitoramento de comandos rápidos e automações. Ele permite que desenvolvedores e equipes de TI integrem e automatizem processos de forma eficiente, utilizando APIs e serviços inteligentes.

## Utilizando StackSpot IA com CodeRunner
Para demonstrar como utilizar o StackSpot IA, você pode integrar a API do StackSpot IA com a aplicação CodeRunner. Esta integração facilita a autenticação, criação de execuções e verificação do status dos comandos rápidos.

### Passo a Passo para Criar um Quick Command na Plataforma StackSpot IA

Criar um Quick Command na plataforma StackSpot IA envolve várias etapas, desde a configuração inicial até a execução do comando. Aqui está um guia passo a passo para ajudar você a criar e utilizar um Quick Command.

#### 1. Configuração Inicial

1. **Acesse a Plataforma StackSpot IA**: Abra seu navegador e acesse a URL da plataforma StackSpot IA fornecida pela sua organização.

2. **Faça Login**: Use suas credenciais de acesso (usuário e senha) para entrar na plataforma. Caso ainda não tenha uma conta, registre-se seguindo as instruções da plataforma.

#### 2. Navegando até a Seção de Quick Commands

1. **Dashboard**: Após fazer login, você será direcionado ao dashboard principal da plataforma.

2. **Quick Commands**: No menu lateral ou na barra de navegação superior, encontre e selecione a opção "Quick Commands" ou "Comandos Rápidos".

#### 3. Criando um Novo Quick Command

1. **Novo Quick Command**: Clique no botão "Novo" ou "Create New" para iniciar a criação de um novo Quick Command.

2. **Configurar Detalhes do Comando**:
   - **Nome**: Dê um nome descritivo ao seu comando que reflita sua funcionalidade.
   - **Descrição**: Adicione uma descrição detalhada do que o comando faz e em quais situações ele deve ser usado.
   - **Slug**: Crie um identificador único (slug) para o comando, que será usado para chamá-lo via API.
   - **Categoria**: Selecione ou crie uma categoria adequada para organizar seu comando.

3. **Definir Entradas do Comando**:
   - **Parâmetros**: Adicione os parâmetros necessários que o comando deverá aceitar. Defina o nome, tipo de dado (string, número, etc.), e se são obrigatórios ou opcionais.

4. **Escrever o Script do Comando**:
   - **Código**: No editor de código fornecido pela plataforma, escreva o script que será executado quando o comando for chamado. Este script deve ser escrito na linguagem suportada pela plataforma (geralmente Python ou JavaScript).

5. **Configurar Saídas do Comando**:
   - **Formato de Saída**: Defina como a saída do comando será estruturada (ex.: JSON, texto, etc.).

#### 4. Testando o Quick Command

1. **Salvar e Testar**: Após configurar e escrever o código do comando, salve-o e utilize a funcionalidade de teste fornecida pela plataforma para garantir que o comando funcione conforme esperado.

2. **Depurar**: Se o comando não funcionar corretamente, utilize as mensagens de erro e logs para depurar e ajustar o código.

#### 5. Publicando o Quick Command

1. **Revisão Final**: Faça uma revisão final de todas as configurações e do código do comando.

2. **Publicar**: Clique no botão "Publicar" ou "Deploy" para disponibilizar o comando para uso.

#### 6. Utilizando o Quick Command

1. **API Endpoint**: Após publicar, a plataforma fornecerá um endpoint de API que pode ser usado para chamar o Quick Command.

2. **Chamar o Comando**: Use o endpoint fornecido junto com os parâmetros necessários para chamar o comando a partir de qualquer cliente HTTP, como o Postman, Insomnia, ou diretamente do seu código utilizando bibliotecas HTTP (ex.: requests em Python).

Seguindo estes passos, você poderá criar, configurar, testar, publicar e utilizar Quick Commands na plataforma StackSpot IA. Isso permitirá automatizar e simplificar diversos processos e tarefas dentro da sua organização.

## Utilizando a Interface do CodeRunner

Para entrar no CodeRunner, basta acessar o Mainframe Hub de Homologação, selecionar o produto CodeRunner e, em seguida, selecionar o editor de código. Aparecerão todas as siglas que você consegue editar ou criar novos códigos.

#### Interface do Editor de Códigos
Na interface do CodeRunner, você pode criar, editar, comparar, fazer upload, executar e visualizar logs de seus códigos Python.

#### Descrição dos Botões:
- **Novo**: Cria um novo script Python.
- **Comparar**: Permite comparar a versão atual do script com versões anteriores.
- **Upload**: Faz o upload de um script Python do seu computador para o CodeRunner.
- **Executar**: Executa o script atual.
- **Logs**: Visualiza os logs da execução do script, redirecionando para o Splunk.

### Exemplo de Uso do CodeRunner com StackSpot IA

1. **Configuração Inicial**: Crie uma instância da classe `ExecutarComandoRapido`.

2. **Autenticação**: Utilize um método para autenticar-se e obter o token de acesso necessário para fazer chamadas à API.

3. **Criação de Execução**: Utilize um método para iniciar um comando rápido fornecendo o `slug` do comando e dados de entrada opcionais.

4. **Verificação de Status**: Use um método para verificar o status de um comando em execução até que ele seja concluído.

5. **Execução Completa**: Combine os métodos anteriores para iniciar um comando rápido e aguardar sua conclusão.

Vamos utilizar uma exeucao completa que ja faz todo o processo.

```python
from app.functions.basicas import *
from app.functions.stackspot import *

def run(data):
    input_data = data['data']
    slug_data = data['slug']
    executor = ExecucaoComandoRapido()
    sucesso, resultado = executor.executar_comando_rapido(slug=slug_data, input_data=input_data)

    if sucesso:
        resposta = {
            "data": resultado
        }
    else:
        resposta = {
            "data": "Falhou"
        }

    return resposta, 200
```

### Passos para Executar o Código
1. Crie um novo script ou edite um existente no editor de códigos do CodeRunner.
2. Cole o código de exemplo na área de edição.
3. Clique em **Executar** para rodar o script.
4. Verifique os resultados e logs utilizando os botões **Logs**.

Essa abordagem facilita a integração com o StackSpot IA e permite automações eficientes dentro do CodeRunner, aumentando a produtividade e eficiência dos desenvolvedores.