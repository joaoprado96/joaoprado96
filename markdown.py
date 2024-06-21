import re
from transformers import T5ForConditionalGeneration, T5Tokenizer

class MarkdownRewriter:
    def __init__(self, model_name="t5-base"):
        self.tokenizer = T5Tokenizer.from_pretrained(model_name)
        self.model = T5ForConditionalGeneration.from_pretrained(model_name)

    def split_content(self, content, max_length=512):
        # Split content into chunks that fit within the max token length
        tokens = self.tokenizer.encode(content, return_tensors='pt', truncation=False)
        chunks = []
        for i in range(0, tokens.size(1), max_length):
            chunk = tokens[:, i:i + max_length]
            chunks.append(chunk)
        return chunks

    def reformat_section(self, section):
        # Prepare the input text for T5
        input_text = "summarize: " + section
        input_ids = self.tokenizer.encode(input_text, return_tensors="pt", truncation=True)
        
        # Generate the reformatted text
        output_ids = self.model.generate(input_ids, max_length=512, num_beams=4, early_stopping=True)
        improved_section = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        
        return improved_section

    def reformat_markdown(self, content):
        # Split content into sections by paragraphs and code blocks
        sections = re.split(r'(```.*?```|\n\s*\n)', content, flags=re.DOTALL)

        improved_sections = []
        for section in sections:
            if section.startswith('```') and section.endswith('```'):
                # Preserve code blocks as is
                improved_sections.append(section)
            elif section.strip():  # Avoid empty sections
                chunks = self.split_content(section, max_length=512)
                improved_chunks = [self.reformat_section(self.tokenizer.decode(chunk[0], skip_special_tokens=True)) for chunk in chunks]
                improved_sections.append(" ".join(improved_chunks))
            else:
                improved_sections.append(section)  # Preserve empty sections

        return "".join(improved_sections)

    def rewrite_markdown_content(self, content):
        formatted_content = self.reformat_markdown(content)
        return formatted_content

# Exemplo de uso:
# content = "Seu conteúdo de markdown aqui"
# rewriter = MarkdownRewriter()
# new_content = rewriter.rewrite_markdown_content(content)
# print(new_content)