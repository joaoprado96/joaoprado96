import boto3
from botocore.exceptions import ClientError
import os

# Configurar o cliente S3 com as credenciais do MinIO
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='admin',
    aws_secret_access_key='password'
)

bucket_name = 'meu-bucket'
file_path = 'bonus.txt'
s3_key = 'remote-file.txt'

# Verificar se o bucket já existe
def bucket_exists(bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError:
        return False

# Criar o bucket se ele não existir
if not bucket_exists(bucket_name):
    try:
        s3_client.create_bucket(Bucket=bucket_name)
        print(f'Bucket {bucket_name} criado com sucesso.')
    except ClientError as e:
        print(f'Erro ao criar o bucket: {e}')
else:
    print(f'O bucket {bucket_name} já existe.')

# Verificar se o arquivo existe antes de fazer o upload
if os.path.isfile(file_path):
    try:
        s3_client.upload_file(file_path, bucket_name, s3_key)
        print('Arquivo enviado com sucesso.')
    except ClientError as e:
        print(f'Erro ao enviar o arquivo: {e}')
else:
    print(f'O arquivo {file_path} não foi encontrado.')

# Listar arquivos no bucket
try:
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    if 'Contents' in response:
        for obj in response['Contents']:
            print(obj['Key'])
    else:
        print('O bucket está vazio.')
except ClientError as e:
    print(f'Erro ao listar os arquivos no bucket: {e}')