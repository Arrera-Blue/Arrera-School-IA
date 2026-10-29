-- Plan IA, IA2 : les cours des enseignants (docs/etapes/etape-IA2-cours.md). Seul le TEXTE extrait est gardé, jamais
-- le fichier déposé ; un cours est privé à l'enseignant qui l'a déposé ; le retirer efface tout son texte.

CREATE TABLE cours (
    id INTEGER PRIMARY KEY,
    enseignant_id INTEGER NOT NULL REFERENCES enseignant (id) ON DELETE CASCADE,
    nom TEXT NOT NULL,                       -- le nom du fichier déposé, ou celui que l'enseignant lui donne
    matiere TEXT,                            -- facultatives : pour chercher d'abord dans les cours de la demande
    niveau TEXT,
    format TEXT NOT NULL CHECK (format IN ('pdf', 'docx', 'odt', 'txt')),
    pages INTEGER,                           -- PDF seulement
    mots INTEGER NOT NULL,
    empreinte TEXT NOT NULL,                 -- SHA-256 du texte extrait : le même cours n'est pas déposé deux fois
    ajoute TEXT NOT NULL,
    UNIQUE (enseignant_id, empreinte)
);
CREATE INDEX cours_enseignant ON cours (enseignant_id);

-- le texte découpé en passages d'environ 300 mots, avec leur page (PDF)
CREATE TABLE cours_passage (
    id INTEGER PRIMARY KEY,
    cours_id INTEGER NOT NULL REFERENCES cours (id) ON DELETE CASCADE,
    rang INTEGER NOT NULL,
    page INTEGER,
    texte TEXT NOT NULL
);
CREATE INDEX cours_passage_cours ON cours_passage (cours_id);

-- l'index plein texte des passages (rowid = cours_passage.id) : sans accents, sans majuscules
CREATE VIRTUAL TABLE cours_fts USING fts5 (texte, tokenize = 'unicode61 remove_diacritics 2');
