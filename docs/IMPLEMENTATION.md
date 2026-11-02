# Implementazione e corrispondenza con gli appunti

Questo documento descrive il codice consegnato. Non aggiunge nuovi risultati
alle congetture della track e non attribuisce al POS2NAT originale una proprietà
di minimizzazione che negli appunti è esplicitamente esclusa.

## 1. Algoritmo originale

| Passaggio degli appunti | Implementazione |
|---|---|
| `LEFT_WRITE(nu,f,a) = [(f,a)] + nu` | `strategy.left_write`: antepone una regola e conserva la lista precedente |
| `s_nu = [(true,idle)]`, `psi = false` | `pos2nat.pos2nat`: inizializza la lista e la formula di copertura |
| Marcatura 0..n per prima raggiungibilità | `reachability_layers`: BFS sulle transizioni compatibili con la politica |
| Stati nuovi `G'_i / G'_(i-1)` | Ogni stato appare una volta nel livello BFS in cui viene scoperto |
| Test `V(q) && !psi = false` | Test esatto di copertura della valutazione completa di `q`, spiegato sotto |
| Caso coperto: anteporre `(V(q), nu(q))` | Ramo `overwrite`; `psi` non viene cambiata |
| Caso non coperto: anteporre `(V(q) && !psi, nu(q))` | Ramo `uncovered`; viene conservata la guardia completa, senza semplificarla |
| Aggiornare `psi = psi || (V(q) && !psi)` | Il nodo `f` usa la precedente `psi`, poi si costruisce il nuovo nodo OR |
| Restituire strategia e, opzionalmente, costo | Oggetto `Conversion`, con strategia, costo tramite `strategy.cost`, livelli e traccia |

Le formule sono DAG immutabili: se una sottostruttura ricorre due volte può
essere condivisa in memoria. Il costo, però, è sempre quello dell'albero
sintattico **espanso**: `|!f|=1+|f|`, `|f && g|=1+|f|+|g|`, analogamente per OR.
Non si conteggiano una sola volta nodi condivisi né si omettono operatori o la
regola finale. Nessun `simplify` viene applicato al percorso letterale.

Il comando `convert` conserva la traccia del POS2NAT per ogni agente. In
`search` la traccia è più compatta e si abilita con `--trace`.

### Convenzione su V(q) e test SAT

Per ogni atomo dichiarato si mette il letterale positivo se è vero in `q`,
altrimenti quello negativo. Dunque `V(q)` è vera esattamente sulla valutazione
`L(q)` e non anche sulle sue sovraetichette. Per zero atomi si usa `T`.

Per queste particolari formule, l'invariante della copertura è che `psi` denota
l'unione delle valutazioni complete già elaborate. Perciò
`SAT(V(q) && !psi)` equivale all'appartenenza di `L(q)` all'insieme delle
valutazioni ancora nuove. Il codice usa questo controllo esatto invece di
invocare un solver SAT, ma continua a costruire la formula sintattica richiesta.
Questa scelta **non** risolve SAT per guardie arbitrarie e non dimostra la
congettura di complessità generale degli appunti.

Una politica che assegna azioni diverse alla stessa valutazione non è
implementabile da una lista proposizionale deterministica di questo linguaggio.
Il codice la rifiuta, anziché lasciare che una regola sovrascriva silenziosamente
l'azione di uno stato precedente. Non è implementata l'interpretazione
alternativa di `V(q)` come sola congiunzione degli atomi positivi: quella
interpretazione introdurrebbe sovrapposizioni e nuovi obblighi di correttezza.

## 2. Adattamenti necessari rispetto al codice NatATL allegato

1. Il POS2NAT degli appunti lavora su `G'` raggiungibile dall'iniziale. Il codice
   aggiornato richiede una strategia ammissibile nell'intero gioco originale.
   Il solver completa quindi la costruzione sui restanti stati, dopo i livelli
   raggiungibili. `convert` lascia scegliere esplicitamente `--complete`.
2. Se `IDLE` è nell'alfabeto dell'agente, resta l'azione iniziale di default.
   Se non è presente, si sceglie un'azione esistente, in ordine deterministico.
   Il paper e il codice aggiornato consentono una qualsiasi azione nella regola
   finale. La funzione Python permette anche `default_action=...` esplicito.
3. Il default è l'ammissibilità `first-match` del backend aggiornato. Si può
   scegliere `global`, che controlla ogni regola anche dove è oscurata da quelle
   precedenti. Le guardie e il costo restano identici; non si confondono i due
   problemi a budget fissato.
4. Il vincolo è `<= k`, coerente con la richiesta e il codice attuale, anche nei
   punti in cui le email usavano informalmente `< k`.

La marcatura consulta `G` filtrando le mosse compatibili con la politica, prima
del controllo del costo. È un accesso implicito a `G'`, inevitabile per la BFS
richiesta dal POS2NAT. Il **modello prunato usato da CTL** è materializzato
soltanto dopo che la strategia naturale ha superato costo e ammissibilità.
Con `--compiler exact` si evita del tutto la marcatura.

## 3. Nuovo spazio di ricerca

`policy_space` raggruppa gli stati per etichetta completa. Per ogni classe e
agente della coalizione considera l'intersezione delle azioni abilitate negli
stati della classe. Il prodotto di queste scelte enumera le politiche che una
strategia naturale del linguaggio supportato può implementare.

Se gli stati `s` e `t` hanno la stessa etichetta, ogni guardia proposizionale ha
lo stesso valore in entrambi e la prima regola vera è la stessa. Per questo la
uniformità sulle etichette è un vincolo necessario, anche se il gioco originale
è a informazione perfetta. Non si aggiunge una relazione epistemica al modello.

Con `c` classi, il numero di candidati è il prodotto delle dimensioni delle
intersezioni di azioni per classe e agente. Il valore è esportato nelle
statistiche, insieme al prodotto sulle singole coppie stato/agente. Non si usa
la stima `|S| * |A|^k` come numero generale di strategie posizionali.

## 4. Implementazione dell'Approach (1): costo esatto entro k

Il compilatore `exact` è un componente aggiunto per rendere utilizzabile la
riduzione anche per risposte negative. È distinto dal POS2NAT letterale.

### Guardie

Ogni formula è associata alla maschera dei valori di verità sulle **etichette
presenti nel modello**, non su campioni di esecuzioni. La tabella viene costruita
per costo crescente, da atomi e costanti usando NOT, AND e OR. Per ciascuna
maschera si conserva la prima formula trovata al costo minimo. Si considerano
solo formule potenzialmente utilizzabili entro il budget richiesto.

Le valutazioni non presenti nella CGS sono don't care: non si sta richiedendo
un'implementazione della politica su stati inesistenti. La sostituzione di una
guardia con una più economica avente la stessa maschera preserva sia il
comportamento, sia i controlli `global` sulle guardie nel modello originale.

### Liste ordinate

Per una politica individuale fissata, lo stato della programmazione dinamica è
l'insieme delle classi non ancora coperte dalle regole precedenti, insieme al
budget residuo. Una guardia può essere anteposta al resto della lista se le
classi appena coperte richiedono tutte la stessa azione. In modalità `global`
l'azione deve inoltre essere abilitata su tutta la maschera della guardia.
La ricorsione termina con una regola **sintatticamente `T`**, che costa uno.

Ogni regola considerata copre almeno una classe nuova: le regole senza effetto
possono essere eliminate senza aumentare il costo. Si mantiene il risultato di
costo minimo. Per una coalizione si sommano i minimi individuali della politica
fissata: il budget non viene applicato separatamente a ogni agente.

Questo calcolo può essere oneroso: ci possono essere esponenzialmente molte
maschere e insiemi di classi residue. I tetti di risorse producono `unknown`,
non una prova di assenza di implementazioni. Non viene attribuita una nuova
classificazione della complessità alle congetture del progetto.

## 5. Raffinamento tramite controesempi

`temporal.counterexample` produce un prefisso finito per `AX`, `AG` e le
violazioni finite di `AU`/`AW`, oppure un lasso per le violazioni infinite di
`AF`/`AU`. Il lasso include l'arco di chiusura del ciclo.

Da ogni arco del controesempio si memorizza la scelta della coalizione nella
classe del suo stato sorgente. Una nuova politica che conserva queste scelte
conserva il cammino: l'avversario può ancora scegliere le stesse mosse che ne
realizzano gli archi. Quella politica non può quindi risolvere la stessa query
da quello stato. Un endpoint finito che viola già la formula non richiede un
vincolo sull'azione successiva.

I vincoli sono locali alla modalità, ai suoi operandi e allo stato da decidere.
Un fallimento da `s` non elimina una strategia che potrebbe vincere da `t`.
I vincoli non vengono condivisi tra formule annidate o esecuzioni diverse.

## 6. Risposte complete e incomplete

Il backend restituisce due insiemi: stati sicuramente soddisfacenti e stati
ancora potenzialmente soddisfacenti. Le due componenti coincidono quando il
problema è deciso. Negazione e connettivi propagano questi intervalli;
gli operatori strategici usano la monotonicità rispetto agli operandi.

In modalità `pos2nat`, una rappresentazione troppo costosa lascia potenzialmente
valida la politica che l'ha generata. In modalità `exact`/`hybrid`, uno scarto
per costo è definitivo soltanto dopo che il compilatore ha completato il suo
calcolo entro il budget. Per gli input supportati e a ricerca terminata senza
limiti irrisolti, l'enumerazione copre le politiche implementabili del linguaggio
e consente una risposta negativa completa. La suite verifica questa proprietà
su piccoli spazi esauribili; non costituisce una prova meccanizzata generale.

Le query annidate sono valutate nel modello originale e non riusano il
testimone di un'altra quantificazione esistenziale. Un testimone in radice viene
ricompilato, confrontato con la politica posizionale e controllato nel grafo
prunato prima di essere restituito.

## 7. Cosa resta aperto per la ricerca

- Le congetture originali con guardie/etichette interpretate in modo diverso
  dalle valutazioni complete non vengono dichiarate risolte dal codice.
- Non è stata implementata una caratterizzazione greedy delle strategie
  monotone che ne garantisca il costo minimo durante il fixpoint.
- Il costo minimo non viene ottenuto gratuitamente dal POS2NAT: nella modalità
  esatta si paga il calcolo esplicito descritto sopra.
- Il vantaggio pratico rispetto alla generazione classica deve essere valutato
  su benchmark della track. I risultati inclusi sono soltanto un primo
  confronto riproducibile e comprendono anche casi in cui la baseline è migliore.
