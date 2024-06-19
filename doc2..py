import docx
import os
from markdownify import markdownify as md
from bs4 import BeautifulSoup

class DocumentConverter:
    def __init__(self):
        self.elements = []
        self.errors = []
        self.image_counter = 1

    def read_docx(self, file_path):
        doc = docx.Document(file_path)
        self.elements = []
        self.errors = []
        self.image_counter = 1

        self.handle_table_of_contents(doc)

        for element in doc.element.body:
            self.handle_element(element)

        content = '\n\n'.join(self.elements).replace('\t', '    ')
        content = content.replace('\n', ' \n')
        
        if self.errors:
            error_report = "\n\n# Relatório de Erros\n\n" + "\n".join(self.errors)
            content += error_report
        
        return content

    def handle_paragraph(self, para):
        style = para.style.name
        text = para.text.strip()
        font_size = para.runs[0].font.size.pt if para.runs and para.runs[0].font.size else 12
        
        if style.startswith('Heading') or font_size > 12:
            try:
                if style.startswith('Heading'):
                    level = int(style.split(' ')[1])
                else:
                    level = max(1, min(int((font_size - 12) / 2) + 1, 6))
                self.elements.append('#' * level + ' ' + text)
            except (IndexError, ValueError):
                self.elements.append('## ' + text)
        else:
            self.handle_text_styles(style, text)

    def handle_text_styles(self, style, text):
        styles_map = {
            'Normal': text,
            'BodyText': text,
            'Body Text': text,
            'Body Text Indent': text,
            'List Bullet': f"* {text}",
            'List Bullet 2': f"* {text}",
            'List Bullet 3': f"* {text}",
            'List Number': f"1. {text}",
            'List Number 2': f"1. {text}",
            'List Number 3': f"1. {text}",
            'TOCHeading': f"[TOC] {text}",
            'Italic': f"*{text}*",
            'Emphasis': f"*{text}*",
            'Bold': f"**{text}**",
            'Strong': f"**{text}**",
            'Underline': f"__{text}__",
            'Strikethrough': f"~~{text}~~",
            'Subscript': f"<sub>{text}</sub>",
            'Superscript': f"<sup>{text}</sup>",
            'Highlight': f"`{text}`",
            'Hyperlink': f"[Link]({text})",
            'Quote': f"> {text}",
            'Intense Quote': f"> **{text}**",
            'Title': f"# {text}",
            'Subtitle': f"## {text}"
        }

        self.elements.append(styles_map.get(style, text))

    def handle_table(self, table):
        try:
            table_data = []
            for i, row in enumerate(table.rows):
                row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                table_data.append('| ' + ' | '.join(row_data) + ' |')
                if i == 0:
                    header_separator = '| ' + ' | '.join(['---'] * len(row.cells)) + ' |'
                    table_data.insert(1, header_separator)
            self.elements.extend(table_data)
        except Exception as e:
            self.errors.append(f"Erro ao processar tabela: {str(e)}")

    def handle_table_of_contents(self, doc):
        for para in doc.paragraphs:
            if para.style.name.startswith('TOC'):
                self.elements.append(para.text.strip())

    def handle_image(self, image):
        try:
            image_path = f"image_{self.image_counter}.png"
            with open(image_path, "wb") as img_file:
                img_file.write(image)
            self.elements.append(f"![Image]({image_path})")
            self.image_counter += 1
        except Exception as e:
            self.errors.append(f"Erro ao processar imagem: {str(e)}")

    def handle_element(self, element):
        if isinstance(element, docx.text.paragraph.Paragraph):
            self.handle_paragraph(element)
        elif isinstance(element, docx.table.Table):
            self.handle_table(element)
        elif isinstance(element, docx.shape.InlineShape):
            self.handle_image(element)
        elif isinstance(element, docx.oxml.CT_Drawing):
            self.handle_image(element)
        elif hasattr(element, 'element') and hasattr(element.element, 'body'):
            for sub_element in element.element.body:
                self.handle_element(sub_element)

    def read_html(self, file_path):
        self.elements = []
        self.errors = []
        self.image_counter = 1

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for element in soup.descendants:
                self.handle_html_element(element)

        except Exception as e:
            self.errors.append(f"Erro ao processar HTML: {str(e)}")

        content = '\n\n'.join(self.elements).replace('\t', '    ')
        content = content.replace('\n', ' \n')
        
        if self.errors:
            error_report = "\n\n# Relatório de Erros\n\n" + "\n".join(self.errors)
            content += error_report

        return content

    def handle_html_element(self, element):
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(element.name[1])
            self.elements.append('#' * level + ' ' + element.get_text(strip=True))
        elif element.name == 'p':
            self.elements.append(element.get_text(strip=True))
        elif element.name == 'ul':
            for li in element.find_all('li'):
                self.elements.append(f"* {li.get_text(strip=True)}")
        elif element.name == 'ol':
            for li in element.find_all('li'):
                self.elements.append(f"1. {li.get_text(strip=True)}")
        elif element.name == 'table':
            self.handle_html_table(element)
        elif element.name == 'img':
            src = element.get('src')
            self.elements.append(f"![Image]({src})")
        elif element.name == 'a':
            href = element.get('href')
            text = element.get_text(strip=True)
            self.elements.append(f"[{text}]({href})")
        elif element.name == 'blockquote':
            self.elements.append(f"> {element.get_text(strip=True)}")

    def handle_html_table(self, table):
        table_data = []
        for i, row in enumerate(table.find_all('tr')):
            row_data = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
            table_data.append('| ' + ' | '.join(row_data) + ' |')
            if i == 0:
                header_separator = '| ' + ' | '.join(['---'] * len(row_data)) + ' |'
                table_data.insert(1, header_separator)
        self.elements.extend(table_data)

    def convert_to_markdown(self, input_file, output_file):
        if not os.path.isfile(input_file):
            print(f"Arquivo de entrada {input_file} não encontrado.")
            return

        file_extension = os.path.splitext(input_file)[1].lower()

        if file_extension == '.docx':
            content = self.read_docx(input_file)
        elif file_extension in ['.html', '.htm']:
            content = self.read_html(input_file)
        else:
            print(f"Tipo de arquivo {file_extension} não suportado.")
            return

        self.save_markdown(content, output_file)
        print(f"Arquivo convertido e salvo em {output_file}")

    def save_markdown(self, markdown_content, output_path):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

# Exemplo de uso
converter = DocumentConverter()
input_file = 'documentacao.docx'  # ou 'documentacao.html'
output_file = 'documentacao.md'
converter.convert_to_markdown(input_file, output_file)