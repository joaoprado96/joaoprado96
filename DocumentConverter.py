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
            # Basic Styles
            'Normal': text,
            'Texto do Corpo': text,
            
            # Body Text Variants
            'BodyText': text,
            'Body Text': text,
            'Body Text Indent': text,
            'Texto do Corpo Indentado': text,
            
            # List Bullet Styles
            'List Bullet': f"* {text}",
            'List Bullet 2': f"* {text}",
            'List Bullet 3': f"* {text}",
            'Lista com Marcadores': f"* {text}",
            'Lista com Marcadores 2': f"* {text}",
            'Lista com Marcadores 3': f"* {text}",
            
            # List Number Styles
            'List Number': f"1. {text}",
            'List Number 2': f"1. {text}",
            'List Number 3': f"1. {text}",
            'Lista Numerada': f"1. {text}",
            'Lista Numerada 2': f"1. {text}",
            'Lista Numerada 3': f"1. {text}",
            
            # Table of Contents
            'TOCHeading': f"[TOC] {text}",
            'Cabeçalho TOC': f"[TOC] {text}",
            
            # Text Formatting
            'Italic': f"*{text}*",
            'Emphasis': f"*{text}*",
            'Cursiva': f"*{text}*",
            'Ênfase': f"*{text}*",
            
            'Bold': f"**{text}**",
            'Strong': f"**{text}**",
            'Negrito': f"**{text}**",
            'Forte': f"**{text}**",
            
            'Underline': f"__{text}__",
            'Sublinhado': f"__{text}__",
            
            'Strikethrough': f"~~{text}~~",
            'Tachado': f"~~{text}~~",
            
            'Subscript': f"<sub>{text}</sub>",
            'Subscrito': f"<sub>{text}</sub>",
            
            'Superscript': f"<sup>{text}</sup>",
            'Sobrescrito': f"<sup>{text}</sup>",
            
            'Highlight': f"`{text}`",
            'Destaque': f"`{text}`",
            
            'Hyperlink': f"[Link]({text})",
            'Hiperlink': f"[Link]({text})",
            
            # Quote Styles
            'Quote': f"> {text}",
            'Citação': f"> {text}",
            
            'Intense Quote': f"> **{text}**",
            'Citação Intensa': f"> **{text}**",
            
            # Heading Styles
            'Title': f"# {text}",
            'Título': f"# {text}",
            
            'Subtitle': f"## {text}",
            'Subtítulo': f"## {text}",
            
            'Heading 1': f"# {text}",
            'Heading 2': f"## {text}",
            'Heading 3': f"### {text}",
            'Heading 4': f"#### {text}",
            'Heading 5': f"##### {text}",
            'Heading 6': f"###### {text}",
            'Título 1': f"# {text}",
            'Título 2': f"## {text}",
            'Título 3': f"### {text}",
            'Título 4': f"#### {text}",
            'Título 5': f"##### {text}",
            'Título 6': f"###### {text}",
            
            # HTML Styles
            'HTML Acronym': f"<acronym>{text}</acronym>",
            'HTML Address': f"<address>{text}</address>",
            'HTML Cite': f"<cite>{text}</cite>",
            'HTML Code': f"<code>{text}</code>",
            'HTML Definition': f"<dfn>{text}</dfn>",
            'HTML Keyboard': f"<kbd>{text}</kbd>",
            'HTML Preformatted': f"<pre>{text}</pre>",
            'HTML Sample': f"<samp>{text}</samp>",
            'HTML Typewriter': f"<tt>{text}</tt>",
            'HTML Variable': f"<var>{text}</var>",
            
            # Index Styles
            'Index 1': f"{text}",
            'Index 2': f"{text}",
            'Index 3': f"{text}",
            'Index 4': f"{text}",
            'Index 5': f"{text}",
            'Index 6': f"{text}",
            'Index 7': f"{text}",
            'Index 8': f"{text}",
            'Index 9': f"{text}",
            'Index Heading': f"**{text}**",
            
            # Line and List Styles
            'Line Number': text,
            'List': f"{text}",
            'List 2': f"{text}",
            'List 3': f"{text}",
            'List 4': f"{text}",
            'List 5': f"{text}",
            'List Bullet 4': f"* {text}",
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