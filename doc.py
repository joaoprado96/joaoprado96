import docx
from markdownify import markdownify as md
import os

def read_docx(file_path):
    doc = docx.Document(file_path)
    elements = []

    def handle_paragraph(para):
        style = para.style.name
        text = para.text.strip()

        if style.startswith('Heading'):
            level = int(style.split(' ')[1])
            elements.append('#' * level + ' ' + text)
        elif style in ['Normal', 'BodyText', 'Body Text', 'Body Text Indent']:
            elements.append(text)
        elif style in ['List Bullet', 'List Bullet 2', 'List Bullet 3']:
            elements.append(f"* {text}")
        elif style in ['List Number', 'List Number 2', 'List Number 3']:
            elements.append(f"1. {text}")
        else:
            elements.append(text)

    def handle_table(table):
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells]
            elements.append('| ' + ' | '.join(row_data) + ' |')
        
        if len(table.rows) > 0:
            header = table.rows[0]
            separator = '| ' + ' | '.join(['---'] * len(header.cells)) + ' |'
            elements.append(separator)

    for para in doc.paragraphs:
        handle_paragraph(para)

    for table in doc.tables:
        handle_table(table)

    return '\n\n'.join(elements)

def convert_to_markdown(docx_content):
    return md(docx_content, heading_style="ATX")

def save_markdown(markdown_content, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

def convert_docx_to_markdown(input_file, output_file):
    docx_content = read_docx(input_file)
    markdown_content = convert_to_markdown(docx_content)
    save_markdown(markdown_content, output_file)

# Exemplo de uso
input_file = 'documentacao.docx'
output_file = 'documentacao.md'

# Verifique se o arquivo de entrada existe
if not os.path.isfile(input_file):
    print(f"Arquivo de entrada {input_file} não encontrado.")
else:
    convert_docx_to_markdown(input_file, output_file)
    print(f"Arquivo convertido e salvo em {output_file}")