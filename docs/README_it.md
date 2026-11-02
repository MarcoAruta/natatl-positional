# NatATL memoryless: positional guess-and-check and POS2NAT

Progetto autonomo Python per la track di Marco Aruta e GianMarco Parretti.
Non richiede VITAMIN, server, interfacce web o dipendenze Python esterne.
Richiede **Python 3.10 o successivo**. Sviluppato e verificato con Python 3.12.

La pipeline principale cerca strategie posizionali, le traduce in liste naturali,
controlla ammissibilità e costo `<= k`, costruisce il modello prunato e verifica
l'obiettivo universale CTL. Se trova una soluzione restituisce anche la strategia
vincente, il costo e le azioni selezionate in ogni stato originale.

## Avvio immediato

Estrai lo ZIP e apri un terminale nella cartella che contiene questo README.
Puoi aprire direttamente la cartella in PyCharm e scegliere l'interprete Python.
Non occorre eseguire `pip install`.

```bash
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --output witness.json
```

Il risultato è `true`, con la strategia `p -> B; T -> A`, di costo **2**.
Per ricontrollare il testimone salvato:

```bash
python -m natatl_positional verify examples/switch.txt --formula "<{1},2>F goal" --witness witness.json
```

Il comando `check` stampa JSON e può salvarlo con `--output`. I comandi eseguiti
correttamente terminano con codice 0, anche per gli esiti logici `false` e
`unknown`. Gli errori di input terminano con codice 2 e un messaggio JSON su stderr.

## Dove si trova l'algoritmo di GianMarco

**`natatl_positional/pos2nat.py`** contiene `pos2nat` e la marcatura in avanti.
**`natatl_positional/strategy.py`** contiene `left_write`, che aggiunge la regola
in testa, non in coda. Nessuna semplificazione booleana viene applicata al
POS2NAT letterale. Il costo comprende la formula espansa anche quando il codice
la conserva come DAG per risparmiare memoria.

Per eseguire soltanto la conversione di una strategia posizionale nota e vedere
ogni aggiornamento, inclusi ramo, costo della regola e costo totale:

```bash
python -m natatl_positional convert examples/switch.txt --coalition 1 --policy examples/switch_policy.json --complete --output conversion.json
```

Senza `--complete` vengono elaborati soltanto gli stati di `G'` raggiungibili
dall'iniziale: è il dominio della costruzione degli appunti. Con `--complete`
si aggiungono successivamente gli stati originali non raggiunti, in modo da
ottenere una strategia sul modello intero. La traccia identifica queste aggiunte.

## Tre modalità di conversione

| `--compiler` | Comportamento | Esito negativo |
|---|---|---|
| `pos2nat` | Solo la costruzione letterale degli appunti, senza minimizzazione | `unknown` se uno scarto per costo/ammissibilità lascia aperta un'altra implementazione |
| `exact` | Implementazione minima entro il budget, mediante guardie e liste ordinate | `false` dopo una ricerca completa; `unknown` se interviene un limite |
| `hybrid` (default) | Prima POS2NAT; se la rappresentazione non rientra nel budget o non è ammissibile, usa il compilatore esatto | Come `exact` |

Il compilatore esatto è l'implementazione dell'**Approach (1)** discusso negli
appunti. Non è una proprietà attribuita al POS2NAT originale. Minimizza la
**lista ordinata complessiva**, tenendo conto della priorità, delle valutazioni
presenti nel modello e dell'ammissibilità: non minimizza separatamente una
formula per azione sperando di ottenere una lista minima.

```bash
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --compiler pos2nat
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --compiler exact --trace
```

Nel primo comando il risultato è `unknown`: la rappresentazione grezza costa
63, mentre esiste la strategia di costo 2 mostrata sopra. Scartare quella
rappresentazione e rispondere `false` sarebbe scorretto.

## Input e semantica

- File CGS testuali VITAMIN: `Transition`, `Name_State`, `Initial_State`,
  `Atomic_propositions`, `Labelling`, `Number_of_agents`. Sono accettati anche
  `Agent_labels` e `Unknown_Transition_by` come metadati; la relazione usata è
  esclusivamente quella esplicita sotto `Transition`.
- JSON sparso: lo schema è quello prodotto da `Game.to_dict()` e dai modelli
  salvati da `experiments/run_benchmarks.py`.
- CGS deterministiche e totali, con tutte le combinazioni delle azioni locali.
  Tabelle mancanti, wildcard, etichette non binarie e nondeterminismo sono errori.
- Azioni nominali: `MOVE_FORWARD|BLOCK_PATH`. Per due agenti `AB` significa
  `(A,B)`; per un agente `MOVE_FORWARD` è una sola azione. `I` e `IDLE` coincidono.
- Coalizioni indicizzate da **1**. Il budget è condiviso e somma i costi delle
  strategie individuali. La regola finale `T` costa uno per agente.
- Guardie proposizionali `!`, `&&`, `||`, parentesi e costanti `T`, `true`,
  `false`. Non sono implementati operatori epistemici o strategie con memoria.
- `V(q)` contiene letterali positivi **e negativi** per tutti gli atomi.
  Stati con la stessa etichetta sono indistinguibili dalle guardie: la ricerca
  enumera direttamente le politiche uniformi sulle classi di etichette.
- `--appropriateness first-match` (default) segue la variante operazionale della
  nota 3, §4.1 del paper allegato, e il default del codice aggiornato.
  `--appropriateness global` applica il requisito più forte del testo principale.
  Sono due semantiche distinte a budget fissato.
- L'ammissibilità è controllata sul **modello originale intero**, inclusi gli
  stati non raggiungibili dall'iniziale.
- Il pruning mantiene esattamente le mosse concordi con la coalizione e **tutte**
  le mosse avversarie. `IDLE` non viene aggiunta come alternativa extra.

Sintassi delle formule:

```text
<{1},4>F goal
<{1,2},5>G safe
<{1},3>X p
<{1},4>(safe U goal)
<{1},4>(safe W goal)
!<{1},2>F goal
(<{1},1>X p) && (<{1},1>X q)
<{1},3>F (<{2},2>G safe)
```

Gli operandi annidati vengono valutati nel gioco originale con coalizione e
budget propri. Un esito `unknown` non viene trasformato in `false` dalla
composizione o in `true` dalla negazione. Non è una traduzione generale LTL→CTL:
sono implementati gli operatori universali `AX`, `AF`, `AG`, `A[U]`, `A[W]` di
NatATL dopo la scelta di ciascuna strategia.

## Ordine delle operazioni e controesempi

Il codice verifica costo e ammissibilità **prima di costruire il modello
prunato destinato a CTL**. La marcatura di POS2NAT richiede comunque di consultare
le transizioni compatibili con la politica: questo accesso è implicito e non
materializza il modello prunato. `--compiler exact` non richiede quella marcatura.

Sono attivi vincoli appresi da controesempi finiti o a lasso. Ogni vincolo
impedisce di riproporre una combinazione di scelte che conserva il controesempio
per la stessa query e lo stesso stato iniziale. Per disattivarli usa `--no-cegar`.
Questa è una realizzazione della proposta di raffinamento tramite controesempi;
non viene presentata come un framework generale di astrazione di CGS.

`--trace` mostra la sequenza `guess`, `pos2nat`, `admissible`, `pruning`, `ctl`,
o le ragioni di scarto. La traccia conserva al massimo 2.000 eventi; vengono
esportati al massimo 50 controesempi. Questi limiti di diagnostica non limitano
la ricerca. Il sistema conserva al massimo 10.000 vincoli, poi continua senza
apprenderne altri.

## Limiti espliciti e risultati

```bash
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --max-candidates 1
```

Un limite di tempo, candidati, maschere delle guardie o stati della programmazione
dinamica produce `unknown` negli stati non decisi. Di default le due strutture
di minimizzazione hanno un tetto di 100.000 elementi ciascuna; non c'è un limite
di candidati o di tempo. I limiti di tempo sono controllati ai checkpoint del
calcolo, non da un processo esterno che interrompe ogni singola istruzione.

`satisfied` è `true`, `false` o `null`. `winning_strategy` compare come oggetto
quando è positiva una modalità strategica in radice; contiene guardie, azioni,
costo e una serializzazione DAG ricaricabile. Per una formula booleana che
combina modalità indipendenti non si inventa un'unica strategia condivisa.

Di default si decide lo stato iniziale. `--all-states` richiede l'intero insieme
degli stati soddisfacenti; `query_complete` e `state_set_complete` distinguono
esplicitamente i due casi. Gli stati definitivamente veri, falsi e ancora
indecisi sono sempre separati nei risultati.

## Test e confronto con l'approccio classico

```bash
python -m unittest discover -s tests -v
python experiments/run_benchmarks.py --repeats 3
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --engine classic
```

La baseline usa la generazione lazy del codice allegato, copiata isolatamente in
`_classic_generation.py`, e gli stessi controlli di ammissibilità/pruning/CTL.
Le misure separano quindi gli spazi di ricerca; non sono un confronto con il
tempo di avvio dell'intera interfaccia VITAMIN.

Gli esiti eseguiti sono in `experiments/results/`, insieme a CSV, ambiente,
modelli e testimone di esempio. La suite comprende un oracolo indipendente basato
su enumerazione sintattica e rilevazione di cicli, oltre ai confronti fra motori.
I benchmark inclusi sono piccoli esempi di funzionamento, non evidenza di una
superiorità generale o della soglia del 70% ipotizzata negli appunti.

## API Python e file principali

```python
from natatl_positional import check, Game, Limits

result = check("examples/switch.txt", "<{1},2>F goal", compiler="hybrid")
print(result["satisfied"], result["winning_strategy"])

# Per integrare un modello VITAMIN già in memoria, senza importare VITAMIN:
# game = Game(states, propositions, number_of_agents, initial_state,
#             labels, transitions)
# result = check(game, formula, all_states=True)
```

| File | Compito |
|---|---|
| `pos2nat.py`, `strategy.py` | Algoritmi di GianMarco, liste e costo |
| `minimize.py` | Guardie minime sulle etichette osservate e liste minime entro il budget |
| `search.py` | Enumerazione posizionale, controlli prima di pruning, baseline |
| `temporal.py`, `refinement.py` | CTL universale, controesempi e vincoli |
| `checker.py`, `formulas.py` | NatATL composizionale e risultati anche incompleti |
| `model.py`, `cli.py` | Formati VITAMIN/JSON e comandi |
| `docs/IMPLEMENTATION.md` | Corrispondenza puntuale con gli appunti e scelte implementative |

Per installare il comando opzionale: `python -m pip install -e . --no-build-isolation`.
L'esecuzione tramite `python -m natatl_positional` non richiede installazione.

Origine e licenza del codice allegato sono conservate in `LICENSE` e
`docs/PROVENANCE.md`.
