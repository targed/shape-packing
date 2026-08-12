import html.parser

class Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ['style', 'script', 'svg']: self.skip = True
    def handle_endtag(self, tag):
        if tag in ['style', 'script', 'svg']: self.skip = False
    def handle_data(self, data):
        if not self.skip and data.strip(): self.text.append(data.strip())
p = Parser()
with open('The Mill [IT Research Support Solutions Wiki].html', 'r', encoding='utf-8') as f:
    p.feed(f.read())
with open('mill_docs.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(p.text))
