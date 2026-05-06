# USD Composer - Complete Handover Guide

This system represents a production line in USD Composer with palettes/carriers, a Human workstation, robots, lifts, queues, and both offline and live replay modes.

## Path Convention

Throughout this README, `PROJECT_ROOT` means the root folder of this project: the folder that contains `README.md`, `3d/`, and `scripts/`.

The project can be installed anywhere, for example:

```text
C:\Projects\USD_Composer
D:\Work\ku_leuven_des
E:\Engineering\USD_Composer
```

Important rule: only change the value of `PROJECT_ROOT` in commands and Python snippets. Do not change internal project paths such as `scripts\DES\...`, `scripts\RealtimeTCP\...`, or `3d\layout\...`, because those paths are relative to `PROJECT_ROOT`.

PowerShell example:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

USD Composer Script Editor example:

```python
PROJECT_ROOT = Path(r"C:\Projects\USD_Composer")
```

## Install From GitHub

On a new machine, start with:

```powershell
$WORKSPACE_DIR = "C:\Projects"
$PROJECT_DIR_NAME = "USD_Composer"
$PROJECT_ROOT = Join-Path $WORKSPACE_DIR $PROJECT_DIR_NAME

git lfs install
git clone https://github.com/dwgitdw/ku_leuven_des.git $PROJECT_ROOT
cd $PROJECT_ROOT
git lfs pull
```

Only change `$WORKSPACE_DIR` to choose where the project is installed, and optionally `$PROJECT_DIR_NAME` to choose the local folder name. The local folder can remain `USD_Composer` even though the GitHub repository is named `ku_leuven_des`.

If a new PowerShell terminal is opened later, simply define the project path again:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

Adjust the value to match the folder chosen during the clone step.

Then install the NVIDIA template inside the project folder:

```powershell
git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git kit-app-template
cd kit-app-template
git lfs pull
cd ..
```

Expected structure after installation:

```text
USD_Composer/
  kit-app-template/        NVIDIA template installed locally
  3d/                      USD scenes, assets, and 3D layouts for this project
  scripts/                 scenarios, TCP bridges, and Python tooling
  README.md
  .gitignore
  .gitattributes
```

This installation does not change the project architecture. `kit-app-template/` remains an external reference folder and is ignored by Git. The actual system files remain in `3d/` and `scripts/`.

The `.gitattributes` file does not move anything and does not modify the scenes. It only tells GitHub to store large `.usd` and `.stp` files with Git LFS. For someone cloning the project, the only requirement is to have Git LFS installed and to run `git lfs pull` if the assets are not downloaded automatically.

Minimum installation check:

```powershell
python -c "import simpy; print('simpy OK')"
python -c "from pxr import Usd; print('pxr OK')"
```

If `pxr` fails, run the scripts with the USD Composer / Omniverse Python environment, or with another Python environment that provides compatible OpenUSD bindings.

## NVIDIA Omniverse Kit App Template Note

Upstream reference: [NVIDIA-Omniverse/kit-app-template](https://github.com/NVIDIA-Omniverse/kit-app-template)

This project is an USD Composer / Omniverse Kit application project derived from, or inspired by, the Kit App Template ecosystem. The local `kit-app-template/` folder, when present, is only a reference or template copy and is ignored by Git in this repository. To use this project, focus on `3d/` and `scripts/`: those folders contain the scenes, layouts, TCP bridges, and production scenarios.

In practice:

- `kit-app-template` is the upstream NVIDIA template for building Omniverse Kit / OpenUSD applications.
- `USD_Composer` is the production-line project documented here.
- To run or modify the simulation, do not restart from the template. Follow the commands in this README.
- To recreate a clean Kit application from scratch, follow the upstream NVIDIA README first, then reintegrate the project-specific assets and scripts.

## Install Kit App Template In This Folder

For a complete project handover, keep or install the NVIDIA template at the project root:

```text
USD_Composer/
  kit-app-template/
  3d/
  scripts/
  README.md
```

The template is intentionally ignored by `.gitignore` because it is an external dependency/reference. Do not worry if `git status` does not show it.

Kit App Template prerequisites according to NVIDIA:

- Windows 10/11 or Linux Ubuntu 22.04+.
- NVIDIA RTX GPU recommended.
- Compatible NVIDIA driver.
- Internet access to download the Kit SDK, extensions, and tools.
- Git and Git LFS.
- Visual Studio + Windows SDK only if compiling C++ on Windows.

Recommended Windows installation inside this project:

```powershell
cd $PROJECT_ROOT
git lfs install
git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git kit-app-template
cd kit-app-template
git lfs pull
cd ..
```

If `kit-app-template/` already exists, do not clone over it. Just enter the folder:

```powershell
cd $PROJECT_ROOT
cd kit-app-template
```

NVIDIA procedure for creating an application from the template:

```powershell
.\repo.bat template new
.\repo.bat build
.\repo.bat launch
```

During `template new`, use the following choices:

| Wizard question | Recommended choice |
| --- | --- |
| Type to create | `Application` |
| Template | `USD Composer` if the goal is close to this project, otherwise `Kit Base Editor` for a minimal base |
| `.kit` file name | short, lowercase, no spaces |
| Display name | readable application name |
| Version | for example `0.1.0` |
| Application layers | `No` for a simple local test |

Important: the scripts in this repository do not directly depend on an application generated by the wizard. The template is used to install/recreate the Kit environment and understand the Omniverse structure. To run the production scenarios, stay in `USD_Composer/` and follow the DES, RealtimeTCP, Simulogs, or RealTimeTCPlogs sections.

## Project Purpose

This repository visualizes a production line in USD Composer. It contains four active systems:

| System | Mode | Input | Output | Main use |
| --- | --- | --- | --- | --- |
| `DES` | Offline | JSON layout + source USD scene | Exported animated USD | Simulate the complete logic, then open a replay |
| `RealtimeTCP` | Live | Internal DES + JSON layout | TCP messages to USD Composer | Watch the simulation move in real time |
| `Simulogs` | Offline | CSV logs | Exported animated USD | Replay existing logs in a USD scene |
| `RealTimeTCPlogs` | Live | Continuously followed CSV | TCP messages to USD Composer | Visualize logs as they arrive during execution |

Key principle: positions are not hard-coded in the scripts. The JSON layouts use `marker:...` references; `scripts/marker_layout.py` reads those markers from USD files and replaces them with coordinates at runtime.

## Quick Start

Define `PROJECT_ROOT` once in the terminal:

```powershell
$PROJECT_ROOT = "C:\Projects\USD_Composer"
cd $PROJECT_ROOT
```

Check the Python environment:

```powershell
python -c "import simpy; print('simpy OK')"
python -c "from pxr import Usd; print('pxr OK')"
```

If `pxr` fails, run the scripts from a USD Composer / Omniverse Python environment, or install/use a Python environment with USD Python bindings.

Launch order to remember:

1. Install or verify `kit-app-template/` in the project folder if the machine is being set up from scratch.
2. Choose a scenario: `DES`, `RealtimeTCP`, `Simulogs`, or `RealTimeTCPlogs`.
3. Check the JSON configuration file for that scenario.
4. Check that the scene referenced by `marker_stage` contains the expected markers.
5. For an offline scenario, run the Python scripts, then open the generated USD file.
6. For a live scenario, first open the scene in USD Composer, start the TCP bridge inside Composer, then start the Python producer from PowerShell.

Quick scenario choice:

| Need | Scenario |
| --- | --- |
| Test the production logic without real time | `DES` |
| See the DES logic moving live in Composer | `RealtimeTCP` |
| Convert an existing CSV into a USD replay | `Simulogs` |
| Follow a CSV that is being written during execution | `RealTimeTCPlogs` |

## Prerequisites

- Windows with PowerShell for the commands below.
- NVIDIA USD Composer / Omniverse Kit to open scenes and run live bridges.
- Python with `simpy`.
- Python with `pxr` / OpenUSD for every script that reads markers or writes USD scenes.
- Free TCP ports:
  - `127.0.0.1:5050` for `RealtimeTCP`.
  - `127.0.0.1:5051` for `RealTimeTCPlogs`.

## Repository Architecture

```text
USD_Composer/
  README.md
  .gitignore

  3d/
    layout/
      model.usd                         source scene for DES / RealtimeTCP
      modelbuffer.usd                   source scene for Simulogs
      carrier.usd                       palette/carrier asset
    RealtimeTCP/
      model.usd                         live RealtimeTCP scene to open in Composer
    RealTimeTCPlogs/
      modelbuffer.usd                   live log scene to open in Composer
    DES/
      model_build.usd                   generated by DES build
      model_replay.usd                  generated by DES simulation
    Simulogs/
      modelbuffer_build.usd             generated by Simulogs build
      modelbuffer_replay.usd            generated by Simulogs replay

  scripts/
    marker_layout.py                    resolves marker:... references
    DES/                                offline discrete-event simulation
    RealtimeTCP/                        live DES simulation + Composer TCP bridge
    Simulogs/                           offline build/replay from CSV
    RealTimeTCPlogs/                    live CSV reader + Composer TCP bridge
```

The following files are generated locally or temporary: `.venv/`, `__pycache__/`, `*.pyc`, `*.ndjson`, generated USD build/replay exports, logs, and caches. They are ignored by `.gitignore`.

## Four-Scenario Flow

```text
DES offline
  scripts/DES/production_layout.json
  + 3d/layout/model.usd
  + 3d/layout/carrier.usd
  -> 3d/DES/model_build.usd
  -> 3d/DES/model_replay.usd

RealtimeTCP live
  scripts/RealtimeTCP/production_layout_realtime.json
  + 3d/RealtimeTCP/model.usd opened in Composer
  + Composer bridge on 127.0.0.1:5050
  -> live animated palettes in USD Composer

Simulogs offline
  scripts/Simulogs/CSV/logs.csv
  + scripts/Simulogs/production_layout_simulogs.json
  + 3d/layout/modelbuffer.usd
  -> 3d/Simulogs/modelbuffer_build.usd
  -> 3d/Simulogs/modelbuffer_replay.usd

RealTimeTCPlogs live
  scripts/RealTimeTCPlogs/CSV/logs.csv
  + scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
  + 3d/RealTimeTCPlogs/modelbuffer.usd opened in Composer
  + Composer bridge on 127.0.0.1:5051
  -> live animated carriers in USD Composer
```

## Markers And Layouts

A marker is an `Xform` prim inside a USD scene. The scripts look for a prim named `Markers`, with the following supported roots:

```text
/World/Markers
/model/Markers
/Markers
```

The script also accepts another prim named `Markers` found while traversing the stage.

In JSON layouts, a position is referenced like this:

```json
"entry": "marker:human"
```

The `marker_stage` field tells the scripts which USD file contains the markers:

```json
"marker_stage": "3d/layout/model.usd"
```

To move a workstation, buffer, or trajectory:

1. Open the file referenced by `marker_stage` in USD Composer.
2. Move or create the marker under `Markers`.
3. Save the USD scene.
4. Run the relevant script again.

## DES / RealtimeTCP Markers

Source scene:

```text
3d/layout/model.usd
```

Expected markers:

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

Business logic:

```text
Human -> Lift_ToQueue -> Robot queue -> Robot_1/Robot_2 -> Lift_Return -> Human
```

Current rules:

- Human has a queue.
- If Human is free and the Human queue is empty, a palette can enter directly.
- The robot queue is shared by `Robot_1` and `Robot_2`.
- If a robot is free and the robot queue is empty, the palette can go directly to that robot.
- Strict priority: `Robot_1`, then `Robot_2`.
- Palettes pass through `entry_exit_robot*` before `processing_robot*`.
- `Lift_ToQueue` and `Lift_Return` each last `4.0` seconds and have a logical capacity of `1`.

## Simulogs / RealTimeTCPlogs Markers

Source scenes:

```text
3d/layout/modelbuffer.usd                  for offline Simulogs
3d/RealTimeTCPlogs/modelbuffer.usd         for live RealTimeTCPlogs
```

Resource IDs in the CSV files:

```text
1 = Human
2 = Robot_1
3 = Robot_2
4 = Robot_3
5 = Visual_System
6 = Lift_ToQueue_End
7 = Lift_Return_End
```

Main markers:

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

## Scenario 1 - DES Offline

Main files:

```text
scripts/DES/USD_FINAL_build.py
scripts/DES/USD_FINAL_simulation.py
scripts/DES/production_layout.json
3d/layout/model.usd
3d/layout/carrier.usd
```

Commands:

```powershell
cd $PROJECT_ROOT
python scripts\DES\USD_FINAL_build.py
python scripts\DES\USD_FINAL_simulation.py
```

Outputs:

```text
3d/DES/model_build.usd
3d/DES/model_replay.usd
```

Then open `3d/DES/model_replay.usd` in USD Composer to play the animation.

Detailed steps:

1. `USD_FINAL_build.py` opens `3d/layout/model.usd`, creates `/World/Palettes`, references `3d/layout/carrier.usd`, adds palettes according to `num_palettes`, then exports `3d/DES/model_build.usd`.
2. `USD_FINAL_simulation.py` opens `3d/DES/model_build.usd`, runs the SimPy simulation, adds keyframes on each palette, then exports `3d/DES/model_replay.usd`.
3. USD Composer then reads `model_replay.usd` as a standard offline animation.

Useful options:

```powershell
python scripts\DES\USD_FINAL_simulation.py --until 3000
python scripts\DES\USD_FINAL_simulation.py --skip-usd-export
python scripts\DES\USD_FINAL_simulation.py --start-all-at-once
python scripts\DES\USD_FINAL_simulation.py --event-log scripts\DES\des_events.ndjson
```

CLI options:

| Option | Effect |
| --- | --- |
| `--until` | simulation stop time in simulated seconds |
| `--skip-usd-export` | runs the logic without writing `model_replay.usd`; useful for quick debugging |
| `--start-all-at-once` | starts all palettes at `t=0` instead of using `inter_arrival_time` |
| `--event-log` | writes an NDJSON event log compatible with TCP replay/debugging |

Current business values in `production_layout.json`:

| Parameter | Current value |
| --- | --- |
| `simulation_params.num_palettes` | `10` |
| `simulation_params.inter_arrival_time` | `72` |
| `simulation_params.transport_speed` | `5` |
| `simulation_params.max_cycles` | `3` |
| `workstations.Human.cycle_times` | `[48, 120, 48]` |
| `workstations.Robot_1.process_time` | `144` |
| `workstations.Robot_2.process_time` | `144` |

Detailed DES logic:

1. At startup, each palette is placed from `palette_template.initial_position`; following palettes are offset using `palette_template.initial_spacing`.
2. Palettes are launched one by one using `simulation_params.inter_arrival_time`, unless `--start-all-at-once` is used.
3. Each palette repeats `simulation_params.max_cycles` cycles.
4. On every cycle, the palette must go through `Human`. If Human is free and the Human queue is empty, it enters directly. Otherwise, it takes a slot in `HUMAN_QUEUE`.
5. Human processing times come from `workstations.Human.cycle_times`: cycle 1 = first value, cycle 2 = second value, cycle 3 = third value.
6. If this is not the final cycle, the palette moves toward the robot area through `HUMAN_TO_ROBOT_AREA`. The segment between `human_to_queue_p1` and `human_to_queue_p2` is recognized as `Lift_ToQueue`, so it uses the fixed duration `transfers.Lift_ToQueue.duration`.
7. On the robot side, if `Robot_1` or `Robot_2` is free and the robot queue is empty, the palette goes directly to the robot. Otherwise, it waits in `QUEUE_ROBOT_AREA`.
8. Robot selection is intentionally prioritized: `Robot_1` first, then `Robot_2`.
9. The palette passes through `entry_exit_robot*`, moves to `processing_robot*`, waits for `process_time`, then exits through `entry_exit_robot*`.
10. The palette returns to Human through `ROBOT_1_RETURN` or `ROBOT_2_RETURN`. The segment `robot_return_p1` -> `robot_return_p2` is recognized as `Lift_Return`, so it uses the fixed duration `transfers.Lift_Return.duration`.
11. Queues do not shift forward as soon as a palette reserves a resource. They shift only once the head palette has physically cleared the critical area. This is important to avoid visual overlaps.
12. At the end of the final Human cycle, the palette is considered complete and does not return to the robots.

This is the most important scenario for understanding the business logic: it simulates resources, queues, priorities, and timings, then turns the result into a USD animation.

## Scenario 2 - RealtimeTCP Live

Main files:

```text
scripts/RealtimeTCP/realtime_tcp_build_and_produce.py
scripts/RealtimeTCP/usd_composer_tcp_realtime_bridge.py
scripts/RealtimeTCP/tcp_client.py
scripts/RealtimeTCP/production_layout_realtime.json
scripts/RealtimeTCP/places.json
3d/RealtimeTCP/model.usd
```

Step 1: open in USD Composer:

```text
3d/RealtimeTCP/model.usd
```

Step 2: start the bridge in the USD Composer Script Editor:

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

Step 3: start the producer in PowerShell:

```powershell
cd $PROJECT_ROOT
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py
```

Useful options:

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

- `--realtime-factor 1.0` means `1` simulated second = `1` wall-clock second.
- `--realtime-factor 0.25` speeds up the live render: `1` simulated second takes `0.25` wall-clock seconds.
- `--no-live-tcp` tests the simulation without USD Composer.
- The producer mainly sends direct coordinates or TCP paths; `places.json` can remain empty.

CLI options:

| Option | Effect |
| --- | --- |
| `--config` | overrides the default JSON layout |
| `--event-log` | writes an NDJSON copy of generated or sent messages |
| `--live-tcp` | enables live TCP sending; this is the default behavior |
| `--no-live-tcp` | disables TCP and keeps the simulation in memory only |
| `--host` | Composer bridge host, default `127.0.0.1` |
| `--port` | Composer bridge port, default `5050` |
| `--realtime-factor` | wall-clock factor: `1.0` = real time, `0.25` = 4x faster |
| `--until` | simulation stop time in simulated seconds |
| `--start-all-at-once` | starts all palettes at `t=0` |

Current values in `production_layout_realtime.json`:

| Parameter | Current value |
| --- | --- |
| `simulation_params.num_palettes` | `10` |
| `simulation_params.inter_arrival_time` | `3` |
| `simulation_params.transport_speed` | `80` |
| `simulation_params.max_cycles` | `3` |
| `workstations.Human.cycle_times` | `[2, 5, 2]` |
| `workstations.Robot_1.process_time` | `6` |
| `workstations.Robot_2.process_time` | `6` |

Detailed RealtimeTCP logic:

1. `RealtimeTCP` uses almost the same business logic as `DES`: Human, Human queue, lift to robot queue, shared robot queue, `Robot_1` then `Robot_2` priority, and return to Human.
2. The main difference is the output: instead of writing a USD animation at the end, the script immediately sends movements to the TCP bridge inside USD Composer.
3. The Python script uses a real-time SimPy simulation when `--live-tcp` is enabled. `--realtime-factor` controls the relationship between simulated time and wall-clock time.
4. On startup, the producer sends seed messages to create/place palettes in Composer.
5. During simulation, each movement becomes a TCP JSON message: `set_position`, `move_linear`, or most often `move_path`.
6. Each message may include an `event_id` and `sim_time`; the bridge uses them to ignore stale or out-of-order messages.
7. The Composer bridge receives line-delimited JSON, creates `/World/Palettes/Palette_N` prims if needed, and interpolates their positions on each Composer frame.
8. The lifts remain exclusive logical resources: if capacity is `1`, only one palette can occupy the lift at a time.

In short: `DES` computes and exports, while `RealtimeTCP` computes and streams live. Use this scenario for a live demo of the DES logic.

## Scenario 3 - Simulogs Offline

Main files:

```text
scripts/Simulogs/01_build_from_logs.py
scripts/Simulogs/02_replay_logs.py
scripts/Simulogs/production_layout_simulogs.json
scripts/Simulogs/CSV/logs.csv
3d/layout/modelbuffer.usd
3d/layout/carrier.usd
```

Commands:

```powershell
cd $PROJECT_ROOT
python scripts\Simulogs\01_build_from_logs.py
python scripts\Simulogs\02_replay_logs.py
```

Outputs:

```text
3d/Simulogs/modelbuffer_build.usd
3d/Simulogs/modelbuffer_replay.usd
```

Then open `3d/Simulogs/modelbuffer_replay.usd` in USD Composer.

Expected CSV format:

```csv
carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details
```

CSV columns:

| Column | Description |
| --- | --- |
| `carrier_id` | numeric palette/carrier identifier |
| `origin_id` | source resource; can be empty for an initial spawn/appearance |
| `event_type` | event type: `TRANSPORT`, `QUEUE`, or `PROCESSING` |
| `destination_id` | target resource according to `resource_map` |
| `start_time` | start time; format `HH:MM:SS`, `HH:MM:SS.s`, or seconds |
| `processing_time` | declared duration; used as a fallback if `end_time` is missing or inconsistent |
| `end_time` | end time; if lower than `start_time`, the script recomputes it with `processing_time` |
| `task_id` | task or step identifier; used to sort/stabilize events |
| `details` | free-text field; kept for information but not heavily used by geometry |

Minimal example:

```csv
carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details
1,,TRANSPORT,1,00:00:00,0.0,00:00:00,1,spawn human
1,1,TRANSPORT,6,00:00:05,9.3,00:00:14,2,human to lift
1,6,TRANSPORT,5,00:00:14,3.0,00:00:17,3,lift to visual
1,5,TRANSPORT,2,00:00:17,5.2,00:00:22,4,visual to robot1
1,2,PROCESSING,2,00:00:22,6.0,00:00:28,5,robot1 process
```

Supported event types:

| Type | Visual effect |
| --- | --- |
| `TRANSPORT` | movement between resources |
| `QUEUE` | waiting in a buffer or queue |
| `PROCESSING` | hold or micro-move to the processing position |

Rows are sorted by `carrier_id`, `start_time`, `end_time`, `task_id`, and `event_type` before the offline animation is generated.

Detailed Simulogs logic:

1. `01_build_from_logs.py` reads every `carrier_id` from the CSV and creates one palette per carrier in `3d/Simulogs/modelbuffer_build.usd`.
2. `02_replay_logs.py` reads the CSV again, converts each row into a movement or hold, then writes keyframes into `3d/Simulogs/modelbuffer_replay.usd`.
3. `resource_map` converts CSV IDs into readable names: for example `1` -> `Human`, `2` -> `Robot_1`.
4. For a `TRANSPORT`, the script looks for an `origin->destination` route in `routes`. If `origin_id` is empty, the key is `START->destination`.
5. If a route crosses a segment declared in `transfers`, the transfer duration is enforced by the JSON. Example: the lift keeps `4.0` seconds even if the distance is short.
6. For a `QUEUE`, the script assigns a slot in `buffer_path`. Rank `0` is closest to processing; later ranks move backward in the queue.
7. For `PROCESSING`, the carrier moves toward `processing`, then remains visible until `end_time`.
8. `path_sample_step` adds intermediate points on long routes to make movement smoother.

## Scenario 4 - RealTimeTCPlogs Live

Main files:

```text
scripts/RealTimeTCPlogs/realtime_tcp_logs_live.py
scripts/RealTimeTCPlogs/usd_composer_tcp_logs_bridge.py
scripts/RealTimeTCPlogs/tcp_logs_client.py
scripts/RealTimeTCPlogs/realtimetcp_logs_config.json
scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
scripts/RealTimeTCPlogs/CSV/logs.csv
3d/RealTimeTCPlogs/modelbuffer.usd
```

Step 1: open in USD Composer:

```text
3d/RealTimeTCPlogs/modelbuffer.usd
```

Step 2: start the bridge in the USD Composer Script Editor:

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

Step 3: start the log reader in PowerShell.

To replay rows that are already present in the CSV:

```powershell
cd $PROJECT_ROOT
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --drain-existing --replay-timing
```

To follow only new rows added to the CSV:

```powershell
cd $PROJECT_ROOT
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py
```

Useful options:

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

CLI options:

| Option | Effect |
| --- | --- |
| `--config` | `realtimetcp_logs_config.json` file to use |
| `--layout` | forces a layout different from the one referenced in the config |
| `--logs` | forces a CSV different from the one referenced in the config |
| `--host` | Composer bridge host |
| `--port` | Composer bridge port |
| `--timeout` | TCP connection timeout |
| `--duration-scale` | multiplies movement durations sent to the bridge |
| `--poll-interval` | CSV polling frequency while waiting for new rows |
| `--drain-existing` | processes rows already present in the CSV |
| `--replay-timing` | respects CSV `start_time` values while draining existing rows |
| `--replay-scale` | multiplies waits between events during `--replay-timing` |
| `--idle-timeout` | stops the script after N seconds with no new rows |
| `--max-events` | stops after N processed rows |
| `--dry-run` | does not connect to the TCP bridge |
| `--print-messages` | prints outgoing JSON messages |
| `--audit-log` | writes an NDJSON copy of sent messages |

Important behavior:

- Without `--drain-existing`, the script seeks to the end of the CSV and waits for new rows.
- With `--drain-existing`, it processes rows that are already present.
- With `--replay-timing`, it respects CSV `start_time` values.
- `--replay-scale 0.25` speeds up the wait between existing rows.
- The bridge keeps a movement queue per carrier: a new movement does not overwrite the active movement for the same carrier.

Live CSV:

- The format is the same as for `Simulogs`: `carrier_id,origin_id,event_type,destination_id,start_time,processing_time,end_time,task_id,details`.
- In normal live mode, the script does not replay history: it waits for rows added after it starts.
- For a real external source, append CSV rows with the header already present and fields in the same order.
- `TRANSPORT` rows are temporarily held per carrier to inspect the next event. This tells the script whether the transport should arrive directly at processing or only at the queue entry.
- `QUEUE` rows place the carrier into a buffer slot.
- `PROCESSING` rows remove the carrier from the logical queue and move it toward the `processing` marker.

Detailed RealTimeTCPlogs logic:

1. `realtime_tcp_logs_live.py` reads `realtimetcp_logs_config.json`.
2. The config points to a CSV, a layout, and the expected Composer stage.
3. The layout converts CSV IDs into resources and routes into marker paths.
4. For each processed row, the script creates a JSON message: `set_position`, `set_visibility`, `move_path`, or `move_timed_path`.
5. The Composer bridge receives messages on `127.0.0.1:5051` and creates carriers under `/World/RealTimeTCPlogs/Carriers/Carrier_N`.
6. Unlike the `RealtimeTCP` bridge, this bridge keeps a message queue per carrier. If a carrier is already moving, the next movement waits its turn.
7. `move_timed_path` preserves segment durations, which is useful for keeping fixed-duration lifts while respecting CSV timings.

Direct self-test in USD Composer:

```python
import RealTimeTCPlogs.usd_composer_tcp_logs_bridge as rtlogs
rtlogs.bridge_self_test(carrier_id=999, duration=8.0)
```

## Auto Bridge Extensions

Two local Omniverse extensions can automatically start the bridges if they are added to the USD Composer extension search path:

```text
scripts/RealtimeTCP/omni.realtimetcp.autobridge
scripts/RealTimeTCPlogs/omni.realtimetcplogs.autobridge
```

Default settings:

```text
omni.realtimetcp.autobridge       -> 127.0.0.1:5050
omni.realtimetcplogs.autobridge   -> 127.0.0.1:5051
```

These extensions are useful when you do not want to paste snippets into the Script Editor. When in doubt, use the manual snippets: they are explicit and let you inspect `bridge_status()`.

## Editable Parameters

### DES / RealtimeTCP Layouts

Files:

```text
scripts/DES/production_layout.json
scripts/RealtimeTCP/production_layout_realtime.json
```

Important fields:

| Field | Role |
| --- | --- |
| `workstations.Human.cycle_times` | Human cycle durations |
| `workstations.Robot_*.process_time` | robot processing duration |
| `workstations.*.entry` | workstation entry position |
| `workstations.*.processing` | processing position |
| `workstations.*.exit` | exit position |
| `transfers.*.duration` | fixed transfer duration, for example a lift |
| `transfers.*.capacity` | logical transfer capacity |
| `transfers.*.from` / `to` | endpoints of a fixed-duration transfer |
| `conveyor_segments.*.waypoints` | path followed by palettes |
| `conveyor_segments.*.capacity` | logical segment capacity |
| `conveyor_segments.*.slot_spacing` | spacing between palettes in a queue |
| `conveyor_segments.*.is_queue_zone` | enables queue-style placement |
| `conveyor_segments.*.extend_after_end` | allows slots after the final waypoint |
| `palette_template.asset_path` | USD asset used for palettes |
| `palette_template.initial_position` | initial position |
| `palette_template.initial_spacing` | initial spacing between palettes |
| `palette_template.scale` | carrier scale |
| `simulation_params.num_palettes` | number of palettes |
| `simulation_params.inter_arrival_time` | delay between palette launches |
| `simulation_params.transport_speed` | speed for non-fixed transfers |
| `simulation_params.max_cycles` | number of cycles per palette |
| `simulation_params.timeline_fps` | FPS for the offline USD timeline |
| `marker_stage` | USD scene containing the markers |

Warning: the current DES logic is coded for `Human`, `Robot_1`, and `Robot_2`. Adding `Robot_3` to DES is not only a JSON change; the robot selection code and return segments must also be updated.

Precise DES / RealtimeTCP parameter reference:

| Parameter | Type | Explanation |
| --- | --- | --- |
| `workstations` | object | list of logical workstations known by the simulation |
| `workstations.Human.entry` | marker or coordinates | point where the palette enters the Human workstation |
| `workstations.Human.buffer` | marker or coordinates | Human buffer point; in this DES it is the same as the Human marker |
| `workstations.Human.processing` | marker or coordinates | point where the palette stays during Human processing |
| `workstations.Human.exit` | marker or coordinates | Human exit point |
| `workstations.Human.cycle_times` | list of numbers | Human processing duration per cycle; must cover `max_cycles` |
| `workstations.Robot_1.entry` | marker or coordinates | Robot_1 entry point |
| `workstations.Robot_1.processing` | marker or coordinates | Robot_1 processing point |
| `workstations.Robot_1.exit` | marker or coordinates | Robot_1 exit point |
| `workstations.Robot_1.process_time` | number | Robot_1 processing duration |
| `workstations.Robot_2.*` | same as Robot_1 | same fields for Robot_2 |
| `transfers` | object | segments with fixed duration and their own capacity |
| `transfers.Lift_ToQueue.duration` | number | enforced time for the Human -> robot queue lift |
| `transfers.Lift_ToQueue.capacity` | integer | number of palettes allowed simultaneously in this lift |
| `transfers.Lift_ToQueue.from` | marker or coordinates | start of the segment recognized as the lift |
| `transfers.Lift_ToQueue.to` | marker or coordinates | end of the segment recognized as the lift |
| `transfers.Lift_Return.*` | same pattern | robot -> Human return lift |
| `conveyor_segments` | object | logical paths followed by palettes |
| `conveyor_segments.START_TO_HUMAN.waypoints` | list | initial path to Human; here a single marker |
| `conveyor_segments.*.capacity` | integer | number of palettes admitted on the segment |
| `conveyor_segments.*.slot_spacing` | number | distance between two palettes when they occupy slots |
| `conveyor_segments.*.is_queue_zone` | boolean | if `true`, slots are distributed between the first and last waypoint |
| `conveyor_segments.*.extend_after_end` | boolean | if `true`, slots may continue after the last waypoint |
| `palette_template.prototype_path` | USD path | hidden prototype prim referencing the palette asset |
| `palette_template.instance_prefix` | USD path | prefix used to create `/World/Palettes/Palette_1`, etc. |
| `palette_template.asset_path` | file path | USD asset referenced by each palette |
| `palette_template.initial_position` | marker or coordinates | starting position of the first palette |
| `palette_template.initial_spacing` | number | offset between palettes at startup |
| `palette_template.scale` | list `[x,y,z]` | scale applied to the carrier |
| `simulation_params.num_palettes` | integer | number of palettes created and simulated |
| `simulation_params.inter_arrival_time` | number | delay between two palette launches |
| `simulation_params.transport_speed` | number | movement speed outside fixed transfers |
| `simulation_params.max_cycles` | integer | number of Human/Robot cycles per palette |
| `simulation_params.timeline_fps` | number | FPS used for offline USD keyframes; keep `24` unless there is a specific need |
| `marker_stage` | file path | source USD file from which `marker_layout.py` reads markers |

### Log Layouts

Files:

```text
scripts/Simulogs/production_layout_simulogs.json
scripts/RealTimeTCPlogs/realtimetcp_logs_layout.json
```

Important fields:

| Field | Role |
| --- | --- |
| `resource_map` | CSV ID -> resource name mapping |
| `workstations.*.entry` | resource entry position |
| `workstations.*.processing` | processing position |
| `workstations.*.exit` | resource exit position |
| `workstations.*.buffer` | main buffer position |
| `workstations.*.buffer_path` | queue/buffer slots |
| `workstations.*.entry_to_buffer` | entry -> buffer path |
| `workstations.*.buffer_to_processing` | buffer -> processing path |
| `workstations.*.processing_to_exit` | processing -> exit path |
| `routes` | global routes between resources, for example `1->6` |
| `transfers` | fixed-duration segments, for example lifts |
| `palette_template` | prototype, prefix, initial position, scale, asset |
| `simulation_params.path_sample_step` | density of intermediate points |
| `simulation_params.max_keys_per_motion` | point limit per movement |
| `simulation_params.micro_move_seconds` | minimum duration for small visual movements |
| `marker_stage` | USD scene containing the markers |

To add a log route, add or modify a key in `routes`, for example:

```json
"2->7": [
  "marker:entry_exit_robot1",
  "marker:robot_to_lift2_p1",
  "marker:lift2"
]
```

Precise log parameter reference:

| Parameter | Type | Explanation |
| --- | --- | --- |
| `resource_map` | object | maps CSV IDs to names used in `workstations` |
| `transfers` | object | fixed-duration segments detected inside routes |
| `transfers.*.duration` | number | enforced duration for this segment |
| `transfers.*.capacity` | integer | documentary/logical value; mostly useful for consistency with DES |
| `transfers.*.from` | marker or coordinates | start point of the fixed segment |
| `transfers.*.to` | marker or coordinates | end point of the fixed segment |
| `workstations.*.entry` | marker or coordinates | arrival position from a global route |
| `workstations.*.processing` | marker or coordinates | processing position |
| `workstations.*.exit` | marker or coordinates | departure position toward a global route |
| `workstations.*.entry_to_processing` | list | local entry -> processing path |
| `workstations.*.processing_to_exit` | list | local processing -> exit path |
| `workstations.*.buffer` | marker or coordinates | main buffer position |
| `workstations.*.entry_to_buffer` | list | local entry -> queue path |
| `workstations.*.buffer_path` | list | queue slots; the last slot is closest to processing |
| `workstations.*.buffer_to_processing` | list | local queue -> processing path |
| `workstations.*.processing_to_buffer` | list | local processing -> queue return path, useful for some logs |
| `routes.START->1` | list | route used when `origin_id` is empty and `destination_id=1` |
| `routes.A->B` | list | global route between two CSV IDs |
| `palette_template.prototype_path` | USD path | hidden carrier prototype |
| `palette_template.instance_prefix` | USD path | prefix for offline instances `/World/Palettes/Palette_N` |
| `palette_template.initial_position` | marker or coordinates | starting position before the first event |
| `palette_template.scale` | list `[x,y,z]` | scale applied to the carrier |
| `palette_template.asset_path` | file path | carrier USD asset |
| `simulation_params.timeline_fps` | number | FPS for the offline Simulogs replay |
| `simulation_params.path_sample_step` | number | distance between intermediate points on long routes |
| `simulation_params.max_keys_per_motion` | integer | point/keyframe limit to avoid overly heavy files |
| `simulation_params.queue_slots_per_station` | integer | documentary parameter here; actual slots come from `buffer_path` |
| `simulation_params.micro_move_seconds` | number | minimum duration used to make small movements visible |
| `marker_stage` | file path | USD scene containing the layout markers |

### RealTimeTCPlogs Config

File:

```text
scripts/RealTimeTCPlogs/realtimetcp_logs_config.json
```

Fields:

| Field | Role |
| --- | --- |
| `tcp.host` | USD Composer bridge host |
| `tcp.port` | USD Composer bridge port |
| `tcp.timeout` | connection timeout |
| `logs.path` | CSV followed live |
| `logs.poll_interval` | CSV polling frequency |
| `runtime.duration_scale` | factor applied to durations sent to the bridge |
| `composer_stage` | scene to open in USD Composer |
| `layout` | layout used to convert logs into trajectories |

## Common Changes

Change the number of DES or RealtimeTCP palettes:

```json
"simulation_params": {
  "num_palettes": 10
}
```

Change processing times:

```json
"Human": { "cycle_times": [48, 120, 48] }
"Robot_1": { "process_time": 144 }
```

Change transport speed:

```json
"transport_speed": 5
```

Change a path:

```json
"waypoints": [
  "marker:human",
  "marker:human_to_queue_p1",
  "marker:human_to_queue_p2",
  "marker:start_robot_queue"
]
```

Change a TCP port:

1. Change the port in the Composer snippet or in the extension.
2. Start the producer with the same port:

```powershell
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --port 5052
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --port 5053
```

Replace the palette asset:

```json
"palette_template": {
  "asset_path": "3d/layout/carrier.usd",
  "scale": [0.15, 0.15, 0.15]
}
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'pxr'`

The Python environment does not contain OpenUSD. Use the USD Composer / Omniverse Python environment, or another environment that exposes `pxr`.

### `ModuleNotFoundError: No module named 'simpy'`

Install `simpy` in the Python environment being used:

```powershell
python -m pip install simpy
```

### Nothing Moves In RealtimeTCP

- Check that `3d/RealtimeTCP/model.usd` is open in USD Composer.
- Check that the Composer bridge is listening on `127.0.0.1:5050`.
- In Composer, run `print(rt.bridge_status())`.
- In PowerShell, test without TCP:

```powershell
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --no-live-tcp --until 30
```

### Nothing Moves In RealTimeTCPlogs

- Check that `3d/RealTimeTCPlogs/modelbuffer.usd` is open.
- Check that the bridge is listening on `127.0.0.1:5051`.
- To test messages without TCP:

```powershell
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --dry-run --print-messages --max-events 10 --drain-existing
```

- To test the bridge alone in Composer:

```python
rtlogs.bridge_self_test(carrier_id=999, duration=8.0)
```

### RealTimeTCPlogs Looks Stuck

This is normal if `--drain-existing` is not used: the script waits for new rows appended to the CSV. To replay the existing file:

```powershell
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --drain-existing --replay-timing
```

### Marker Not Found

- Open the file referenced by `marker_stage`.
- Check that the `Markers` prim exists.
- Check the exact name after `marker:`.
- Save the USD scene after making changes.

### Port Already In Use

An old bridge may still be running. In the Script Editor:

```python
rt.stop_tcp_bridge()
rtlogs.stop_tcp_bridge()
```

Then restart the bridge, or choose another port on both the Composer side and the PowerShell side.

### Palettes Overlap

- Check `capacity`, `slot_spacing`, `is_queue_zone`, and `extend_after_end`.
- Check that queue markers are ordered correctly.
- Check that lifts keep capacity `1` if the system must remain exclusive.

## Handover Verification

Run at least:

```powershell
cd $PROJECT_ROOT
python -m compileall -q scripts\DES scripts\RealtimeTCP scripts\Simulogs scripts\RealTimeTCPlogs
```

Then verify the four workflows:

```powershell
python scripts\DES\USD_FINAL_build.py
python scripts\DES\USD_FINAL_simulation.py --until 300
python scripts\Simulogs\01_build_from_logs.py
python scripts\Simulogs\02_replay_logs.py
python scripts\RealtimeTCP\realtime_tcp_build_and_produce.py --no-live-tcp --until 30
python scripts\RealTimeTCPlogs\realtime_tcp_logs_live.py --dry-run --print-messages --drain-existing --max-events 10
```

If the folder is tracked by Git:

```powershell
git status
```

The current local folder may not always contain `.git`; in that case, `git status` may report that it is not a Git repository.

## Checklist For The Next Person

- Read the "Quick Start" section.
- Check `simpy` and `pxr`.
- Open the correct USD scene for the chosen scenario.
- For live mode, start the Composer bridge before starting the PowerShell script.
- Change positions in USD markers, not directly in the code.
- Change times, capacities, routes, and palette counts in the JSON files.
- Keep Composer and PowerShell TCP ports identical.
- Do not version generated outputs, caches, temporary logs, or `.venv/`.
