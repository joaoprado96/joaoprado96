
# Configuração de Containers com Docker: Nginx e MySQL

## Índice
1. [Pré-requisitos](#pré-requisitos)
2. [Objetivo](#objetivo)
3. [Passo 1: Criação da Rede Docker](#passo-1-criação-da-rede-docker)
4. [Passo 2: Criação do Container MySQL](#passo-2-criação-do-container-mysql)
    - [1. Baixar a imagem do MySQL](#1-baixar-a-imagem-do-mysql)
    - [2. Executar o container MySQL](#2-executar-o-container-mysql)
5. [Passo 3: Criação do Container Nginx](#passo-3-criação-do-container-nginx)
    - [1. Baixar a imagem do Nginx](#1-baixar-a-imagem-do-nginx)
    - [2. Criar um arquivo de configuração Nginx](#2-criar-um-arquivo-de-configuração-nginx)
    - [3. Executar o container Nginx](#3-executar-o-container-nginx)
6. [Passo 4: Testar a Comunicação](#passo-4-testar-a-comunicação)
    - [1. Verificar os containers em execução](#1-verificar-os-containers-em-execução)
    - [2. Acessar o container Nginx](#2-acessar-o-container-nginx)
    - [3. Acessar o container MySQL](#3-acessar-o-container-mysql)
7. [Conclusão](#conclusão)
8. [Recursos Adicionais](#recursos-adicionais)

## Pré-requisitos
- Docker instalado na sua máquina. [Instruções de instalação](https://docs.docker.com/get-docker/)
- Conhecimento básico de linha de comando.

## Objetivo
Criar dois containers: um com uma aplicação web (Nginx) e outro com um banco de dados (MySQL), e configurar a comunicação entre eles.

## Passo 1: Criação da Rede Docker
Para que os containers possam se comunicar, vamos criar uma rede Docker.

\`\`\`bash
docker network create my_network
\`\`\`

## Passo 2: Criação do Container MySQL
Vamos criar um container MySQL usando uma imagem oficial do MySQL.

### 1. Baixar a imagem do MySQL
\`\`\`bash
docker pull mysql:latest
\`\`\`

### 2. Executar o container MySQL
\`\`\`bash
docker run --name my_mysql_container --network my_network -e MYSQL_ROOT_PASSWORD=root_password -e MYSQL_DATABASE=my_database -e MYSQL_USER=user -e MYSQL_PASSWORD=user_password -d mysql:latest
\`\`\`
- **--name**: Nome do container (my_mysql_container).
- **--network**: Rede Docker para o container (my_network).
- **-e**: Variáveis de ambiente para configuração do MySQL.
- **-d**: Executar o container em modo desacoplado (em background).

## Passo 3: Criação do Container Nginx
Vamos criar um container Nginx que servirá como servidor web.

### 1. Baixar a imagem do Nginx
\`\`\`bash
docker pull nginx:latest
\`\`\`

### 2. Criar um arquivo de configuração Nginx
Crie um arquivo chamado \`default.conf\` com o seguinte conteúdo:

\`\`\`nginx
server {
    listen 80;

    location / {
        proxy_pass http://my_mysql_container:3306;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
\`\`\`

### 3. Executar o container Nginx
\`\`\`bash
docker run --name my_nginx_container --network my_network -v $(pwd)/default.conf:/etc/nginx/conf.d/default.conf:ro -p 8080:80 -d nginx:latest
\`\`\`
- **--name**: Nome do container (my_nginx_container).
- **--network**: Rede Docker para o container (my_network).
- **-v**: Montar o arquivo de configuração Nginx no container.
- **-p**: Mapeia a porta 80 do container para a porta 8080 do host.
- **-d**: Executar o container em modo desacoplado (em background).

## Passo 4: Testar a Comunicação
Agora que ambos os containers estão em execução e na mesma rede, vamos testar a comunicação entre eles.

### 1. Verificar os containers em execução
\`\`\`bash
docker ps
\`\`\`
Você deve ver ambos os containers (\`my_mysql_container\` e \`my_nginx_container\`) em execução.

### 2. Acessar o container Nginx
Abra um navegador web e acesse \`http://localhost:8080\`. O Nginx deve estar configurado para encaminhar solicitações ao MySQL.

### 3. Acessar o container MySQL
Você pode acessar o container MySQL diretamente usando um cliente MySQL ou o CLI do Docker.

#### Usar o CLI do Docker para acessar o MySQL
\`\`\`bash
docker exec -it my_mysql_container mysql -uuser -p
\`\`\`
Digite a senha \`user_password\` quando solicitado. Agora você deve estar no prompt do MySQL.

## Conclusão
Você configurou com sucesso dois containers Docker (Nginx e MySQL) e configurou a comunicação entre eles usando uma rede Docker. Este é um exemplo básico, e você pode expandir essa configuração para incluir mais containers e serviços conforme necessário.

## Recursos Adicionais
- [Documentação do Docker](https://docs.docker.com/)
- [Imagens Docker no Docker Hub](https://hub.docker.com/)
- [Documentação do Nginx](https://nginx.org/en/docs/)
- [Documentação do MySQL](https://dev.mysql.com/doc/)
