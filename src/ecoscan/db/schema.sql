-- EcoScan Local — livello relazionale.
--
-- Il database è un artefatto DERIVATO: la verità sta nei file di data/normalizzato/ e
-- data/riferimento/. Il caricamento ricostruisce tutto da zero a ogni esecuzione
-- (vedi ecoscan-carica), quindi qui non servono logiche di aggiornamento.
--
-- Gli indici di ricerca (FTS5, vettori) sono nel livello di serving e si rigenerano da qui.
PRAGMA foreign_keys = ON;

CREATE TABLE comune (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL UNIQUE,
    gestore TEXT NOT NULL
);

-- Flusso di materiale canonico: serve a confrontare comuni che raggruppano diversamente
-- ("Vetro e imballaggi in metallo" a Torino = vetro+metalli; "Plastica e Metalli" a Napoli).
CREATE TABLE flusso (
    codice TEXT PRIMARY KEY
);

-- Dove si conferisce, con il nome usato dal comune. Non è il materiale: è il posto.
CREATE TABLE destinazione (
    id          INTEGER PRIMARY KEY,
    comune_id   INTEGER NOT NULL REFERENCES comune(id),
    nome        TEXT NOT NULL,
    canale      TEXT NOT NULL CHECK (canale IN (
                  'raccolta_ordinaria',    -- bidoni, campane, sacchi
                  'contenitore_dedicato',  -- pile, farmaci, abiti, oli
                  'centro_raccolta',       -- isole ecologiche, centri di raccolta
                  'raccolta_itinerante',   -- ecopunti mobili, ecoisole
                  'ritiro_domicilio')),    -- numero verde, prenotazione ingombranti
    colore      TEXT,
    note        TEXT,
    UNIQUE (comune_id, nome)
);

-- Nomi alternativi della stessa destinazione dentro la stessa fonte
-- ("Cartone" per "Carta e Cartoncino").
CREATE TABLE destinazione_alias (
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    alias           TEXT NOT NULL,
    PRIMARY KEY (destinazione_id, alias)
);

CREATE TABLE destinazione_flusso (
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    flusso_codice   TEXT NOT NULL REFERENCES flusso(codice),
    PRIMARY KEY (destinazione_id, flusso_codice)
);

-- Livello di evidenza 1: il comune ha classificato questo oggetto.
CREATE TABLE voce (
    id                INTEGER PRIMARY KEY,
    comune_id         INTEGER NOT NULL REFERENCES comune(id),
    slug              TEXT NOT NULL,           -- identificatore stabile nella fonte
    nome              TEXT NOT NULL,           -- forma normalizzata, senza condizioni
    nome_originale    TEXT NOT NULL,           -- testo della fonte, mai modificato
    codice_materiale  TEXT,                    -- sigla sull'imballaggio: PET 01, ALU 41...
    avvertenza        TEXT,
    revisione_manuale INTEGER NOT NULL DEFAULT 0,
    UNIQUE (comune_id, slug)
);

-- Ciò che cambia la destinazione a parità di oggetto: pulito/unto, vuoto/pieno...
CREATE TABLE voce_condizione (
    voce_id    INTEGER NOT NULL REFERENCES voce(id),
    condizione TEXT NOT NULL,
    PRIMARY KEY (voce_id, condizione)
);

CREATE TABLE voce_alias (
    voce_id INTEGER NOT NULL REFERENCES voce(id),
    alias   TEXT NOT NULL,
    PRIMARY KEY (voce_id, alias)
);

-- Destinazioni ALTERNATIVE (semantica OR): un divano si porta all'isola ecologica
-- OPPURE si fa ritirare. `ordine` conserva la sequenza della fonte.
CREATE TABLE voce_destinazione (
    voce_id         INTEGER NOT NULL REFERENCES voce(id),
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    ordine          INTEGER NOT NULL,
    PRIMARY KEY (voce_id, destinazione_id)
);

-- Livello di evidenza 2: cosa entra o non entra in un contenitore, per categoria.
CREATE TABLE regola (
    id              INTEGER PRIMARY KEY,
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    polarita        TEXT NOT NULL CHECK (polarita IN ('ammesso', 'escluso', 'nota')),
    testo           TEXT NOT NULL,
    dettaglio       TEXT,
    origine         TEXT NOT NULL CHECK (origine IN ('estrazione', 'trascrizione_manuale')),
    fonte           TEXT NOT NULL,
    riferimento     TEXT NOT NULL             -- URL della pagina o pagina del PDF
);

-- Le decisioni prese a mano, caricate per poterle interrogare e contare.
CREATE TABLE decisione_revisione (
    id        INTEGER PRIMARY KEY,
    comune_id INTEGER NOT NULL REFERENCES comune(id),
    slug      TEXT NOT NULL,
    azione    TEXT NOT NULL,
    valore    TEXT,
    nota      TEXT
);

-- Traccia di come è stato costruito questo database: serve a sapere se è aggiornato.
CREATE TABLE caricamento (
    eseguito_il   TEXT NOT NULL,
    versione      TEXT NOT NULL,
    file_sorgente TEXT NOT NULL,
    righe         INTEGER NOT NULL
);

CREATE INDEX idx_voce_comune ON voce(comune_id);
CREATE INDEX idx_voce_nome ON voce(nome);
CREATE INDEX idx_destinazione_comune ON destinazione(comune_id);
CREATE INDEX idx_regola_destinazione ON regola(destinazione_id);
