import sys
from pathlib import Path
from pypdf import PdfReader
source, cible = Path(sys.argv[1]), Path(sys.argv[2])
for pdf in sorted(source.glob("*.pdf")):
    lecteur = PdfReader(str(pdf))
    pages = [f"=== page {i + 1} ===\n{(p.extract_text() or '')}" for i, p in enumerate(lecteur.pages)]
    (cible / (pdf.stem + ".txt")).write_text("\n".join(pages), encoding="utf-8")
    print(pdf.name, len(lecteur.pages), "pages")
