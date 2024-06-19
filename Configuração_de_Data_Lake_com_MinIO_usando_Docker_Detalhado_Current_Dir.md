
# Configuração de um Data Lake com MinIO usando Docker

## Pré-requisitos
- Docker instalado no sistema. [Instale o Docker](https://docs.docker.com/get-docker/).

## Passo a Passo

### 1. Instalar Docker
Certifique-se de que o Docker está instalado no seu sistema.

```bash
# Verificar se o Docker está instalado
docker --version
```

### 2. Configurar compartilhamento de pastas no Docker Desktop
Para garantir que as pastas que você deseja montar no Docker estejam compartilhadas, siga os passos abaixo:

1. Abra o Docker Desktop.
2. Vá para **Preferences** > **Resources** > **File Sharing**.
3. Adicione o caminho da pasta que deseja compartilhar (ex: `/mnt/data` e `/mnt/config`).
4. Clique em **Apply & Restart** para aplicar as mudanças.

### 3. Baixar a imagem do MinIO
Antes de rodar o MinIO, vamos baixar a imagem do MinIO do repositório do Docker Hub.

```bash
docker pull quay.io/minio/minio
```

### 4. Criar diretórios locais para persistência de dados
Crie os diretórios locais no diretório atual que serão usados para armazenar os dados e as configurações do MinIO.

```bash
mkdir -p $(pwd)/data $(pwd)/config
```

### 5. Rodar o MinIO
Execute o seguinte comando para iniciar um container MinIO:

```bash
docker run -p 9000:9000 -p 9001:9001 --name minio \
  -e "MINIO_ROOT_USER=admin" \
  -e "MINIO_ROOT_PASSWORD=password" \
  -v $(pwd)/data:/data \
  -v $(pwd)/config:/root/.minio \
  quay.io/minio/minio server /data --console-address ":9001"
```

#### Explicação dos parâmetros:
- `-p 9000:9000`: Expõe a porta 9000 (API do MinIO).
- `-p 9001:9001`: Expõe a porta 9001 (Console do MinIO).
- `--name minio`: Dá um nome ao container.
- `-e "MINIO_ROOT_USER=admin"`: Define o usuário root.
- `-e "MINIO_ROOT_PASSWORD=password"`: Define a senha root.
- `-v $(pwd)/data:/data`: Monta um volume no host para persistência dos dados.
- `-v $(pwd)/config:/root/.minio`: Monta um volume no host para persistência da configuração.
- `quay.io/minio/minio`: Imagem do MinIO.
- `server /data --console-address ":9001"`: Inicia o servidor MinIO.

### 6. Acessar o MinIO
Após iniciar o container, você pode acessar o console do MinIO navegando até `http://localhost:9001` no seu navegador. Utilize as credenciais definidas (`admin` e `password`).

### 7. Criar Buckets
No console do MinIO, você pode criar buckets para organizar seus dados. Um bucket no MinIO é similar a um bucket no Amazon S3.

### 8. Integrar com outras ferramentas
Você pode usar ferramentas como Apache Spark, Hadoop, ou outras soluções de processamento de dados para ler e escrever dados no MinIO.

### Exemplo de uso com Python (Boto3)
Aqui está um exemplo simples de como você pode interagir com o MinIO usando o Boto3, que é um SDK da AWS para Python:

```python
import boto3

# Configurar o cliente S3 com as credenciais do MinIO
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='password'
)

# Criar um bucket
s3_client.create_bucket(Bucket='meu-bucket')

# Fazer upload de um arquivo
s3_client.upload_file('localfile.txt', 'meu-bucket', 'remote-file.txt')

# Listar arquivos no bucket
response = s3_client.list_objects_v2(Bucket='meu-bucket')
for obj in response.get('Contents', []):
    print(obj['Key'])
```

### Conclusão
Esses passos fornecem uma maneira básica de configurar um Data Lake usando MinIO em um container Docker. Essa configuração pode ser expandida para incluir outras ferramentas e serviços conforme necessário, dependendo das suas necessidades específicas de processamento e armazenamento de dados.
