"""Test della valutazione: i casi e la diagnosi.

Si misura la meccanica della misura, non la qualità del sistema: che un caso si legga e si
scriva senza doppioni, che la diagnosi distingua un recupero fallito da una scelta
sbagliata, e che una misura non dichiari di sapere ciò che non ha misurato.
"""
import json
from contextlib import contextmanager

import pytest

from ecoscan.osservabilita.tracciamento import SpanNullo, TracciatoreNullo

from ecoscan.agente.agente import Agente
from ecoscan.valutazione import esegui as val
from ecoscan.valutazione.casi import Caso, aggiungi, leggi

# --------------------------------------------------------------------------- i casi


def test_un_caso_diventa_un_riconoscimento_certo():
    """Il riconoscimento è un dato, non un'ipotesi: la soglia di confidenza non va rieseguita."""
    caso = Caso(comune="Napoli", oggetto="forchetta", materiali=["acciaio"],
                destinazioni_attese=["Plastica e Metalli"])
    riconoscimento = caso.riconoscimento
    assert riconoscimento.oggetto == "forchetta"
    assert riconoscimento.materiali == ["acciaio"]
    assert riconoscimento.confidenza == 1.0


def test_un_caso_senza_attesa_non_e_valido():
    assert not Caso(comune="Napoli", oggetto="forchetta").valido
    assert not Caso(comune="Napoli", oggetto="", destinazioni_attese=["x"]).valido
    assert Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["x"]).valido


def test_lo_stesso_caso_non_si_aggiunge_due_volte(tmp_path):
    """Lo stesso caso ripetuto gonfierebbe le percentuali senza misurare niente di nuovo."""
    percorso = tmp_path / "casi.jsonl"
    caso = Caso(comune="Napoli", oggetto="forchetta", destinazioni_attese=["Indifferenziata"])
    assert aggiungi(caso, percorso) is True
    assert aggiungi(caso, percorso) is False
    assert len(leggi(percorso)) == 1


def test_un_campo_sconosciuto_nel_file_non_rompe_la_lettura(tmp_path):
    """I file crescono nel tempo: un campo in più di una versione futura non deve fermare
    la valutazione di oggi."""
    percorso = tmp_path / "casi.jsonl"
    percorso.write_text(json.dumps(
        {"comune": "Napoli", "oggetto": "x", "destinazioni_attese": ["y"], "domani": 1}) + "\n",
        encoding="utf-8")
    assert leggi(percorso)[0].oggetto == "x"


# --------------------------------------------------------------------------- la diagnosi

def caso_dei_giornali(**extra) -> Caso:
    """Una voce senza varianti: l'attesa è una sola destinazione, quindi l'esito non dipende
    da quale condizione il codice sceglie."""
    return Caso(comune="Torino", oggetto="giornale",
                destinazioni_attese=["carta_e_cartone"], **extra)


def test_corretto_quando_la_risposta_porta_alla_destinazione_attesa(ambiente):
    from tests.conftest import SceglieIlDocumento
    agente = Agente(ambiente.recupero, SceglieIlDocumento("Giornali"), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali())
    assert esito.diagnosi == val.CORRETTO
    assert esito.recuperato is True


def test_recupero_fallito_quando_il_documento_atteso_non_esce(ambiente):
    """La distinzione che conta: se nessun documento fra i candidati porta dove doveva, il
    modello non poteva sceglierlo, e intervenire sul prompt non servirebbe a niente."""
    from tests.conftest import ModelloFinto
    caso = Caso(comune="Torino", oggetto="giornale",
                destinazioni_attese=["destinazione che nessun documento raggiunge"])
    agente = Agente(ambiente.recupero, ModelloFinto(indice_scelto=0), k=8)
    esito = val.valuta_caso(agente, caso)
    assert esito.recuperato is False
    assert esito.posizione is None
    assert esito.diagnosi == val.RECUPERO_FALLITO


@pytest.mark.parametrize("recuperato, destinazioni, diagnosi", [
    # il documento c'era e la risposta ci è arrivata: niente da fare
    (True, ["carta_e_cartone"], val.CORRETTO),
    # il caso della forchetta: il documento c'era, il modello ha scelto un altro.
    # Si interviene sul prompt di scelta, non sull'indice
    (True, ["organico"], val.SCELTA_SBAGLIATA),
    # il modello non poteva sceglierlo: si interviene sull'indice o sulle formulazioni
    (False, ["organico"], val.RECUPERO_FALLITO),
    # giusto per caso: una regola di categoria ha rimediato a un dizionario incompleto
    (False, ["carta_e_cartone"], val.ALTRA_STRADA),
])
def test_la_diagnosi_dice_dove_intervenire(recuperato, destinazioni, diagnosi):
    """La tabella 2x2 che rende la valutazione azionabile: non "quanto sbaglia", ma
    "dove va messa la prossima ora di lavoro"."""
    esito = val.Esito(caso=caso_dei_giornali(), recuperato=recuperato,
                      destinazioni=destinazioni)
    assert esito.diagnosi == diagnosi


def test_una_scelta_sbagliata_si_riconosce_eseguendo_un_caso(ambiente):
    """La stessa diagnosi, ma dall'esecuzione vera: il modello sceglie un documento che
    porta altrove, e il recupero aveva fatto il suo."""
    from tests.conftest import ModelloFinto
    agente = Agente(ambiente.recupero, ModelloFinto(indice_scelto=0), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali(livello_atteso=1))
    assert esito.recuperato is True
    assert esito.livello_corretto is not None


def test_senza_modello_si_misura_il_solo_recupero(ambiente):
    """La modalità piu utile mentre si lavora sull'indice: non tocca il modello, quindi si
    esegue in secondi invece che in minuti, e misura il tetto."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali(), con_modello=False)
    assert esito.valutata_la_scelta is False
    assert esito.recuperato is True
    assert val.misure([esito])["risposte_perfette"] is None


def test_le_misure_sono_percentuali_sui_casi_eseguiti(ambiente):
    from tests.conftest import SceglieIlDocumento
    agente = Agente(ambiente.recupero, SceglieIlDocumento("Giornali"), k=8)
    esiti = [val.valuta_caso(agente, caso_dei_giornali())]
    misure = val.misure(esiti)
    assert misure["casi"] == 1
    assert misure["recupero"] == 100.0


def test_senza_casi_le_misure_non_esplodono():
    assert val.misure([])["casi"] == 0


@pytest.mark.parametrize("destinazioni, attese, atteso", [
    (["carta_e_cartone"], ["carta_e_cartone"], True),
    # basta una destinazione in comune: un oggetto con piu varianti ne offre parecchie
    (["organico", "carta_e_cartone"], ["carta_e_cartone"], True),
    (["organico"], ["carta_e_cartone"], False),
    ([], ["carta_e_cartone"], False),
])
def test_un_documento_porta_alla_destinazione_attesa(destinazioni, attese, atteso):
    from ecoscan.agente.tipi import Candidato, Variante
    candidato = Candidato(id="x", livello=1, testo="t",
                          varianti=[Variante(destinazioni=destinazioni)])
    assert val.porta_alla_destinazione(candidato, attese) is atteso


# ------------------------------------------ una misura che non sa non deve dire di sapere

def test_senza_modello_il_livello_non_si_misura():
    """Il difetto del 18/09: senza modello il livello non viene mai determinato, e
    confrontare None con l'atteso dava False per ogni caso. La misura riportava "0% di
    livelli corretti" su un'esecuzione in cui il livello non era stato misurato affatto.
    Una metrica che mente è peggio di una che manca, perché la si legge."""
    caso = caso_dei_giornali(livello_atteso=1)
    senza = val.Esito(caso=caso, recuperato=True, valutata_la_scelta=False)
    assert senza.livello_corretto is None
    assert val.misure([senza])["livello_atteso"] is None


def test_con_modello_il_livello_si_misura_eccome():
    caso = caso_dei_giornali(livello_atteso=1)
    assert val.Esito(caso=caso, recuperato=True, livello=1).livello_corretto is True
    assert val.Esito(caso=caso, recuperato=True, livello=2).livello_corretto is False


def test_senza_modello_la_diagnosi_non_dice_corretto():
    """"corretto" farebbe leggere come risposta giusta ciò che è solo un documento trovato."""
    senza = val.Esito(caso=caso_dei_giornali(), recuperato=True, valutata_la_scelta=False)
    assert senza.diagnosi == val.RECUPERATO
    assert "non è stata valutata" in senza.diagnosi


def test_un_esito_dice_dove_portavano_i_documenti_trovati(ambiente):
    """Serve a distinguere un recupero fallito da un'attesa sbagliata, che è l'errore che
    ho fatto io col frullatore: il sistema aveva ragione e il caso no."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8)
    esito = val.valuta_caso(agente, caso_dei_giornali(), con_modello=False)
    assert "carta_e_cartone" in esito.raggiungibili


# ------------------------------------------------- i due errori della risposta, separati

def caso_del_microonde(**extra) -> Caso:
    """Una voce con tre canali: è il caso su cui l'uguaglianza esatta non bastava più.
    La risposta poteva essere vera e insufficiente, e il vecchio numero non lo diceva."""
    return Caso(comune="Napoli", oggetto="microonde",
                destinazioni_attese=["Isola Ecologica Estesa", "Ecopunto Elettrodomestici",
                                     "Numero Verde Gratuito"], **extra)


def test_un_contenitore_sbagliato_e_un_canale_perso_non_sono_lo_stesso_errore():
    """Il primo manda una persona nel cassonetto sbagliato, il secondo le fa solo fare più
    strada: confonderli in un numero solo nasconde quale dei due si sta riparando."""
    perso = val.Esito(caso=caso_del_microonde(), recuperato=True,
                      destinazioni=["Isola Ecologica Estesa"])
    sbagliato = val.Esito(caso=caso_del_microonde(), recuperato=True,
                          destinazioni=["Organico"])
    assert perso.contenitore_corretto is True and round(perso.copertura, 2) == 0.33
    assert sbagliato.contenitore_corretto is False and sbagliato.copertura == 0.0
    assert perso.diagnosi == val.CANALE_PERSO
    assert sbagliato.diagnosi == val.SCELTA_SBAGLIATA


def test_la_risposta_perfetta_e_quella_completa():
    completa = val.Esito(caso=caso_del_microonde(), recuperato=True,
                         destinazioni=["Numero Verde Gratuito", "Isola Ecologica Estesa",
                                       "Ecopunto Elettrodomestici"])
    assert completa.perfetta is True
    assert completa.diagnosi == val.CORRETTO


def test_il_dettaglio_dice_cosa_manca_e_cosa_e_di_troppo():
    """Nell'uscita non si deve dedurre la differenza fra due elenchi a occhio."""
    esito = val.Esito(caso=caso_del_microonde(), recuperato=True,
                      destinazioni=["Isola Ecologica Estesa", "Organico"])
    assert esito.di_troppo == ["Organico"]
    assert "Numero Verde Gratuito" in esito.mancate


def test_la_copertura_media_e_una_percentuale_sulle_attese():
    esiti = [val.Esito(caso=caso_del_microonde(), recuperato=True,
                       destinazioni=["Isola Ecologica Estesa"]),
             val.Esito(caso=caso_dei_giornali(), recuperato=True,
                       destinazioni=["carta_e_cartone"])]
    misure = val.misure(esiti)
    assert misure["contenitore_corretto"] == 100.0     # nessuna destinazione sbagliata
    assert misure["risposte_perfette"] == 50.0         # ma un canale perso
    assert misure["copertura"] == round(100 * (1 / 3 + 1) / 2, 1)


# --------------------------------------------------------------- la curva del recall

def test_il_recall_si_legge_a_piu_profondita():
    """Se il documento esce ma tardi, il problema è l'ordinamento e non l'indice: una media
    delle posizioni non lo direbbe, e per giunta peggiorerebbe quando un caso difficile
    comincia finalmente a uscire."""
    esiti = [val.Esito(caso=caso_dei_giornali(), recuperato=True, posizione=1),
             val.Esito(caso=caso_dei_giornali(), recuperato=True, posizione=6),
             val.Esito(caso=caso_dei_giornali(), recuperato=False)]
    misure = val.misure(esiti, k=8)
    assert misure["recall@1"] == 33.3
    assert misure["recall@4"] == 33.3
    assert misure["recall@8"] == 66.7
    assert misure["recupero"] == misure["recall@8"]


def test_le_soglie_seguono_k():
    """Lanciare con -k 20 e leggere una curva ferma a 8 non direbbe nulla su ciò che si
    sta provando."""
    assert val.soglie_recall(8) == [1, 4, 8]
    assert val.soglie_recall(20) == [1, 10, 20]


# --------------------------------------------------------------- i casi negativi

def caso_assente(**extra) -> Caso:
    return Caso(comune="Napoli", oggetto="tavola da surf", destinazioni_attese=[],
                livello_atteso=3, origine="assenti", **extra)


def test_un_caso_senza_attese_e_valido_solo_se_dichiara_il_livello_tre():
    """L'attesa vuota deve essere una dichiarazione, non una riga scritta a metà."""
    assert caso_assente().valido is True
    assert caso_assente().negativo is True
    assert not Caso(comune="Napoli", oggetto="tavola da surf").valido


def test_astenersi_e_la_risposta_giusta_quando_il_comune_non_copre_l_oggetto():
    """Il difetto classico di un RAG è rispondere comunque: senza casi negativi non ha
    un numero e resta invisibile."""
    zitto = val.Esito(caso=caso_assente(), recuperato=False, destinazioni=[], livello=3)
    parlante = val.Esito(caso=caso_assente(), recuperato=False,
                         destinazioni=["Plastica e Metalli"], livello=1)
    assert zitto.diagnosi == val.ASTENUTO
    assert parlante.diagnosi == val.NON_ASTENUTO
    misure = val.misure([zitto, parlante])
    assert misure["astensione_corretta"] == 50.0


def test_i_casi_negativi_non_entrano_nel_recall():
    """Un caso senza attese non ha un documento da recuperare: contarlo come recupero
    fallito abbasserebbe il tetto per un motivo inventato."""
    misure = val.misure([val.Esito(caso=caso_assente(), recuperato=False, destinazioni=[])])
    assert misure["recall@8"] is None


def test_astenersi_troppo_e_un_difetto_a_sua_volta():
    """Un sistema muto non è prudente: le due astensioni si leggono in coppia."""
    muto = val.Esito(caso=caso_dei_giornali(), recuperato=True, destinazioni=[], livello=3)
    assert val.misure([muto])["astensione_a_sproposito"] == 100.0


# ------------------------------------- le condizioni in cui la misura è stata presa

class AgenteFinto:
    def configurazione(self):
        return {"modello_visione": "gemma3:4b", "prompt_scelta": "scelta v8@a3f1"}


def test_l_esecuzione_porta_con_se_la_sua_configurazione():
    """Senza, si confronta una run a k=8 con una a k=12 e si legge la differenza come
    merito della modifica."""
    esecuzione = val.descrizione_esecuzione(
        AgenteFinto(), [caso_dei_giornali(), caso_assente()], k=8, con_modello=True)
    assert esecuzione["k"] == 8 and esecuzione["modalita"] == "completa"
    assert esecuzione["configurazione"]["modello_visione"] == "gemma3:4b"
    assert esecuzione["casi"] == {"regressioni": 1, "assenti": 1}
    assert esecuzione["data"]


def test_il_confronto_si_accorge_che_le_condizioni_sono_cambiate():
    prima = {"k": 8, "modalita": "completa", "configurazione": {"prompt_scelta": "v8"}}
    adesso = {"k": 12, "modalita": "completa", "configurazione": {"prompt_scelta": "v9"}}
    differenze = val.differenze_di_configurazione(prima, adesso)
    assert differenze["k"] == (8, 12)
    assert differenze["prompt_scelta"] == ("v8", "v9")
    assert "modalita" not in differenze


def test_l_esito_salvato_contiene_le_condizioni():
    esiti = [val.Esito(caso=caso_dei_giornali(), recuperato=True, posizione=1,
                       destinazioni=["carta_e_cartone"])]
    salvato = val.come_json(esiti, {"k": 8}, k=8)
    assert salvato["esecuzione"] == {"k": 8}
    assert salvato["misure"]["recall@8"] == 100.0
    primo = next(iter(salvato["esiti"].values()))
    assert primo["contenitore_corretto"] is True and primo["copertura"] == 1.0


# --------------------------------------------------- il dataset vero, quello sul disco

def test_i_tre_insiemi_si_leggono_e_non_si_mescolano():
    from ecoscan.valutazione.casi import INSIEMI, tutti
    casi = tutti()
    origini = {c.origine for c in casi}
    assert origini <= set(INSIEMI) and len(origini) >= 2
    assert len(casi) >= 60, "il dataset si è svuotato"


def test_nessuna_domanda_coincide_con_la_voce_da_cui_nasce():
    """La regola d'oro del campione: cercare "Cartone per pizze" e trovare "Cartone per
    pizze" non misura il recupero, misura che l'indice esiste. Un dataset tautologico
    produce percentuali alte e informazione zero."""
    from ecoscan.valutazione.casi import tutti
    tautologici = [c.id for c in tutti()
                   if c.voce_fonte and c.oggetto.strip().lower() == c.voce_fonte.strip().lower()]
    assert not tautologici, f"domande uguali alla voce di origine: {tautologici}"


def test_ogni_caso_del_campione_dichiara_da_dove_viene_l_attesa():
    """L'attesa del campione viene dal database, non dalla memoria di chi l'ha scritta:
    `voce_fonte` è ciò che permette di ricontrollarla."""
    from ecoscan.valutazione.casi import tutti
    senza = [c.id for c in tutti() if c.origine == "campione" and not c.voce_fonte]
    assert not senza, f"casi del campione senza voce di origine: {senza}"


def test_i_casi_assenti_dichiarano_il_livello_tre_e_una_verifica():
    from ecoscan.valutazione.casi import tutti
    assenti = [c for c in tutti() if c.origine == "assenti"]
    assert len(assenti) >= 8
    assert all(c.negativo and c.livello_atteso == 3 for c in assenti)
    assert all(c.nota for c in assenti), "un'assenza senza verifica scritta non è un dato"


# --------------------------------------------------------- l'avanzamento a schermo

def test_l_avanzamento_dice_a_che_punto_siamo(capsys):
    """Anche `--senza-modello` calcola un embedding per ogni formulazione di ogni caso:
    su CPU sono minuti, e senza avanzamento sembra bloccato."""
    avanzamento = val.Avanzamento(totale=3, interattivo=False)
    esito = val.Esito(caso=caso_dei_giornali(), recuperato=True, posizione=1,
                      destinazioni=["carta_e_cartone"])
    for numero in (1, 2, 3):
        avanzamento(numero, 3, esito.caso, esito)
    uscita = capsys.readouterr().out
    assert "[  3/3]" in uscita and "ok" in uscita
    assert "s/caso" in uscita


def test_l_avanzamento_segnala_i_casi_falliti_mentre_passano(capsys):
    """Un errore visto al centesimo caso si guarda subito, non dopo il riepilogo."""
    avanzamento = val.Avanzamento(totale=1, interattivo=False)
    fallito = val.Esito(caso=caso_dei_giornali(), recuperato=True, destinazioni=["organico"])
    avanzamento(1, 1, fallito.caso, fallito)
    assert "NO" in capsys.readouterr().out


def test_l_esecuzione_chiama_l_avanzamento_dopo_ogni_caso(ambiente):
    """Dopo, non prima: così la riga può dire com'è andato invece di annunciare cosa sta
    per fare."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    visti = []
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8)
    val.esegui(agente, [caso_dei_giornali()], con_modello=False,
               avanzamento=lambda n, t, c, e: visti.append((n, t, c.id, e.recuperato)))
    assert visti == [(1, 1, "Torino · giornale", True)]


# --------------------------------------------------- una traccia per ogni caso

class TracciatoreFinto(TracciatoreNullo):
    """Registra cosa gli è stato chiesto, senza parlare con MLflow. Eredita dal nullo, così
    se l'interfaccia cambia questo test se ne accorge invece di inventarsene una sua."""

    def __init__(self):
        self.turni, self.etichette, self.uscite = [], [], []

    @contextmanager
    def turno(self, nome, conversazione, ingressi):
        self.turni.append((nome, conversazione, ingressi))
        raccolte = self.uscite

        class Radice(SpanNullo):
            trace_id = "tr-finto"

            def uscita(self, valore):
                raccolte.append(valore)

        yield Radice()

    def etichetta(self, span, **tag):
        self.etichette.append(tag)


def test_ogni_caso_apre_la_sua_traccia(ambiente):
    """Le percentuali dicono quanti casi vanno male; la traccia dice perché *quel* caso è
    andato male. Senza, la valutazione resta un contatore."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    tracciatore = TracciatoreFinto()
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8, tracciatore=tracciatore)
    val.valuta_caso(agente, caso_dei_giornali(), con_modello=False, sessione="prova")

    nome, sessione, ingressi = tracciatore.turni[0]
    assert (nome, sessione) == ("valutazione", "prova")
    assert ingressi["caso"] == "Torino · giornale"
    assert ingressi["destinazioni_attese"] == ["carta_e_cartone"]
    assert tracciatore.uscite[0]["recuperato"] is True


def test_la_traccia_porta_i_tag_su_cui_si_filtra(ambiente):
    """Sui tag l'interfaccia di MLflow filtra, sugli attributi no: è così che dopo una
    valutazione si aprono le sole tracce dei casi falliti."""
    from ecoscan.valutazione.esegui import _ModelloAssente
    tracciatore = TracciatoreFinto()
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8, tracciatore=tracciatore)
    val.valuta_caso(agente, caso_dei_giornali(), con_modello=False)

    tag = tracciatore.etichette[0]
    assert tag["caso"] == "Torino · giornale"
    assert tag["insieme"] == "regressioni" and tag["comune"] == "Torino"
    assert tag["diagnosi"] == val.RECUPERATO and tag["recuperato"] == "si"


def test_un_caso_negativo_dichiara_nel_tag_che_deve_tacere(ambiente):
    from ecoscan.valutazione.esegui import _ModelloAssente
    tracciatore = TracciatoreFinto()
    agente = Agente(ambiente.recupero, _ModelloAssente(), k=8, tracciatore=tracciatore)
    val.valuta_caso(agente, caso_assente(), con_modello=False)
    assert "deve astenersi" in tracciatore.etichette[0]["atteso"]


# ------------------------------------------------- le due domande, da leggere in coppia

def caso_ambiguo(**extra) -> Caso:
    """Il cartone della pizza senza dire com'è: la condizione decide fra carta e organico,
    e l'agente non può vederla."""
    return Caso(comune="Napoli", oggetto="scatola della pizza",
                destinazioni_attese=["Carta e Cartoncino", "Organico"],
                origine="chiarimenti", chiarimento_atteso=True, **extra)


def caso_dichiarato(**extra) -> Caso:
    """Lo stesso oggetto, ma l'utente ha già detto com'è: chiedere sarebbe far perdere
    tempo a chi ha già risposto."""
    return Caso(comune="Napoli", oggetto="scatola della pizza", testo_utente="è unto",
                destinazioni_attese=["Organico"], origine="chiarimenti",
                chiarimento_atteso=False, **extra)


def test_la_domanda_si_misura_nelle_due_direzioni():
    """`domanda_dovuta` da sola si massimizza chiedendo sempre, che è il difetto opposto:
    è la stessa ragione per cui le astensioni si leggono in coppia."""
    chiesto = val.Esito(caso=caso_ambiguo(), recuperato=True, posizione=1,
                        destinazioni=["Carta e Cartoncino", "Organico"],
                        chiarimento="L'oggetto è: pulito oppure unto?", opzioni=["pulito", "unto"])
    zitto = val.Esito(caso=caso_ambiguo(), recuperato=True, posizione=1,
                      destinazioni=["Carta e Cartoncino", "Organico"])
    assert chiesto.chiarimento_corretto is True and zitto.chiarimento_corretto is False
    misure = val.misure([chiesto, zitto])
    assert misure["domanda_dovuta"] == 50.0
    assert misure["domanda_inutile"] is None, "nessun caso verifica l'altra direzione"


def test_chiedere_quando_la_condizione_e_gia_dichiarata_e_un_difetto():
    inutile = val.Esito(caso=caso_dichiarato(), recuperato=True, posizione=1,
                        destinazioni=["Carta e Cartoncino", "Organico"],
                        chiarimento="L'oggetto è: pulito oppure unto?")
    assert inutile.chiarimento_corretto is False
    assert inutile.diagnosi == val.DOMANDA_INUTILE
    assert val.misure([inutile])["domanda_inutile"] == 100.0


def test_non_chiedere_quando_serviva_ha_la_sua_diagnosi():
    """Le due diagnosi sono separate perché si riparano in punti diversi: una domanda
    mancata è una condizione che il codice non ha visto, una di troppo è un testo
    dell'utente che non è stato letto."""
    mancata = val.Esito(caso=caso_ambiguo(), recuperato=True, posizione=1,
                        destinazioni=["Carta e Cartoncino", "Organico"])
    assert mancata.diagnosi == val.MANCATA_DOMANDA


def test_senza_modello_la_domanda_non_si_misura():
    """La domanda nasce durante la scelta: senza modello non viene nemmeno formulata, e
    contarla come mancata direbbe il falso su qualcosa che non è stato misurato."""
    esito = val.Esito(caso=caso_ambiguo(), recuperato=True, posizione=1,
                      valutata_la_scelta=False)
    assert esito.chiarimento_corretto is None
    assert val.misure([esito])["domanda_dovuta"] is None


def test_i_casi_che_non_verificano_la_domanda_non_entrano_nel_conto():
    """Un caso del campione può ricevere una domanda senza che sia un difetto: se non
    dichiara un'attesa, non deve spostare il numero."""
    normale = val.Esito(caso=caso_dei_giornali(), recuperato=True, posizione=1,
                        destinazioni=["carta_e_cartone"], chiarimento="una domanda")
    assert normale.chiarimento_corretto is None
    misure = val.misure([normale])
    assert misure["domanda_dovuta"] is None and misure["domanda_inutile"] is None


# ---------------------------------------------------- il dataset dei chiarimenti sul disco

def test_i_chiarimenti_vengono_a_coppie():
    """Ogni oggetto compare due volte: una senza la condizione e una con. Un insieme fatto
    di soli casi ambigui si supererebbe chiedendo sempre."""
    from ecoscan.valutazione.casi import tutti
    casi = [c for c in tutti() if c.origine == "chiarimenti"]
    assert len(casi) >= 20
    per_voce: dict[str, set] = {}
    for caso in casi:
        per_voce.setdefault(caso.voce_fonte, set()).add(caso.chiarimento_atteso)
    spaiati = [voce for voce, attese in per_voce.items() if attese != {True, False}]
    assert not spaiati, f"voci con una direzione sola: {spaiati}"


def test_i_casi_ambigui_non_dichiarano_la_condizione():
    """Se il testo dell'utente contenesse la condizione, il caso non misurerebbe la domanda:
    misurerebbe che il codice sa leggere."""
    from ecoscan.valutazione.casi import tutti
    con_testo = [c for c in tutti()
                 if c.origine == "chiarimenti" and c.chiarimento_atteso and c.testo_utente]
    assert not con_testo, f"casi ambigui che dichiarano già la condizione: {con_testo}"


def test_una_risposta_provvisoria_non_si_misura_come_definitiva():
    """L'agente ha detto "probabilmente X, ma dimmi Y": pretendere che X sia già la risposta
    completa significherebbe punirlo per aver fatto la cosa giusta."""
    provvisoria = val.Esito(caso=caso_ambiguo(), recuperato=True, posizione=1,
                            destinazioni=["Carta e Cartoncino"],   # una sola delle due
                            chiarimento="L'oggetto è: pulito oppure unto?")
    assert provvisoria.provvisoria is True
    assert provvisoria.diagnosi == val.CORRETTO_CON_DOMANDA
    misure = val.misure([provvisoria])
    assert misure["contenitore_corretto"] is None, "non è una risposta definitiva"
    assert misure["domanda_dovuta"] == 100.0


def test_una_risposta_senza_domanda_si_misura_eccome():
    """Il rovescio: se non ha chiesto, la destinazione che ha dato è la sua risposta finale
    e si giudica come tale."""
    definitiva = val.Esito(caso=caso_dichiarato(), recuperato=True, posizione=1,
                           destinazioni=["Organico"])
    assert definitiva.provvisoria is False
    assert val.misure([definitiva])["contenitore_corretto"] == 100.0


def test_l_esito_dice_quale_voce_ha_risposto():
    """Senza, un caso che si aspettava una voce e ne ha trovata un'altra sembra un difetto
    della domanda invece che della scelta: è successo il 25/09 con "medicinali", dove ha
    risposto la voce «Medicinale» (una variante sola, niente da chiedere) invece di
    «Farmaci»."""
    caso = Caso(comune="Napoli", oggetto="medicinali che ho in casa",
                voce_fonte="Farmaci", destinazioni_attese=["Contenitore Farmaco"],
                origine="chiarimenti", chiarimento_atteso=True)
    esito = val.Esito(caso=caso, recuperato=True, posizione=1,
                      destinazioni=["Contenitore Farmaco"], scelto="Medicinale")
    assert esito.scelto == "Medicinale"
    assert val.come_json([esito])["esiti"][caso.id]["scelto"] == "Medicinale"
