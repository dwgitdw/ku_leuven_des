# USD Composer - guide de reprise complet

Ce systeme represente une ligne de production avec palettes/carriers, un poste Human, des robots, des lifts, des files d'attente et des replays offline ou live dans USD Composer.

## Convention de chemin

Dans ce README, `PROJECT_ROOT` designe le dossier racine du projet, c'est-a-dire le dossier qui contient `README.md`, `3d/` et `scripts/`.

La personne qui installe le projet peut choisir librement ou le mettre, par exemple:

```text
C:\Projects\USD_Composer
D:\Work\ku_leuven_des
E:\Engineering\USD_Composer
```

Regle importante: modifier seulement la valeur de `PROJECT_ROOT` dans les commandes et les snippets Python. Ne pas modifier les chemins internes du projet comme `scripts\DES\...`, `scripts\RealtimeTCP\...` ou `3d\layout\...`, car ils sont relatifs a `PROJECT_ROOT`.

Exemple PowerShell:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

Exemple dans le Script Editor USD Composer:

```python
PROJECT_ROOT = Path(r"C:\Projects\USD_Composer")
```

## Installation depuis GitHub

Pour installer le projet sur une nouvelle machine, faire d'abord ceci:

```powershell
$WORKSPACE_DIR = "C:\Projects"
$PROJECT_DIR_NAME = "USD_Composer"
$PROJECT_ROOT = Join-Path $WORKSPACE_DIR $PROJECT_DIR_NAME

git lfs install
git clone https://github.com/dwgitdw/ku_leuven_des.git $PROJECT_ROOT
cd $PROJECT_ROOT
git lfs pull
```

Remplacer seulement `$WORKSPACE_DIR` pour choisir l'emplacement, et eventuellement `$PROJECT_DIR_NAME` pour choisir le nom du dossier local. Le nom du dossier local peut rester `USD_Composer`, meme si le depot GitHub s'appelle `ku_leuven_des`.

Si un nouveau terminal PowerShell est ouvert plus tard, redefinir simplement:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

en adaptant la valeur au dossier choisi au moment du clone.

Ensuite installer le template NVIDIA dans le dossier du projet:

```powershell
git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git kit-app-template
cd kit-app-template
git lfs pull
cd ..
```

Structure attendue apres installation:

```text
USD_Composer/
  kit-app-template/        template NVIDIA installe localement
  3d/                      scenes USD, assets et layouts 3D du projet
  scripts/                 scenarios, bridges TCP et outils Python
  README.md
  .gitignore
  .gitattributes
```

Cette installation ne change pas l'architecture du projet. `kit-app-template/` reste un dossier externe de reference, ignore par Git. Les fichiers du systeme restent dans `3d/` et `scripts/`.

Le fichier `.gitattributes` ne deplace rien et ne modifie pas les scenes. Il dit seulement a GitHub de stocker les gros fichiers `.usd` et `.stp` avec Git LFS. Pour la personne qui clone le projet, la seule obligation est donc d'avoir Git LFS installe et de lancer `git lfs pull` si les assets ne sont pas recuperes automatiquement.

Verification minimale apres installation:

```powershell
python -c "import simpy; print('simpy OK')"
python -c "from pxr import Usd; print('pxr OK')"
```

Si `pxr` echoue, lancer les scripts avec le Python de USD Composer / Omniverse ou avec un environnement Python OpenUSD compatible.

## Note sur NVIDIA Omniverse Kit App Template

Reference upstream: [NVIDIA-Omniverse/kit-app-template](https://github.com/NVIDIA-Omniverse/kit-app-template)

Ce projet est un projet applicatif USD Composer / Omniverse Kit derive ou inspire de l'ecosysteme Kit App Template. Le dossier local `kit-app-template/`, quand il existe, sert uniquement de reference ou de copie de template et il est ignore par Git dans ce depot. Pour utiliser ce projet, il faut surtout comprendre les dossiers `3d/` et `scripts/`, car ce sont eux qui contiennent les scenes, les layouts, les bridges TCP et les scenarios metier.

En pratique:

- `kit-app-template` = template NVIDIA upstream pour creer des applications Omniverse Kit/OpenUSD.
- `USD_Composer` = projet de ligne de production documente ici.
- Pour lancer ou modifier la simulation, ne pas repartir du template: suivre les commandes de ce README.
- Pour recreer une application Kit propre depuis zero, consulter le README upstream NVIDIA et refaire l'integration ensuite.

## Installer Kit App Template dans ce dossier

Pour une reprise complete du projet, garder ou installer le template NVIDIA dans le dossier racine du projet:

```text
USD_Composer/
  kit-app-template/
  3d/
  scripts/
  README.md
```

Le template est volontairement ignore par `.gitignore`, car c'est une dependance/reference externe. Il ne faut donc pas s'inquieter si `git status` ne le montre pas.

Prerequis Kit App Template selon NVIDIA:

- Windows 10/11 ou Linux Ubuntu 22.04+.
- GPU NVIDIA RTX recommande.
- Driver NVIDIA compatible.
- Acces Internet pour telecharger le SDK Kit, les extensions et les outils.
- Git et Git LFS.
- Visual Studio + Windows SDK uniquement si on compile du C++ sous Windows.

Installation Windows recommandee dans ce projet:

```powershell
cd $PROJECT_ROOT
git lfs install
git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git kit-app-template
cd kit-app-template
git lfs pull
cd ..
```

Si `kit-app-template/` existe deja, ne pas recloner par-dessus. Entrer simplement dedans:

```powershell
cd $PROJECT_ROOT
cd kit-app-template
```

Procedure NVIDIA pour creer une application depuis le template:

```powershell
.\repo.bat template new
.\repo.bat build
.\repo.bat launch
```

Pendant `template new`, choisir:

| Question du wizard | Choix conseille |
| --- | --- |
| Type a creer | `Application` |
| Template | `USD Composer` si l'objectif est proche de ce projet, sinon `Kit Base Editor` pour une base minimale |
| Nom du fichier `.kit` | nom court, lowercase, sans espace |
| Display name | nom lisible de l'application |
| Version | par exemple `0.1.0` |
| Application layers | `No` pour un test local simple |

Important: les scripts de ce depot ne dependent pas directement d'une app generee par le wizard. Le template sert a installer/recreer l'environnement Kit et a comprendre la structure Omniverse. Pour lancer les scenarios de production, rester dans `USD_Composer/` et suivre les sections DES, RealtimeTCP, Simulogs ou RealTimeTCPlogs.

## Objectif du projet

Ce depot visualise une ligne de production dans USD Composer. Il contient quatre systemes actifs:

| Systeme | Mode | Entree | Sortie | Usage principal |
| --- | --- | --- | --- | --- |
| `DES` | Offline | Layout JSON + scene USD source | USD anime exporte | Simuler la logique complete puis ouvrir un replay |
| `RealtimeTCP` | Live | DES interne + layout JSON | Messages TCP vers USD Composer | Voir la simulation bouger en temps reel |
| `Simulogs` | Offline | CSV de logs | USD anime exporte | Rejouer des logs existants dans une scene USD |
| `RealTimeTCPlogs` | Live | CSV suivi en continu | Messages TCP vers USD Composer | Visualiser des logs qui arrivent pendant l'execution |

Le principe important: les positions ne sont pas codees en dur dans les scripts. Les layouts JSON utilisent des references `marker:...`; `scripts/marker_layout.py` lit les positions dans les fichiers USD et remplace les markers par des coordonnees au lancement.

## Demarrage rapide

Definir `PROJECT_ROOT` une fois dans le terminal:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

Verifier l'environnement Python:

```powershell
python -c "import simpy; print('simpy OK')"
python -c "from pxr import Usd; print('pxr OK')"
```

Si `pxr` echoue, lancer les scripts depuis un Python Omniverse/USD Composer compatible OpenUSD, ou installer un environnement Python qui contient les bindings USD.

Ordre de lancement a retenir:

1. Installer ou verifier `kit-app-template/` dans le dossier du projet si la machine repart de zero.
2. Choisir un scenario: `DES`, `RealtimeTCP`, `Simulogs` ou `RealTimeTCPlogs`.
3. Verifier le fichier de configuration JSON du scenario.
4. Verifier que la scene indiquee par `marker_stage` contient les markers attendus.
5. Pour un scenario offline, lancer les scripts Python puis ouvrir l'USD genere.
6. Pour un scenario live, ouvrir d'abord la scene dans USD Composer, lancer le bridge TCP dans Composer, puis lancer le producteur Python dans PowerShell.

Choix rapide:

| Besoin | Scenario |
| --- | --- |
| Tester la logique de production sans temps reel | `DES` |
| Voir la logique DES bouger en direct dans Composer | `RealtimeTCP` |
| Transformer un CSV existant en replay USD | `Simulogs` |
| Suivre un CSV qui se remplit pendant l'execution | `RealTimeTCPlogs` |

## Prerequis

- Windows avec PowerShell pour les commandes ci-dessous.
- NVIDIA USD Composer / Omniverse Kit pour ouvrir les scenes et executer les bridges live.
- Python avec `simpy`.
- Python avec `pxr` / OpenUSD pour tous les scripts qui lisent les markers ou ecrivent des scenes USD.
- Ports TCP libres:
  - `127.0.0.1:5050` pour `RealtimeTCP`.
  - `127.0.0.1:5051` pour `RealTimeTCPlogs`.

## Architecture du depot

```text
USD_Composer/
  README.md
  .gitignore

  3d/
    layout/
      model.usd                         scene source DES / RealtimeTCP
      modelbuffer.usd                   scene source Simulogs
      carrier.usd                       asset palette/carrier
    RealtimeTCP/
      model.usd                         scene live RealtimeTCP a ouvrir dans Composer
    RealTimeTCPlogs/
      modelbuffer.usd                   scene live logs a ouvrir dans Composer
    DES/
      model_build.usd                   genere par DES build
      model_replay.usd                  genere par DES simulation
    Simulogs/
      modelbuffer_build.usd             genere par Simulogs build
      modelbuffer_replay.usd            genere par Simulogs replay

  scripts/
    marker_layout.py                    resolution des marker:...
    DES/                                simulation a evenements discrets offline
    RealtimeTCP/                        simulation DES live + bridge TCP Composer
    Simulogs/                           build/replay offline depuis CSV
    RealTimeTCPlogs/                    lecture CSV live + bridge TCP Composer
```

Les fichiers suivants sont generes localement ou temporaires: `.venv/`, `__pycache__/`, `*.pyc`, `*.ndjson`, exports USD de build/replay, logs, caches. Ils sont ignores par `.gitignore`.

## Flux des quatre scenarios

```text
DES offline
  scripts/DES/production_layout.json
  + 3d/layout/model.usd
  + 3d/layout/carrier.usd
  -> 3d/DES/model_build.usd
  -> 3d/DES/model_replay.usd

RealtimeTCP live
  scripts/RealtimeTCP/production_layout_realtime.json
  + 3d/RealtimeTCP/model.usd ouvert dans Composer
  + bridge Composer sur 127.0.0.1:5050
  -> palettes animees en live dans USD Composer

Simulogs offline
  scripts/Simulogs/CSV/logs.csv
  + scripts/Simulogs/production_layout_simulogs.json
  + 3d/layout/modelbuffer.usd
  -> 3d/Simulogs/modelbuffer_build.usd
  -> 3d/Simulogs/modelbuffer_replay.usd

RealTimeTCPlogs live
  scripts/RealTimeTCPlogs/CSV/logs.csv
  + scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
  + 3d/RealTimeTCPlogs/modelbuffer.usd ouvert dans Composer
  + bridge Composer sur 127.0.0.1:5051
  -> carriers animes en live dans USD Composer
```

## Markers et layouts

Un marker est un prim `Xform` dans une scene USD. Les scripts cherchent un prim nomme `Markers`, avec ces racines supportees:

```text
/World/Markers
/model/Markers
/Markers
```

Le script accepte aussi un autre prim nomme `Markers` trouve en parcourant le stage.

Dans les JSON, une position se reference comme ceci:

```json
"entry": "marker:human"
```

Le champ `marker_stage` indique dans quel fichier USD lire les markers:

```json
"marker_stage": "3d/layout/model.usd"
```

Pour deplacer un poste, un buffer ou une trajectoire:

1. Ouvrir le fichier indique par `marker_stage` dans USD Composer.
2. Deplacer ou creer le marker sous `Markers`.
3. Sauvegarder la scene USD.
4. Relancer le script concerne.

## Markers DES / RealtimeTCP

Scene source:

```text
3d/layout/model.usd
```

Markers attendus:

```text
human
start_human_queue
end_human_queue
human_to_queue_p1
human_to_queue_p2
start_robot_queue
end_robot_queue
entry_exit_robot1
processing_robot1
entry_exit_robot2
processing_robot2
robot_return_p1
robot_return_p2
```

Logique metier:

```text
Human -> Lift_ToQueue -> Robot queue -> Robot_1/Robot_2 -> Lift_Return -> Human
```

Regles actuelles:

- Human a une file d'attente.
- Si Human est libre et que la file Human est vide, une palette entre directement.
- La file robot est commune a `Robot_1` et `Robot_2`.
- Si un robot est libre et que la file robot est vide, la palette va directement au robot.
- Priorite stricte: `Robot_1`, puis `Robot_2`.
- Les palettes passent par `entry_exit_robot*` avant `processing_robot*`.
- Les lifts `Lift_ToQueue` et `Lift_Return` durent chacun `4.0` secondes et ont une capacite logique de `1`.

## Markers Simulogs / RealTimeTCPlogs

Scenes sources:

```text
3d/layout/modelbuffer.usd                  pour Simulogs offline
3d/RealTimeTCPlogs/modelbuffer.usd         pour RealTimeTCPlogs live
```

IDs ressources dans les CSV:

```text
1 = Human
2 = Robot_1
3 = Robot_2
4 = Robot_3
5 = Visual_System
6 = Lift_ToQueue_End
7 = Lift_Return_End
```

Markers principaux:

```text
entry_exit_human
human_processing
human_to_lift1_p1
human_to_lift1_p2
lift1
lift2
robot_to_lift2_p1
visual_system
entry_exit_robot1
processing_robot1
entry_exit_robot2
processing_robot2
entry_exit_robot3
processing_robot3
humanbuffer_entry
humanbuffer_p1
humanbuffer_p2
robot1buffer_entry
robot1buffer_p1
robot1buffer_p2
robot2buffer_entry
robot2buffer_p1
robot2buffer_p2
robot3buffer_entry
robot3buffer_p1
robot3buffer_p2
```

## Scenario 1 - DES offline

Fichiers principaux:

```text
scripts/DES/USD_FINAL_build.py
scripts/DES/USD_FINAL_simulation.py
scripts/DES/production_layout.json
3d/layout/model.usd
3d/layout/carrier.usd
```

Commandes:

```powershell
cd $PROJECT_ROOT
python scripts\DES\USD_FINAL_build.py
python scripts\DES\USD_FINAL_simulation.py
```

Sorties:

```text
3d/DES/model_build.usd
3d/DES/model_replay.usd
```

Ouvrir ensuite `3d/DES/model_replay.usd` dans USD Composer pour lire l'animation.

Etapes detaillees:

1. `USD_FINAL_build.py` ouvre `3d/layout/model.usd`, cree `/World/Palettes`, reference `3d/layout/carrier.usd`, ajoute les palettes selon `num_palettes`, puis exporte `3d/DES/model_build.usd`.
2. `USD_FINAL_simulation.py` ouvre `3d/DES/model_build.usd`, execute la simulation SimPy, ajoute les keyframes sur chaque palette, puis exporte `3d/DES/model_replay.usd`.
3. USD Composer lit ensuite `model_replay.usd` comme une animation offline classique.

Options utiles:

```powershell
python scripts\DES\USD_FINAL_simulation.py --until 3000
python scripts\DES\USD_FINAL_simulation.py --skip-usd-export
python scripts\DES\USD_FINAL_simulation.py --start-all-at-once
python scripts\DES\USD_FINAL_simulation.py --event-log scripts\DES\des_events.ndjson
```

Options CLI:

| Option | Effet |
| --- | --- |
| `--until` | temps d'arret de la simulation en secondes simulees |
| `--skip-usd-export` | execute la logique sans ecrire `model_replay.usd`; utile pour debug rapide |
| `--start-all-at-once` | lance toutes les palettes a `t=0` au lieu d'utiliser `inter_arrival_time` |
| `--event-log` | ecrit un NDJSON des evenements live compatibles avec un replay/debug TCP |

Valeurs metier actuelles dans `production_layout.json`:

| Parametre | Valeur actuelle |
| --- | --- |
| `simulation_params.num_palettes` | `10` |
| `simulation_params.inter_arrival_time` | `72` |
| `simulation_params.transport_speed` | `5` |
| `simulation_params.max_cycles` | `3` |
| `workstations.Human.cycle_times` | `[48, 120, 48]` |
| `workstations.Robot_1.process_time` | `144` |
| `workstations.Robot_2.process_time` | `144` |

Logique DES detaillee:

1. Au demarrage, chaque palette est placee a partir de `palette_template.initial_position`; les suivantes sont decalees avec `palette_template.initial_spacing`.
2. Les palettes sont lancees une par une selon `simulation_params.inter_arrival_time`, sauf avec `--start-all-at-once`.
3. Chaque palette repete `simulation_params.max_cycles` cycles.
4. A chaque cycle, la palette doit passer par `Human`. Si Human est libre et que la file Human est vide, elle entre directement. Sinon, elle prend un slot dans `HUMAN_QUEUE`.
5. Les temps Human viennent de `workstations.Human.cycle_times`: cycle 1 = premiere valeur, cycle 2 = deuxieme valeur, cycle 3 = troisieme valeur.
6. Si ce n'est pas le dernier cycle, la palette part vers la zone robot via `HUMAN_TO_ROBOT_AREA`. Le passage entre `human_to_queue_p1` et `human_to_queue_p2` est reconnu comme `Lift_ToQueue`, donc il prend la duree fixe `transfers.Lift_ToQueue.duration`.
7. Arrivee cote robots, si `Robot_1` ou `Robot_2` est libre et que la file robot est vide, la palette va directement au robot. Sinon elle attend dans `QUEUE_ROBOT_AREA`.
8. La selection robot est volontairement prioritaire: `Robot_1` d'abord, `Robot_2` ensuite.
9. La palette passe par `entry_exit_robot*`, va a `processing_robot*`, attend `process_time`, puis ressort par `entry_exit_robot*`.
10. La palette revient vers Human via `ROBOT_1_RETURN` ou `ROBOT_2_RETURN`. Le passage `robot_return_p1` -> `robot_return_p2` est reconnu comme `Lift_Return`, donc il prend la duree fixe `transfers.Lift_Return.duration`.
11. Les files ne se decalent pas des qu'une palette reserve une ressource; elles se decalent seulement quand la palette de tete a physiquement libere la zone critique. C'est important pour eviter les superpositions visuelles.
12. A la fin du dernier cycle Human, la palette est consideree terminee et ne repart plus vers les robots.

Ce scenario est donc le plus important pour comprendre la logique metier: il simule les ressources, les files, les priorites et les temps, puis transforme le resultat en animation USD.

## Scenario 2 - RealtimeTCP live

Fichiers principaux:

```text
scripts/RealtimeTCP/realtime_tcp_build_and_produce.py
scripts/RealtimeTCP/usd_composer_tcp_realtime_bridge.py
scripts/RealtimeTCP/tcp_client.py
scripts/RealtimeTCP/production_layout_realtime.json
scripts/RealtimeTCP/places.json
3d/RealtimeTCP/model.usd
```

Etape 1: ouvrir dans USD Composer:

```text
3d/RealtimeTCP/model.usd
```

Etape 2: lancer le bridge dans le Script Editor USD Composer:

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Projects\USD_Composer")
SCRIPTS = PROJECT_ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import RealtimeTCP.usd_composer_tcp_realtime_bridge as rt

rt.stop_tcp_bridge()
rt.start_tcp_bridge(
    host="127.0.0.1",
    port=5050,
    places_path=str(PROJECT_ROOT / "scripts" / "RealtimeTCP" / "places.json"),
)

print(rt.bridge_status())
```

Etape 3: lancer le producteur dans PowerShell:

```powershell
cd $PROJECT_ROOT
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py
```

Options utiles:

```powershell
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --until 120
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --no-live-tcp --until 120
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --event-log scripts\RealtimeTCP\events.ndjson
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --realtime-factor 0.25
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --start-all-at-once
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --host 127.0.0.1 --port 5050
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --config scripts\RealtimeTCP\production_layout_realtime.json
```

Notes:

- `--realtime-factor 1.0` signifie `1` seconde simulee = `1` seconde murale.
- `--realtime-factor 0.25` accelere le rendu live: `1` seconde simulee prend `0.25` seconde murale.
- `--no-live-tcp` permet de tester la simulation sans USD Composer.
- Le producteur envoie surtout des positions directes ou des chemins TCP; `places.json` peut rester vide.

Options CLI:

| Option | Effet |
| --- | --- |
| `--config` | remplace le layout JSON par defaut |
| `--event-log` | ecrit une copie NDJSON des messages envoyes ou generes |
| `--live-tcp` | active l'envoi TCP live; c'est le comportement par defaut |
| `--no-live-tcp` | coupe la connexion TCP et garde seulement la simulation en memoire |
| `--host` | host du bridge Composer, par defaut `127.0.0.1` |
| `--port` | port du bridge Composer, par defaut `5050` |
| `--realtime-factor` | facteur de temps mur: `1.0` = temps reel, `0.25` = 4x plus rapide |
| `--until` | temps d'arret de la simulation en secondes simulees |
| `--start-all-at-once` | lance toutes les palettes a `t=0` |

Valeurs actuelles dans `production_layout_realtime.json`:

| Parametre | Valeur actuelle |
| --- | --- |
| `simulation_params.num_palettes` | `10` |
| `simulation_params.inter_arrival_time` | `3` |
| `simulation_params.transport_speed` | `80` |
| `simulation_params.max_cycles` | `3` |
| `workstations.Human.cycle_times` | `[2, 5, 2]` |
| `workstations.Robot_1.process_time` | `6` |
| `workstations.Robot_2.process_time` | `6` |

Logique RealtimeTCP detaillee:

1. `RealtimeTCP` reprend presque la meme logique metier que `DES`: Human, file Human, lift vers queue robot, file robot commune, priorite `Robot_1` puis `Robot_2`, retour vers Human.
2. La difference principale est la sortie: au lieu d'ecrire une animation USD a la fin, le script envoie les mouvements immediatement au bridge TCP dans USD Composer.
3. Le script Python utilise une simulation SimPy en temps reel quand `--live-tcp` est actif. Le parametre `--realtime-factor` controle le lien entre temps simule et temps mur.
4. Au lancement, le producteur envoie des messages de seed pour creer/placer les palettes dans Composer.
5. Pendant la simulation, chaque mouvement devient un message JSON TCP: `set_position`, `move_linear` ou surtout `move_path`.
6. Chaque message peut porter un `event_id` et un `sim_time`; le bridge les utilise pour ignorer les messages trop anciens ou arrives dans le mauvais ordre.
7. Le bridge Composer recoit les JSON ligne par ligne, cree les prims `/World/Palettes/Palette_N` si besoin, puis interpole leur position a chaque frame Composer.
8. Les lifts restent des ressources logiques exclusives: si la capacite vaut `1`, une seule palette peut occuper le lift a la fois.

En resume: `DES` calcule puis exporte, `RealtimeTCP` calcule et diffuse en direct. C'est le scenario a utiliser pour une demo live de la logique DES.

## Scenario 3 - Simulogs offline

Fichiers principaux:

```text
scripts/Simulogs/01_build_from_logs.py
scripts/Simulogs/02_replay_logs.py
scripts/Simulogs/production_layout_simulogs.json
scripts/Simulogs/CSV/logs.csv
3d/layout/modelbuffer.usd
3d/layout/carrier.usd
```

Commandes:

```powershell
cd $PROJECT_ROOT
python scripts\Simulogs\01_build_from_logs.py
python scripts\Simulogs\02_replay_logs.py
```

Sorties:

```text
3d/Simulogs/modelbuffer_build.usd
3d/Simulogs/modelbuffer_replay.usd
```

Ouvrir ensuite `3d/Simulogs/modelbuffer_replay.usd` dans USD Composer.

Format CSV attendu:

```csv
carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details
```

Colonnes CSV:

| Colonne | Description |
| --- | --- |
| `carrier_id` | identifiant numerique de la palette/carrier |
| `origin_id` | ressource d'origine; peut etre vide pour une apparition/depart initial |
| `event_type` | type d'evenement: `TRANSPORT`, `QUEUE` ou `PROCESSING` |
| `destination_id` | ressource cible selon `resource_map` |
| `start_time` | heure de debut; format `HH:MM:SS`, `HH:MM:SS.s` ou secondes |
| `processing_time` | duree declaree; sert de secours si `end_time` est absent ou incoherent |
| `end_time` | heure de fin; si elle est inferieure a `start_time`, le script recalcule avec `processing_time` |
| `task_id` | identifiant de tache ou d'etape; utilise pour trier/stabiliser les evenements |
| `details` | champ libre; conserve pour information mais peu utilise par la geometrie |

Exemple minimal:

```csv
carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details
1,,TRANSPORT,1,00:00:00,0.0,00:00:00,1,spawn human
1,1,TRANSPORT,6,00:00:05,9.3,00:00:14,2,human to lift
1,6,TRANSPORT,5,00:00:14,3.0,00:00:17,3,lift to visual
1,5,TRANSPORT,2,00:00:17,5.2,00:00:22,4,visual to robot1
1,2,PROCESSING,2,00:00:22,6.0,00:00:28,5,robot1 process
```

Types d'evenements geres:

| Type | Effet visuel |
| --- | --- |
| `TRANSPORT` | deplacement entre deux ressources |
| `QUEUE` | attente dans un buffer ou une file |
| `PROCESSING` | maintien ou micro-mouvement vers la position de traitement |

Les lignes sont triees par `carrier_id`, `start_time`, `end_time`, `task_id`, `event_type` avant l'animation offline.

Logique Simulogs detaillee:

1. `01_build_from_logs.py` lit tous les `carrier_id` du CSV et cree une palette par carrier dans `3d/Simulogs/modelbuffer_build.usd`.
2. `02_replay_logs.py` relit le CSV, convertit chaque ligne en mouvement ou en maintien, puis ecrit les keyframes dans `3d/Simulogs/modelbuffer_replay.usd`.
3. `resource_map` transforme les IDs CSV en noms lisibles: par exemple `1` -> `Human`, `2` -> `Robot_1`.
4. Pour un `TRANSPORT`, le script cherche une route `origin->destination` dans `routes`. Si `origin_id` est vide, la cle utilisee est `START->destination`.
5. Si une route traverse un segment declare dans `transfers`, la duree du transfert est forcee par le JSON. Exemple: le lift garde `4.0` secondes meme si la distance est courte.
6. Pour un `QUEUE`, le script affecte un slot dans `buffer_path`. Le rang `0` est le plus proche du process; les suivants reculent dans la file.
7. Pour un `PROCESSING`, le carrier va vers `processing`, puis reste visible jusqu'a `end_time`.
8. `path_sample_step` ajoute des points intermediaires sur les longs trajets pour rendre le mouvement plus fluide.

## Scenario 4 - RealTimeTCPlogs live

Fichiers principaux:

```text
scripts/RealTimeTCPlogs/realtime_tcp_logs_live.py
scripts/RealTimeTCPlogs/usd_composer_tcp_logs_bridge.py
scripts/RealTimeTCPlogs/tcp_logs_client.py
scripts/RealTimeTCPlogs/realtimetcp_logs_config.json
scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
scripts/RealTimeTCPlogs/CSV/logs.csv
3d/RealTimeTCPlogs/modelbuffer.usd
```

Etape 1: ouvrir dans USD Composer:

```text
3d/RealTimeTCPlogs/modelbuffer.usd
```

Etape 2: lancer le bridge dans le Script Editor USD Composer:

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Projects\USD_Composer")
SCRIPTS = PROJECT_ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import RealTimeTCPlogs.usd_composer_tcp_logs_bridge as rtlogs

rtlogs.stop_tcp_bridge()
rtlogs.start_tcp_bridge(host="127.0.0.1", port=5051, debug=True)

print(rtlogs.bridge_status())
```

Etape 3: lancer le lecteur de logs dans PowerShell.

Pour rejouer les lignes deja presentes dans le CSV:

```powershell
cd $PROJECT_ROOT
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --drain-existing --replay-timing
```

Pour suivre uniquement les nouvelles lignes ajoutees au CSV:

```powershell
cd $PROJECT_ROOT
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py
```

Options utiles:

```powershell
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --dry-run --print-messages
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --drain-existing --replay-timing --replay-scale 0.25
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --duration-scale 0.5
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --idle-timeout 10
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --max-events 50
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --audit-log scripts\RealTimeTCPlogs\rtlogs_audit.ndjson
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --logs scripts\RealTimeTCPlogs\CSV\logs.csv
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --host 127.0.0.1 --port 5051
```

Options CLI:

| Option | Effet |
| --- | --- |
| `--config` | fichier `realtimetcp_logs_config.json` a utiliser |
| `--layout` | force un layout different de celui indique dans la config |
| `--logs` | force un CSV different de celui indique dans la config |
| `--host` | host du bridge Composer |
| `--port` | port du bridge Composer |
| `--timeout` | timeout de connexion TCP |
| `--duration-scale` | multiplie les durees des mouvements envoyes au bridge |
| `--poll-interval` | frequence de lecture du CSV quand on attend de nouvelles lignes |
| `--drain-existing` | traite les lignes deja presentes dans le CSV |
| `--replay-timing` | respecte les `start_time` pendant un drain existing |
| `--replay-scale` | multiplie les attentes entre evenements pendant `--replay-timing` |
| `--idle-timeout` | arrete le script apres N secondes sans nouvelle ligne |
| `--max-events` | arrete apres N lignes traitees |
| `--dry-run` | ne se connecte pas au bridge TCP |
| `--print-messages` | affiche les JSON sortants |
| `--audit-log` | ecrit une copie NDJSON des messages envoyes |

Comportement important:

- Sans `--drain-existing`, le script se place a la fin du CSV et attend les nouvelles lignes.
- Avec `--drain-existing`, il traite les lignes deja presentes.
- Avec `--replay-timing`, il respecte les `start_time` du CSV.
- `--replay-scale 0.25` accelere l'attente entre lignes existantes.
- Le bridge garde une file de mouvements par carrier: un nouveau mouvement n'ecrase pas le mouvement actif du meme carrier.

CSV en live:

- Le format est le meme que pour `Simulogs`: `carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details`.
- En mode live normal, le script ne relit pas l'historique: il attend les nouvelles lignes ajoutees apres son lancement.
- Pour une vraie source externe, il faut ajouter les lignes CSV avec l'en-tete deja present et des champs dans le meme ordre.
- Les `TRANSPORT` sont temporairement gardes en attente par carrier pour regarder l'evenement suivant. Cela permet de savoir si le transport doit arriver directement en processing ou seulement a l'entree d'une file.
- Les `QUEUE` servent a placer le carrier dans un slot de buffer.
- Les `PROCESSING` retirent le carrier de la file logique et l'amenent vers le marker `processing`.

Logique RealTimeTCPlogs detaillee:

1. `realtime_tcp_logs_live.py` lit `realtimetcp_logs_config.json`.
2. La config pointe vers un CSV, un layout et un stage Composer attendu.
3. Le layout convertit les IDs CSV en ressources et les routes en chemins de markers.
4. Pour chaque ligne traitee, le script cree un message JSON: `set_position`, `set_visibility`, `move_path` ou `move_timed_path`.
5. Le bridge Composer recoit les messages sur `127.0.0.1:5051` et cree les carriers sous `/World/RealTimeTCPlogs/Carriers/Carrier_N`.
6. Contrairement au bridge `RealtimeTCP`, celui-ci garde une queue de messages par carrier. Si un carrier est deja en mouvement, le mouvement suivant attend son tour.
7. `move_timed_path` conserve les durees par segment, ce qui est utile pour garder les lifts a duree fixe tout en respectant les temps du CSV.

Self-test direct dans USD Composer:

```python
import RealTimeTCPlogs.usd_composer_tcp_logs_bridge as rtlogs
rtlogs.bridge_self_test(carrier_id=999, duration=8.0)
```

## Auto Bridge extensions

Deux extensions Omniverse locales existent pour demarrer automatiquement les bridges si elles sont ajoutees au chemin d'extensions de USD Composer:

```text
scripts/RealtimeTCP/omni.realtimetcp.autobridge
scripts/RealTimeTCPlogs/omni.realtimetcplogs.autobridge
```

Parametres par defaut:

```text
omni.realtimetcp.autobridge       -> 127.0.0.1:5050
omni.realtimetcplogs.autobridge   -> 127.0.0.1:5051
```

Ces extensions sont pratiques pour eviter de coller les snippets dans le Script Editor. En cas de doute, utiliser les snippets manuels: ils sont explicites et permettent de voir `bridge_status()`.

## Parametres modifiables

### Layouts DES / RealtimeTCP

Fichiers:

```text
scripts/DES/production_layout.json
scripts/RealtimeTCP/production_layout_realtime.json
```

Champs importants:

| Champ | Role |
| --- | --- |
| `workstations.Human.cycle_times` | durees des cycles Human |
| `workstations.Robot_*.process_time` | duree de traitement des robots |
| `workstations.*.entry` | position d'entree d'un poste |
| `workstations.*.processing` | position de traitement |
| `workstations.*.exit` | position de sortie |
| `transfers.*.duration` | duree fixe d'un transfert, par exemple un lift |
| `transfers.*.capacity` | capacite logique du transfert |
| `transfers.*.from` / `to` | extremites d'un transfert a duree fixe |
| `conveyor_segments.*.waypoints` | chemin suivi par les palettes |
| `conveyor_segments.*.capacity` | capacite logique du segment |
| `conveyor_segments.*.slot_spacing` | espacement des palettes en file |
| `conveyor_segments.*.is_queue_zone` | active le placement de type file |
| `conveyor_segments.*.extend_after_end` | autorise les slots apres le dernier waypoint |
| `palette_template.asset_path` | asset USD utilise pour les palettes |
| `palette_template.initial_position` | position initiale |
| `palette_template.initial_spacing` | espacement initial entre palettes |
| `palette_template.scale` | echelle du carrier |
| `simulation_params.num_palettes` | nombre de palettes |
| `simulation_params.inter_arrival_time` | delai entre lancements |
| `simulation_params.transport_speed` | vitesse des deplacements hors transferts fixes |
| `simulation_params.max_cycles` | nombre de cycles par palette |
| `simulation_params.timeline_fps` | FPS de la timeline USD offline |
| `marker_stage` | scene USD qui contient les markers |

Attention: la logique DES actuelle est codee pour `Human`, `Robot_1` et `Robot_2`. Ajouter un `Robot_3` au DES ne se limite pas au JSON; il faut aussi adapter le code de selection robot et les segments de retour.

Lecture precise des parametres DES / RealtimeTCP:

| Parametre | Type | Explication |
| --- | --- | --- |
| `workstations` | objet | liste des postes logiques connus par la simulation |
| `workstations.Human.entry` | marker ou coordonnees | point ou la palette entre dans le poste Human |
| `workstations.Human.buffer` | marker ou coordonnees | point de buffer Human; dans ce DES il est identique au marker Human |
| `workstations.Human.processing` | marker ou coordonnees | point ou la palette reste pendant le traitement Human |
| `workstations.Human.exit` | marker ou coordonnees | point de sortie Human |
| `workstations.Human.cycle_times` | liste de nombres | duree de traitement Human par cycle; doit couvrir `max_cycles` |
| `workstations.Robot_1.entry` | marker ou coordonnees | point d'entree Robot_1 |
| `workstations.Robot_1.processing` | marker ou coordonnees | point de traitement Robot_1 |
| `workstations.Robot_1.exit` | marker ou coordonnees | point de sortie Robot_1 |
| `workstations.Robot_1.process_time` | nombre | duree de traitement Robot_1 |
| `workstations.Robot_2.*` | idem Robot_1 | memes champs pour Robot_2 |
| `transfers` | objet | segments avec duree fixe et capacite propre |
| `transfers.Lift_ToQueue.duration` | nombre | temps impose pour le lift Human -> queue robot |
| `transfers.Lift_ToQueue.capacity` | entier | nombre de palettes autorisees simultanement dans ce lift |
| `transfers.Lift_ToQueue.from` | marker ou coordonnees | debut du segment reconnu comme lift |
| `transfers.Lift_ToQueue.to` | marker ou coordonnees | fin du segment reconnu comme lift |
| `transfers.Lift_Return.*` | idem | retour robot -> Human |
| `conveyor_segments` | objet | chemins logiques empruntes par les palettes |
| `conveyor_segments.START_TO_HUMAN.waypoints` | liste | chemin initial vers Human; ici un seul marker |
| `conveyor_segments.*.capacity` | entier | nombre de palettes admises sur le segment |
| `conveyor_segments.*.slot_spacing` | nombre | distance entre deux palettes quand elles occupent des slots |
| `conveyor_segments.*.is_queue_zone` | booleen | si `true`, les slots sont repartis entre le premier et le dernier waypoint |
| `conveyor_segments.*.extend_after_end` | booleen | si `true`, les slots peuvent continuer apres le dernier waypoint |
| `palette_template.prototype_path` | chemin USD | prim prototype cache qui reference l'asset palette |
| `palette_template.instance_prefix` | chemin USD | prefixe utilise pour creer `/World/Palettes/Palette_1`, etc. |
| `palette_template.asset_path` | chemin fichier | asset USD reference par chaque palette |
| `palette_template.initial_position` | marker ou coordonnees | position de la premiere palette au demarrage |
| `palette_template.initial_spacing` | nombre | decalage entre palettes au demarrage |
| `palette_template.scale` | liste `[x,y,z]` | echelle appliquee au carrier |
| `simulation_params.num_palettes` | entier | nombre de palettes creees et simulees |
| `simulation_params.inter_arrival_time` | nombre | delai entre deux lancements de palettes |
| `simulation_params.transport_speed` | nombre | vitesse des mouvements hors transferts fixes |
| `simulation_params.max_cycles` | entier | nombre de cycles Human/Robot par palette |
| `simulation_params.timeline_fps` | nombre | FPS utilise pour les keyframes USD offline; garde `24` sauf besoin precis |
| `marker_stage` | chemin fichier | USD source dans lequel `marker_layout.py` lit les markers |

### Layouts logs

Fichiers:

```text
scripts/Simulogs/production_layout_simulogs.json
scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
```

Champs importants:

| Champ | Role |
| --- | --- |
| `resource_map` | correspondance ID CSV -> nom de ressource |
| `workstations.*.entry` | entree de la ressource |
| `workstations.*.processing` | position de traitement |
| `workstations.*.exit` | sortie de la ressource |
| `workstations.*.buffer` | position buffer principale |
| `workstations.*.buffer_path` | slots de file/buffer |
| `workstations.*.entry_to_buffer` | chemin entree -> buffer |
| `workstations.*.buffer_to_processing` | chemin buffer -> process |
| `workstations.*.processing_to_exit` | chemin process -> sortie |
| `routes` | routes globales entre ressources, par exemple `1->6` |
| `transfers` | segments a duree fixe, par exemple les lifts |
| `palette_template` | prototype, prefixe, position initiale, echelle, asset |
| `simulation_params.path_sample_step` | densite des points intermediaires |
| `simulation_params.max_keys_per_motion` | limite de points par mouvement |
| `simulation_params.micro_move_seconds` | duree minimale des petits mouvements visuels |
| `marker_stage` | scene USD qui contient les markers |

Pour ajouter une route de logs, ajouter ou modifier une cle dans `routes`, par exemple:

```json
"2->7": [
  "marker:entry_exit_robot1",
  "marker:robot_to_lift2_p1",
  "marker:lift2"
]
```

Lecture precise des parametres logs:

| Parametre | Type | Explication |
| --- | --- | --- |
| `resource_map` | objet | associe les IDs du CSV aux noms utilises dans `workstations` |
| `transfers` | objet | segments a duree fixe detectes dans les routes |
| `transfers.*.duration` | nombre | duree imposee pour ce segment |
| `transfers.*.capacity` | entier | valeur documentaire/logique; surtout utile pour garder la coherence avec DES |
| `transfers.*.from` | marker ou coordonnees | point de depart du segment fixe |
| `transfers.*.to` | marker ou coordonnees | point d'arrivee du segment fixe |
| `workstations.*.entry` | marker ou coordonnees | position d'arrivee depuis une route globale |
| `workstations.*.processing` | marker ou coordonnees | position de traitement |
| `workstations.*.exit` | marker ou coordonnees | position de depart vers une route globale |
| `workstations.*.entry_to_processing` | liste | chemin local entree -> processing |
| `workstations.*.processing_to_exit` | liste | chemin local processing -> sortie |
| `workstations.*.buffer` | marker ou coordonnees | position buffer principale |
| `workstations.*.entry_to_buffer` | liste | chemin local entree -> file |
| `workstations.*.buffer_path` | liste | slots de file; le dernier slot est le plus proche du processing |
| `workstations.*.buffer_to_processing` | liste | chemin local file -> processing |
| `workstations.*.processing_to_buffer` | liste | chemin retour processing -> file, utile pour certains logs |
| `routes.START->1` | liste | route utilisee quand `origin_id` est vide et `destination_id=1` |
| `routes.A->B` | liste | route globale entre deux IDs CSV |
| `palette_template.prototype_path` | chemin USD | prototype cache des carriers |
| `palette_template.instance_prefix` | chemin USD | prefixe des instances offline `/World/Palettes/Palette_N` |
| `palette_template.initial_position` | marker ou coordonnees | position de depart avant le premier evenement |
| `palette_template.scale` | liste `[x,y,z]` | echelle appliquee au carrier |
| `palette_template.asset_path` | chemin fichier | asset USD du carrier |
| `simulation_params.timeline_fps` | nombre | FPS du replay offline Simulogs |
| `simulation_params.path_sample_step` | nombre | distance entre points intermediaires sur les routes longues |
| `simulation_params.max_keys_per_motion` | entier | limite de points/keyframes pour eviter des fichiers trop lourds |
| `simulation_params.queue_slots_per_station` | entier | parametre documentaire ici; les vrais slots viennent de `buffer_path` |
| `simulation_params.micro_move_seconds` | nombre | duree minimale pour rendre visible un petit mouvement |
| `marker_stage` | chemin fichier | scene USD qui contient les markers du layout |

### Config RealTimeTCPlogs

Fichier:

```text
scripts/RealTimeTCPlogs/realtimetcp_logs_config.json
```

Champs:

| Champ | Role |
| --- | --- |
| `tcp.host` | host du bridge USD Composer |
| `tcp.port` | port du bridge USD Composer |
| `tcp.timeout` | timeout de connexion |
| `logs.path` | CSV suivi en live |
| `logs.poll_interval` | frequence de lecture du CSV |
| `runtime.duration_scale` | facteur applique aux durees envoyees au bridge |
| `composer_stage` | scene a ouvrir dans USD Composer |
| `layout` | layout utilise pour convertir logs -> trajectoires |

## Comment changer les choses courantes

Changer le nombre de palettes DES ou RealtimeTCP:

```json
"simulation_params": {
  "num_palettes": 10
}
```

Changer les temps de process:

```json
"Human": { "cycle_times": [48, 120, 48] }
"Robot_1": { "process_time": 144 }
```

Changer la vitesse de transport:

```json
"transport_speed": 5
```

Changer un chemin:

```json
"waypoints": [
  "marker:human",
  "marker:human_to_queue_p1",
  "marker:human_to_queue_p2",
  "marker:start_robot_queue"
]
```

Changer un port TCP:

1. Changer le port dans le snippet Composer ou dans l'extension.
2. Lancer le producteur avec le meme port:

```powershell
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --port 5052
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --port 5053
```

Remplacer l'asset palette:

```json
"palette_template": {
  "asset_path": "3d/layout/carrier.usd",
  "scale": [0.15, 0.15, 0.15]
}
```

## Depannage

### `ModuleNotFoundError: No module named 'pxr'`

Le Python utilise ne contient pas OpenUSD. Utiliser le Python de USD Composer / Omniverse, ou un environnement qui expose `pxr`.

### `ModuleNotFoundError: No module named 'simpy'`

Installer `simpy` dans l'environnement Python utilise:

```powershell
python -m pip install simpy
```

### Rien ne bouge en RealtimeTCP

- Verifier que `3d/RealtimeTCP/model.usd` est ouvert dans USD Composer.
- Verifier que le bridge Composer ecoute sur `127.0.0.1:5050`.
- Dans Composer, executer `print(rt.bridge_status())`.
- Dans PowerShell, tester sans TCP:

```powershell
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --no-live-tcp --until 30
```

### Rien ne bouge en RealTimeTCPlogs

- Verifier que `3d/RealTimeTCPlogs/modelbuffer.usd` est ouvert.
- Verifier que le bridge ecoute sur `127.0.0.1:5051`.
- Pour tester les messages sans TCP:

```powershell
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --dry-run --print-messages --max-events 10 --drain-existing
```

- Pour tester le bridge seul dans Composer:

```python
rtlogs.bridge_self_test(carrier_id=999, duration=8.0)
```

### Le script RealTimeTCPlogs semble bloque

C'est normal si `--drain-existing` n'est pas utilise: le script attend les nouvelles lignes ajoutees au CSV. Pour rejouer le fichier deja present:

```powershell
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --drain-existing --replay-timing
```

### Erreur marker introuvable

- Ouvrir le fichier indique par `marker_stage`.
- Verifier que le prim `Markers` existe.
- Verifier le nom exact apres `marker:`.
- Sauvegarder la scene USD apres modification.

### Port deja utilise

Un ancien bridge tourne peut-etre encore. Dans le Script Editor:

```python
rt.stop_tcp_bridge()
rtlogs.stop_tcp_bridge()
```

Puis relancer le bridge, ou choisir un autre port cote Composer et cote PowerShell.

### Les palettes se superposent

- Verifier `capacity`, `slot_spacing`, `is_queue_zone` et `extend_after_end`.
- Verifier que les markers de file sont dans le bon ordre.
- Verifier que les lifts gardent une capacite de `1` si le systeme doit rester exclusif.

## Verification avant passation

Executer au minimum:

```powershell
cd $PROJECT_ROOT
python -m compileall -q scripts\DES scripts\RealtimeTCP scripts\Simulogs scripts\RealTimeTCPlogs
```

Puis verifier les quatre parcours:

```powershell
python scripts\DES\USD_FINAL_build.py
python scripts\DES\USD_FINAL_simulation.py --until 300
python scripts\Simulogs\01_build_from_logs.py
python scripts\Simulogs\02_replay_logs.py
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --no-live-tcp --until 30
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --dry-run --print-messages --drain-existing --max-events 10
```

Si le dossier est suivi par Git:

```powershell
git status
```

Le repertoire courant fourni ici ne contient pas forcement `.git`; dans ce cas `git status` peut repondre que ce n'est pas un depot Git.

## Checklist pour la personne suivante

- Lire la section "Demarrage rapide".
- Verifier `simpy` et `pxr`.
- Ouvrir les bonnes scenes USD selon le scenario.
- Pour un mode live, demarrer le bridge dans Composer avant le script PowerShell.
- Modifier les positions dans les markers USD, pas directement dans le code.
- Modifier les temps, capacites, routes et nombres de palettes dans les JSON.
- Garder les ports Composer et PowerShell identiques.
- Ne pas versionner les sorties generees, les caches, les logs temporaires ou `.venv/`.
