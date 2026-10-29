"""Fabriquer de vrais fichiers de cours pour les tests (plan IA, IA2) : PDF à plusieurs pages (avec, au besoin, du texte
caché, blanc et minuscule), DOCX, ODT, et des fichiers piégés (bombe zip, XML à entités)."""

import io
import zipfile


def _echapper(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(pages: list[list[str]], caches: dict[int, str] | None = None) -> bytes:
    """Un PDF, une page par liste de lignes ; `caches` : {page (0, 1…) : texte écrit en blanc, en corps 2}."""
    n, objets = len(pages), {}
    police = 3 + 2 * n
    objets[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objets[2] = f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(n))}] /Count {n} >>".encode()
    for i, lignes in enumerate(pages):
        flux = "BT /F1 11 Tf 14 TL 60 780 Td " + " ".join(f"({_echapper(l)}) Tj T*" for l in lignes) + " ET"
        if caches and i in caches:
            flux += f" BT 1 1 1 rg /F1 2 Tf 60 30 Td ({_echapper(caches[i])}) Tj ET"
        donnees = flux.encode("cp1252")
        objets[3 + 2 * i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 "
                             f"{police} 0 R >> >> /Contents {4 + 2 * i} 0 R >>").encode()
        objets[4 + 2 * i] = b"<< /Length %d >>\nstream\n" % len(donnees) + donnees + b"\nendstream"
    objets[police] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    sortie, positions = io.BytesIO(), {}
    sortie.write(b"%PDF-1.4\n")
    for numero in sorted(objets):
        positions[numero] = sortie.tell()
        sortie.write(b"%d 0 obj\n" % numero + objets[numero] + b"\nendobj\n")
    xref = sortie.tell()
    sortie.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1))
    for numero in sorted(objets):
        sortie.write(b"%010d 00000 n \n" % positions[numero])
    sortie.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, xref))
    return sortie.getvalue()


def _xml(texte: str) -> str:
    return texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def docx(paragraphes: list[str], document: str | None = None) -> bytes:
    """Un DOCX minimal ; `document` remplace word/document.xml (fichiers piégés)."""
    corps = "".join(f'<w:p><w:r><w:t xml:space="preserve">{_xml(p)}</w:t></w:r></w:p>' for p in paragraphes)
    document = document or ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                            f'wordprocessingml/2006/main"><w:body>{corps}</w:body></w:document>')
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                                          'package/2006/content-types"/>')
        z.writestr("word/document.xml", document)
    return sortie.getvalue()


def odt(paragraphes: list[str]) -> bytes:
    corps = "".join(f"<text:p>{_xml(p)}</text:p>" for p in paragraphes)
    contenu = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content xmlns:office="urn:oasis:names:tc:'
               'opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
               f"<office:body><office:text>{corps}</office:text></office:body></office:document-content>")
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", contenu)
    return sortie.getvalue()


def bombe(taille: int) -> bytes:
    """Un DOCX dont le document se décompresse en `taille` octets (quelques Ko compressés)."""
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", b" " * taille)
    return sortie.getvalue()


ENTITE_EXTERNE = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                  '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p>'
                  '<w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>')
ENTITES_EN_CASCADE = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">'
                      '<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;">]><w:document xmlns:w="http://schemas.openxmlformats.org/'
                      'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&c;</w:t></w:r></w:p></w:body></w:document>')

FRACTIONS = [
    ["Les fractions (6e)", "Une fraction est un nombre ecrit a/b, avec b different de zero.",
     "Le nombre du haut est le numerateur, celui du bas le denominateur."],
    ["Fractions egales", "On obtient une fraction egale en multipliant le numerateur et le denominateur",
     "par le meme nombre : 3/4 = 6/8. Simplifier, c'est diviser les deux par un meme nombre."],
]
