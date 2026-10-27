-- E8 : le serveur de classe (docs/etapes/etape-E8-serveur.md) : la connexion des élèves, les exercices publiés, les
-- réponses envoyées en direct.

-- comment les élèves d'une classe se connectent : 4 images (6e), ou un mot de passe imprimé sur la carte (5e à 3e,
-- choix du 27/10) ; les classes créées avant gardent leurs images
ALTER TABLE classe ADD COLUMN connexion TEXT NOT NULL DEFAULT 'images' CHECK (connexion IN ('images', 'mot_de_passe'));

-- 5 essais manqués de suite : l'élève est bloqué, jusqu'à ce que l'enseignant le débloque (ou refasse son code)
ALTER TABLE eleve ADD COLUMN echecs INTEGER NOT NULL DEFAULT 0;
ALTER TABLE eleve ADD COLUMN bloque INTEGER NOT NULL DEFAULT 0;

-- 1 : la tentative compte dans le suivi (la première de l'élève sur cet exercice) ; 0 : entraînement (rejouée)
ALTER TABLE tentative ADD COLUMN compte INTEGER NOT NULL DEFAULT 1;

-- un exercice accepté, publié pour une classe, un de ses groupes de besoins ou un de ses élèves
CREATE TABLE publication (
    id INTEGER PRIMARY KEY,
    classe_id INTEGER NOT NULL REFERENCES classe (id) ON DELETE CASCADE,
    groupe_id INTEGER REFERENCES groupe (id) ON DELETE CASCADE,   -- vide : toute la classe
    eleve_id INTEGER REFERENCES eleve (id) ON DELETE CASCADE,     -- vide : toute la classe, ou le groupe
    exercice TEXT NOT NULL,                                        -- identifiant de l'exercice (banque)
    titre TEXT,                                                    -- son titre à la publication
    debut TEXT,                                                    -- facultatif, AAAA-MM-JJ
    fin TEXT,                                                      -- facultatif, AAAA-MM-JJ (inclus)
    creee TEXT NOT NULL,
    CHECK (groupe_id IS NULL OR eleve_id IS NULL)
);
CREATE INDEX publication_classe ON publication (classe_id);

-- les sessions des élèves, sur le serveur de classe : courtes (10 minutes sans activité) ; le jeton n'est connu que
-- du navigateur, la base garde son empreinte SHA-256
CREATE TABLE session_eleve (
    empreinte TEXT PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleve (id) ON DELETE CASCADE,
    creee REAL NOT NULL,
    activite REAL NOT NULL
);
CREATE INDEX session_eleve_eleve ON session_eleve (eleve_id);
