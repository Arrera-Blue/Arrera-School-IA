-- Le cycle 2 (générateur procédural du cycle 2, lot 0 : docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md) : des
-- classes de CP, de CE1 et de CE2. SQLite ne modifie pas une contrainte CHECK : la table est reconstruite à
-- l'identique, sauf la liste des classes (la méthode de la documentation de SQLite : nouvelle table, copie, ancienne
-- supprimée, nouvelle renommée). migrer() coupe les clés étrangères le temps de la migration (sinon, supprimer
-- l'ancienne table effacerait en cascade les élèves, les groupes et les publications), puis vérifie qu'aucune n'est
-- cassée avant de valider. Les élèves, les groupes et les publications gardent leur classe : mêmes identifiants.

CREATE TABLE classe_cycle2 (
    id INTEGER PRIMARY KEY,
    enseignant_id INTEGER NOT NULL REFERENCES enseignant (id),   -- un compte qui a des classes ne se supprime pas
    nom TEXT NOT NULL,                                           -- « 6e B », « CP A »
    niveau TEXT NOT NULL CHECK (niveau IN ('CP', 'CE1', 'CE2', '6e', '5e', '4e', '3e')),
    annee TEXT NOT NULL,                                         -- « 2026-2027 » : la purge de juillet s'appuie dessus
    archivee INTEGER NOT NULL DEFAULT 0,
    dernier_numero INTEGER NOT NULL DEFAULT 0,                   -- un numéro d'élève n'est jamais redonné
    creee TEXT NOT NULL,
    -- 4 images (du CP à la 6e), ou un mot de passe imprimé sur la carte (5e à 3e) ; E8
    connexion TEXT NOT NULL DEFAULT 'images' CHECK (connexion IN ('images', 'mot_de_passe')),
    UNIQUE (enseignant_id, nom, annee)
);

INSERT INTO classe_cycle2 (id, enseignant_id, nom, niveau, annee, archivee, dernier_numero, creee, connexion)
    SELECT id, enseignant_id, nom, niveau, annee, archivee, dernier_numero, creee, connexion FROM classe;

DROP TABLE classe;
ALTER TABLE classe_cycle2 RENAME TO classe;
CREATE INDEX classe_enseignant ON classe (enseignant_id);
