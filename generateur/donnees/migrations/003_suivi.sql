-- E4 : le suivi des élèves (docs/etapes/etape-E4-suivi.md). Mesures (D7) : la proposition choisie, juste ou non
-- (recalculé par le PC enseignant, jamais cru du navigateur), le temps passé, l'attendu du programme ; rien d'autre.

-- un passage d'un élève sur un exercice
CREATE TABLE tentative (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleve (id) ON DELETE CASCADE,
    exercice TEXT NOT NULL,           -- identifiant de l'exercice (banque)
    titre TEXT,                       -- son titre au moment de la tentative (l'exercice peut quitter la banque)
    empreinte TEXT NOT NULL,          -- SHA-256 du contenu de l'exercice : recalculer sur la bonne version
    origine TEXT NOT NULL CHECK (origine IN ('simulation', 'classe', 'import')),  -- E4 simulation, E8 serveur
    date TEXT NOT NULL,
    annulee INTEGER NOT NULL DEFAULT 0  -- faite par erreur (rectification, RGPD) : ne compte plus
);
CREATE INDEX tentative_eleve ON tentative (eleve_id);

CREATE TABLE reponse (
    id INTEGER PRIMARY KEY,
    tentative_id INTEGER NOT NULL REFERENCES tentative (id) ON DELETE CASCADE,
    question INTEGER NOT NULL,        -- numéro de la question (1, 2…)
    choix INTEGER NOT NULL,           -- la proposition choisie (0 à 3)
    juste INTEGER NOT NULL,           -- recalculé à partir de l'exercice
    temps_s REAL,
    attendu TEXT,                     -- l'attendu (ou le thème) du programme que la question travaille
    difficulte TEXT,                  -- facile | moyen | difficile, si l'exercice le dit
    UNIQUE (tentative_id, question)
);
CREATE INDEX reponse_attendu ON reponse (attendu);

-- les groupes de besoins, proposés par l'outil, ajustés et gardés par l'enseignant
CREATE TABLE groupe (
    id INTEGER PRIMARY KEY,
    classe_id INTEGER NOT NULL REFERENCES classe (id) ON DELETE CASCADE,
    nom TEXT NOT NULL,
    attendu TEXT,                     -- l'attendu à consolider, ou à approfondir
    nature TEXT NOT NULL CHECK (nature IN ('consolider', 'approfondir')),
    cree TEXT NOT NULL
);
CREATE TABLE groupe_eleve (
    groupe_id INTEGER NOT NULL REFERENCES groupe (id) ON DELETE CASCADE,
    eleve_id INTEGER NOT NULL REFERENCES eleve (id) ON DELETE CASCADE,
    PRIMARY KEY (groupe_id, eleve_id)
);

-- les exercices à travailler, proposés par l'outil, validés par l'enseignant (aucune décision automatique)
CREATE TABLE proposition (
    id INTEGER PRIMARY KEY,
    eleve_id INTEGER NOT NULL REFERENCES eleve (id) ON DELETE CASCADE,
    nature TEXT NOT NULL CHECK (nature IN ('retravailler', 'plus_loin')),
    attendu TEXT NOT NULL,
    exercice TEXT,                    -- un exercice de la banque ; vide : « à générer »
    cree TEXT NOT NULL
);
CREATE INDEX proposition_eleve ON proposition (eleve_id);
