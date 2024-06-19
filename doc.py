import docx
import os
from markdownify import markdownify as md

def read_docx(file_path):
    doc = docx.Document(file_path)
    elements = []
    errors = []
    image_counter = 1

    def handle_paragraph(para):
        style = para.style.name
        text = para.text.strip()
        
        # Handle different styles
        if style.startswith('Heading'):
            try:
                level = int(style.split(' ')[1])
                elements.append('#' * level + ' ' + text)
            except (IndexError, ValueError):
                elements.append('## ' + text)  # Default to level 2 if parsing fails
        elif style in ['Normal', 'BodyText', 'Body Text', 'Body Text Indent']:
            elements.append(text)
        elif style in ['List Bullet', 'List Bullet 2', 'List Bullet 3']:
            elements.append(f"* {text}")
        elif style in ['List Number', 'List Number 2', 'List Number 3']:
            elements.append(f"1. {text}")
        elif style == 'TOCHeading':
            elements.append(f"[TOC] {text}")
        elif style in ['Italic', 'Emphasis']:
            elements.append(f"*{text}*")
        elif style in ['Bold', 'Strong']:
            elements.append(f"**{text}**")
        elif style == 'Underline':
            elements.append(f"__{text}__")
        elif style == 'Strikethrough':
            elements.append(f"~~{text}~~")
        elif style == 'Subscript':
            elements.append(f"<sub>{text}</sub>")
        elif style == 'Superscript':
            elements.append(f"<sup>{text}</sup>")
        elif style == 'Highlight':
            elements.append(f"`{text}`")
        elif style == 'Hyperlink':
            elements.append(f"[Link]({text})")
        elif style == 'Quote':
            elements.append(f"> {text}")
        elif style == 'Intense Quote':
            elements.append(f"> **{text}**")
        elif style == 'Title':
            elements.append(f"# {text}")
        elif style == 'Subtitle':
            elements.append(f"## {text}")
        else:
            elements.append(text)

    def handle_table(table):
        try:
            table_data = []
            for i, row in enumerate(table.rows):
                row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                table_data.append('| ' + ' | '.join(row_data) + ' |')
                if i == 0:
                    header_separator = '| ' + ' | '.join(['---'] * len(row.cells)) + ' |'
                    table_data.insert(1, header_separator)
            elements.extend(table_data)
        except Exception as e:
            errors.append(f"Erro ao processar tabela: {str(e)}")

    def handle_table_of_contents(doc):
        for para in doc.paragraphs:
            if para.style.name.startswith('TOC'):
                elements.append(para.text.strip())

    def handle_image(image, img_counter):
        try:
            # Extract and save the image separately, then reference it in the Markdown
            image_path = f"image_{img_counter}.png"
            with open(image_path, "wb") as img_file:
                img_file.write(image)
            elements.append(f"![Image]({image_path})")
            return img_counter + 1
        except Exception as e:
            errors.append(f"Erro ao processar imagem: {str(e)}")
            return img_counter

    def handle_footnote():
        elements.append(f"[^footnote]: Footnote content")

    handle_table_of_contents(doc)

    for element in doc.element.body:
        if isinstance(element, docx.oxml.CT_P):
            handle_paragraph(docx.text.paragraph.Paragraph(element, doc))
        elif isinstance(element, docx.oxml.CT_Tbl):
            handle_table(docx.table.Table(element, doc))
        elif isinstance(element, docx.oxml.CT_Drawing):
            image_counter = handle_image(element, image_counter)

    content = '\n\n'.join(elements).replace('\t', '    ')
    content = content.replace('\n', ' \n')
    
    if errors:
        error_report = "\n\n# Relatório de Erros\n\n" + "\n".join(errors)
        content += error_report
    
    return content

def save_markdown(markdown_content, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

def convert_docx_to_markdown(input_file, output_file):
    if not os.path.isfile(input_file):
        print(f"Arquivo de entrada {input_file} não encontrado.")
        return
    docx_content = read_docx(input_file)
    save_markdown(docx_content, output_file)
    print(f"Arquivo convertido e salvo em {output_file}")

# Exemplo de uso
input_file = 'documentacao.docx'
output_file = 'documentacao.md'
convert_docx_to_markdown(input_file, output_file)