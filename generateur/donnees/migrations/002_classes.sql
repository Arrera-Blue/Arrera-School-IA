-- E3 : classes et élèves (docs/etapes/etape-E3-classes.md). Minimisation (D6) : nom, prénom, classe, numéro,
-- empreinte du code ; ni date de naissance, ni photo, ni INE, ni champ libre (registre, docs/rgpd/registre.md §5).

CREATE TABLE classe (
    id INTEGER PRIMARY KEY,
    enseignant_id INTEGER NOT NULL REFERENCES enseignant (id),   -- un compte qui a des classes ne se supprime pas
    nom TEXT NOT NULL,                                           -- « 6e B »
    niveau TEXT NOT NULL CHECK (niveau IN ('6e', '5e', '4e', '3e')),
    annee TEXT NOT NULL,                                         -- « 2026-2027 » : la purge de juillet s'appuie dessus
    archivee INTEGER NOT NULL DEFAULT 0,
    dernier_numero INTEGER NOT NULL DEFAULT 0,                   -- un numéro d'élève n'est jamais redonné
    creee TEXT NOT NULL,
    UNIQUE (enseignant_id, nom, annee)
);
CREATE INDEX classe_enseignant ON classe (enseignant_id);

CREATE TABLE eleve (
    id INTEGER PRIMARY KEY,
    classe_id INTEGER NOT NULL REFERENCES classe (id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,          -- son numéro dans la classe, jamais réutilisé : identifie sans nom (mode C)
    nom TEXT NOT NULL,
    prenom TEXT NOT NULL,
    code TEXT NOT NULL,               -- empreinte du code de 4 images (scrypt + clé secrète, ⚖3) : jamais le code
    actif INTEGER NOT NULL DEFAULT 1, -- 0 : limitation (RGPD) : ne se connecte plus, rien n'est enregistré
    cree TEXT NOT NULL,
    UNIQUE (classe_id, numero)
);
CREATE INDEX eleve_classe ON eleve (classe_id);
