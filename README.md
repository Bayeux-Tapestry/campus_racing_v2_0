# Campus Racing 2.0 — Spa / Ferrari F2004 Arcade

This build replaces the earlier prototype with a state-driven arcade system for **original/vanilla Assetto Corsa**.

## What it does

- Full-screen attract/QR screen on the rig.
- Student registration using student ID, stored as an HMAC-derived identity key rather than the raw ID. Staff can register with an identifier/name.
- Queue and PIN-protected Race Control.
- Dedicated `/leaderboard`, `/live`, `/results`, `/join`, and `/admin` screens.
- Spa + `ks_ferrari_f2004` session preparation using the existing vanilla `race.ini` as the base.
- Starts `acs.exe` with the Assetto Corsa install directory as its working directory and creates `steam_appid.txt` if absent.
- Rig Agent reads original AC shared memory and uploads completed laps.
- Lap 1 = out lap, lap 2 = competitive hot lap, lap 3 = in lap. Only lap 2 can enter the leaderboard.
- After lap 3, `acs.exe` is force-closed and the already-running kiosk becomes visible again.
- Best-effort automatic Enter key to get through vanilla AC's Drive screen, plus a manual **PRESS DRIVE** recovery control in Race Control.
- ESP32 result mirror retained.
- Database/API are keyed by `rig_id` so a second rig can be added later.

## First setup

1. Extract the folder somewhere writable, e.g. `C:\CampusRacing`.
2. Install Python 3.11+ and make sure the `py` launcher works.
3. Start vanilla Assetto Corsa normally and run **one normal session**. Exit AC. This creates a known-good `Documents\Assetto Corsa\cfg\race.ini` that Campus Racing patches rather than trying to invent every AC setting.
4. Open `config.json` and verify `ac_root` and `ac_exe` match your Steam install.
5. Change `student_hmac_secret`, `admin_pin`, and `esp32_shared_key`.
6. Double-click `start_arcade.bat`.

## URLs

- Arcade / QR: `http://127.0.0.1:8000/`
- Race Control: `http://127.0.0.1:8000/admin`
- Leaderboard: `http://127.0.0.1:8000/leaderboard`
- Live timing: `http://127.0.0.1:8000/live`
- Latest result: `http://127.0.0.1:8000/results`
- Network/QR diagnostic: `http://127.0.0.1:8000/api/network`
- Full state diagnostic: `http://127.0.0.1:8000/api/state`

For phones, the QR uses the rig's LAN IPv4. If automatic adapter selection is wrong, set `public_base_url` in `config.json`, e.g. `http://10.20.30.45:8000`.

## Test sequence

1. Start Campus Racing.
2. Register a test driver from `/join`.
3. Open Race Control and press START RIG-01.
4. Campus Racing patches the existing race.ini to Spa/F2004 and launches `acs.exe`.
5. The agent attempts to press Enter on the vanilla AC pre-drive screen after 8 seconds. If the car remains on Drive/Setup/Exit, click **PRESS DRIVE** in Race Control once. This is intentionally exposed because vanilla AC does not provide a documented external API to click that menu.
6. Drive three completed laps. Watch the Rig Agent console: it should print each completed lap.
7. Lap 2 is stored as the competitive time and mirrored to the ESP32.
8. At completed lap 3 the agent kills `acs.exe`, marks the session ended and the kiosk/QR screen returns.

## Important vanilla AC limitation

`race.ini` + `acs.exe` reliably describes/starts the prepared simulator session, but vanilla AC can still present its in-game **Drive / Setup / Exit** screen. Campus Racing 2.0 uses a Windows foreground + Enter automation and provides a Race Control fallback. It does not use Content Manager or CSP.

## College network

The web server listens on `0.0.0.0:8000`. Windows Firewall and the college VLAN/SSID must permit phone-to-rig TCP/8000 traffic. If the college wireless network uses client isolation, no QR-code software change can make the phone reach the laptop directly; use an approved rig VLAN/SSID, local AP/hotspot, or the future central server.

## Second rig later

Copy the Rig Agent/config to Rig 2 and give it `"rig_id":"RIG-02"`. The current UI is prepared around rig IDs, but the local V2.0 server still launches the game on its own Windows machine. When you move to the central server, game launch becomes an agent command instead of a server-local process call.
