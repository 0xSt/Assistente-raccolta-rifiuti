-- EcoScan Local: schema normalizzato comune (SQLite)
-- Livelli: GREZZO (cosa abbiamo scaricato) -> NORMALIZZATO (cosa dice il comune) -> SERVING (cosa cerca l'agente)
PRAGMA foreign_keys = ON;

-- =========================================================================== GREZZO
CREATE TABLE fonte (
    id              INTEGER PRIMARY KEY,
    codice          TEXT NOT NULL UNIQUE,            -- 'amiat_rifiutologo_2025', 'asia_napoli_dove_lo_butto'
    comune_id       INTEGER NOT NULL REFERENCES comune(id),
    ente            TEXT NOT NULL,                   -- 'AMIAT', 'ASIA Napoli'
    formato         TEXT NOT NULL CHECK (formato IN ('pdf', 'html')),
    url             TEXT NOT NULL,
    ambito          TEXT                             -- es. 'solo utenze domestiche'
);

CREATE TABLE snapshot (                              -- un file scaricato: PDF intero o singola pagina HTML
    id              INTEGER PRIMARY KEY,
    fonte_id        INTEGER NOT NULL REFERENCES fonte(id),
    url             TEXT NOT NULL,
    recuperato_il   TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    UNIQUE (url, sha256)                             -- stessa pagina, stesso contenuto: nessun duplicato
);

CREATE TABLE record_grezzo (                         -- output dell'estrattore, non interpretato
    id                  INTEGER PRIMARY KEY,
    snapshot_id         INTEGER NOT NULL REFERENCES snapshot(id),
    tipo                TEXT NOT NULL CHECK (tipo IN ('voce', 'regola_categoria')),
    posizione           TEXT NOT NULL,               -- 'pagina 17' | slug
    payload             TEXT NOT NULL,               -- JSON così come estratto
    versione_estrattore TEXT NOT NULL
);

-- =========================================================================== NORMALIZZATO
CREATE TABLE comune (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL UNIQUE,
    gestore TEXT NOT NULL
);

-- Flussi di materiale canonici: servono a confrontare comuni con raggruppamenti diversi
CREATE TABLE flusso (
    codice  TEXT PRIMARY KEY,                        -- 'carta', 'plastica', 'metalli', 'vetro', 'organico', 'residuo', ...
    nome    TEXT NOT NULL
);

-- Dove si conferisce, così come lo chiama il comune: contenitore, centro di raccolta, servizio
CREATE TABLE destinazione (
    id           INTEGER PRIMARY KEY,
    comune_id    INTEGER NOT NULL REFERENCES comune(id),
    nome_locale  TEXT NOT NULL,                      -- 'Plastica e Metalli', 'Isola Ecologica Estesa'
    canale       TEXT NOT NULL CHECK (canale IN (
                   'raccolta_ordinaria',             -- bidoni/campane/sacchi
                   'contenitore_dedicato',           -- pile, farmaci, abiti, oli, ecoisole RAEE
                   'centro_raccolta',                -- isole ecologiche, centri di raccolta
                   'raccolta_itinerante',            -- ecopunti mobili
                   'ritiro_domicilio')),             -- numero verde, prenotazione ingombranti
    colore       TEXT,
    descrizione  TEXT,
    UNIQUE (comune_id, nome_locale)
);

CREATE TABLE destinazione_alias (                    -- stessa destinazione, nomi diversi nella stessa fonte
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    alias           TEXT NOT NULL,                   -- Napoli: 'Carta e Cartoncino' (indice) = 'Carta e Cartone' (frazioni)
    PRIMARY KEY (destinazione_id, alias)
);

CREATE TABLE destinazione_flusso (                   -- molti-a-molti: 'Plastica e Metalli' -> plastica + metalli
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    flusso_codice   TEXT NOT NULL REFERENCES flusso(codice),
    PRIMARY KEY (destinazione_id, flusso_codice)
);

-- Livello 1 di evidenza: il comune ha classificato questo oggetto
CREATE TABLE voce (
    id                  INTEGER PRIMARY KEY,
    comune_id           INTEGER NOT NULL REFERENCES comune(id),
    nome_originale      TEXT NOT NULL,               -- testo della fonte, mai modificato
    nome                TEXT NOT NULL,               -- forma pulita, senza condizione
    condizione          TEXT,                        -- 'con residui', 'solo se certificato compostabile', 'piccole quantità'
    origine             TEXT NOT NULL CHECK (origine IN ('dizionario', 'esempio_guida')),
    record_grezzo_id    INTEGER NOT NULL REFERENCES record_grezzo(id),
    oggetto_canonico_id INTEGER,                     -- facoltativo: entity resolution tra comuni, in futuro
    stato               TEXT NOT NULL DEFAULT 'attiva' CHECK (stato IN ('attiva', 'da_revisionare', 'esclusa'))
);

CREATE TABLE voce_alias (
    voce_id  INTEGER NOT NULL REFERENCES voce(id),
    alias    TEXT NOT NULL,
    origine  TEXT NOT NULL CHECK (origine IN ('split_voce', 'slug', 'manuale')),
    PRIMARY KEY (voce_id, alias)
);

-- Destinazioni ALTERNATIVE (semantica OR): 'Divani' -> ingombranti oppure centro di raccolta
CREATE TABLE voce_destinazione (
    voce_id         INTEGER NOT NULL REFERENCES voce(id),
    destinazione_id INTEGER NOT NULL REFERENCES destinazione(id),
    ordine          INTEGER NOT NULL,                -- ordine di presentazione nella fonte
    PRIMARY KEY (voce_id, destinazione_id)
);

-- Livello 2 di evidenza: cosa entra (o non entra) in una destinazione, in forma di categoria
CREATE TABLE regola_categoria (
    id               INTEGER PRIMARY KEY,
    destinazione_id  INTEGER NOT NULL REFERENCES destinazione(id),
    polarita         TEXT NOT NULL CHECK (polarita IN ('ammesso', 'escluso', 'nota')),
    testo            TEXT NOT NULL,                  -- 'Caffettiere, pentole, padelle in metallo'
    dettaglio        TEXT,                           -- '(non etichettate T e F)'
    record_grezzo_id INTEGER NOT NULL REFERENCES record_grezzo(id)
);

-- Avvertenze testuali: nota a piè di pagina (Torino), campo avvertenza (Napoli), istruzione nello slug
CREATE TABLE avvertenza (
    id          INTEGER PRIMARY KEY,
    voce_id     INTEGER REFERENCES voce(id),
    regola_id   INTEGER REFERENCES regola_categoria(id),
    testo       TEXT NOT NULL,
    origine     TEXT NOT NULL CHECK (origine IN ('nota_pie_pagina', 'campo_avvertenza', 'slug', 'nota_categoria')),
    CHECK ((voce_id IS NULL) <> (regola_id IS NULL))
);

-- Registro dei problemi di qualità: materiale per la relazione e per la revisione manuale
CREATE TABLE problema_qualita (
    id               INTEGER PRIMARY KEY,
    record_grezzo_id INTEGER NOT NULL REFERENCES record_grezzo(id),
    codice           TEXT NOT NULL,                  -- 'placeholder', 'info_nello_slug', 'slug_duplicato', 'refuso', ...
    dettaglio        TEXT,
    risolto          INTEGER NOT NULL DEFAULT 0
);

-- =========================================================================== SERVING
-- Unità ricercabili: voci (livello 1) e regole di categoria ammesse (livello 2)
CREATE VIEW scheda AS
SELECT 'voce:' || v.id           AS scheda_id,
       v.comune_id,
       1                         AS livello_evidenza,
       v.nome || COALESCE(' (' || v.condizione || ')', '')
         || COALESCE(' ' || (SELECT group_concat(alias, ' ') FROM voce_alias a WHERE a.voce_id = v.id), '')
                                 AS testo_ricerca
FROM voce v WHERE v.stato = 'attiva'
UNION ALL
SELECT 'regola:' || r.id, d.comune_id, 2, r.testo || COALESCE(' ' || r.dettaglio, '')
FROM regola_categoria r JOIN destinazione d ON d.id = r.destinazione_id
WHERE r.polarita = 'ammesso';

-- Indice lessicale a trigrammi (tollera plurali ed errori); popolato dallo script di caricamento
CREATE VIRTUAL TABLE scheda_fts USING fts5(scheda_id UNINDEXED, comune_id UNINDEXED, testo_ricerca, tokenize = 'trigram');

-- Vettori per la ricerca semantica: un BLOB per scheda e modello di embedding
CREATE TABLE scheda_embedding (
    scheda_id  TEXT NOT NULL,
    modello    TEXT NOT NULL,                        -- 'embeddinggemma-300m@256'
    vettore    BLOB NOT NULL,
    PRIMARY KEY (scheda_id, modello)
);

CREATE INDEX idx_voce_comune ON voce(comune_id);
CREATE INDEX idx_destinazione_comune ON destinazione(comune_id);
