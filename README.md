# omaania

**A talking avatar on your Omarchy desktop that answers with your own AI agent.**

omaania installs and controls [Ania Player](https://aniamodels.shop): an
animated avatar that floats over your desktop, listens when you press
`ctrl+shift+space` (or say a wake word you already have, such as “Ok Ania”),
sends what you say to your Omarchy default agent (Codex, Claude Code,
OpenCode, …) and speaks the answer with lip-sync. A bar widget in the native
Omarchy style shows its state and holds the whole menu.

> A free “Hey Omarchy” wake word is coming soon: the model is still training
> and can't be downloaded yet. Until then, use the shortcut or your own wake
> word (works today).
>
> **[Help train “Hey Omarchy” — donate your voice (2 min)](https://aniamodels.shop/omarchy-voice)**

> **Unofficial community plugin, not affiliated with Omarchy or 37signals.**

<!-- DEMO: replace with a 30 s GIF (docs/demo.gif) -->
_Demo GIF coming soon._

- Near-zero configuration: one click on **Finish setup**, sensible defaults,
  nothing to edit by hand.
- No sudo, no package manager, no root. Everything lives in your home folder
  and `omaania uninstall` removes exactly what setup added.
- Your agent answers by default; bring your own OpenAI-compatible API key if
  you prefer.
- Biometric unlock and the spoken briefing are **off** unless you turn them on.
- English first.

## Install

```bash
omarchy plugin add https://github.com/rob-d3v/omaania --enable
```

Click the avatar icon in the bar and press **Finish setup**. Setup runs in a
terminal; you can run it again any time:

```bash
~/.config/omarchy/plugins/io.github.rob-d3v.omaania/bin/omaania setup
```

Setup checks each step and only acts when something is missing:

1. **Ania Player.** Looks up the latest release of
   [rob-d3v/ania-player](https://github.com/rob-d3v/ania-player), downloads
   `AniaPlayerSetup.deb`, checks its sha256 against the release's
   `SHA256SUMS.txt` (falling back to the digest GitHub publishes for the
   asset), and unpacks it with `bsdtar` into `~/.local/opt/ania-player`. If a
   release ever publishes no checksum, setup prints the sha256 it computed so
   you can compare it with the release page. If you already have Ania Player
   installed some other way, setup uses it and leaves it alone: its
   launcher, its service, its settings (step 5) and, when you already have
   window rules for it, its Hyprland rules (step 3).
2. **Launcher.** Writes `~/.local/bin/aniaplayer` (the package's launcher,
   pointed at `~/.local/opt`), an app menu entry and the icon, and links
   `~/.local/bin/omaania`.
3. **Hyprland rules (asks first, default yes).** Writes `~/.config/hypr/omaania.lua` (borderless,
   pinned overlay for the avatar and its chat; settings windows float) and
   adds one line to `~/.config/hypr/hyprland.lua`:
   `pcall(require, "hypr.omaania")`. Omarchy has no user drop-in folder for
   Hyprland rules, so this one line is the only edit to your own files.
   Setup asks before making it (Enter = yes; `--yes` answers yes and prints
   the question). Say no, or pass `--no-hypr`, and your Hyprland files stay
   untouched.
4. **Wake word “Hey Omarchy” (coming soon).** Once the model is published, reuses the bundle from
   [omawake](https://github.com/rob-d3v/omawake) when it is installed,
   otherwise downloads it (pinned sha256) into
   `~/.local/share/aniaplayer/wakeword/`, which omawake also reads.
   When omawake is installed, setup asks which of the two answers the wake
   word (default: the avatar). omawake skips any word the running player
   listens for, so one phrase never wakes both; `--no-wake` leaves the word
   to omawake.
5. **Voice assistant defaults.** Asks who answers: your Omarchy default agent
   (default) or your own API key. Fills only the *missing* keys of the
   player's config, never overwriting a value you set.
6. **Default avatar.** Downloads “Glyph”, a free retro terminal companion
   (sha256-checked, ~94 MB), and makes it the startup avatar only if you have
   not chosen one. It is also free on the Ania marketplace.
7. **Background service.** Installs `aniaplayer.service` (systemd user unit)
   and turns autostart on (`--no-autostart` to skip). An `aniaplayer.service`
   you wrote yourself is left untouched.
8. **Ania tools for your agent (optional, asks first).** Runs
   `npx -y ania-mcp@0.1.2 install <your agent>` so your agent can create and
   switch avatars. Supported today: Codex (`[mcp_servers.ania]` in
   `~/.codex/config.toml`, backed up first; sign in with
   `codex mcp login ania`), Claude Code (runs
   `claude mcp add --transport http --scope user ania …`), OpenCode, Gemini
   CLI, Cursor; for other agents setup prints the MCP URL to add by hand.

Non-interactive flags: `--yes`, `--brain omarchy-agent|own-key`,
`--api-base`, `--api-model` (the key comes from the prompt or the
`OMAANIA_API_KEY` variable, never the command line), `--no-hypr`,
`--no-wake`, `--no-service`, `--no-autostart`, `--no-start`, `--mcp` /
`--no-mcp`, `--update` (re-download), and `--deb FILE --sums SHA256SUMS.txt`
(or `--sha256 HEX`) for an offline install.

### Defaults

| Setting | Default | Player config key |
|---|---|---|
| Wake word | `ctrl+shift+space` today; “Hey Omarchy” once the free model is published (coming soon) | `wake_word.model_name`, `wake_word.wake_word_enabled` |
| Conversation | keeps listening until you say “that's all” / “goodbye”, or 30 s of silence | `agent.conversation_mode = "until_dismissed"` |
| Brain | your Omarchy default agent | `agent.provider = "omarchy-agent"` |
| Brain (option) | your own OpenAI-compatible key, stored `0600` in `~/.config/aniaplayer/omaania-api.key` | `agent.provider = "openai"`, `agent.api_key_file` |
| Chat colours | follow your Omarchy theme | `chat.theme = "auto"` |
| Voice | English | `tts.voice_locale = "en-US"`, `stt.language = "en"` |
| Biometric unlock | off | biometria `unlock_enabled` |
| Briefing | off | biometria `briefing_enabled` |

Some of these need a newer Ania Player than 1.2.47 (see
[Player versions](#player-versions)); setup saves them anyway and an older
player simply ignores keys it does not know.

### Requirements

| What | Why | Shipped by Omarchy? |
|---|---|---|
| Omarchy 4 (Lua Hyprland config) | shell plugin + window rules | yes |
| `python3` ≥ 3.11 (stdlib only) | the `omaania` CLI | yes |
| `bsdtar` (libarchive) | unpacks the .deb | yes |
| `systemd --user`, `journalctl` | background service, logs | yes |
| An Omarchy default agent | the default brain | `omarchy default agent <name>` |
| Node.js `npx` | only for the optional Ania MCP tools | no (optional) |
| ~460 MB disk | the unpacked player (1.2.47) | |

## The bar widget

| Icon | State |
|---|---|
| smile | avatar shown (dimmed: player not running) |
| eye-slash | avatar hidden |
| microphone (pulsing) | listening |
| speaker (pulsing) | speaking |
| lock | position locked |
| gear | setup not finished |

**Click** shows or hides the avatar (starts the player when it is closed).
**Right click** opens the menu:

| Item | Runs |
|---|---|
| Show / Hide | `aniaplayer show` / `hide` |
| Lock / Unlock position | `aniaplayer block` / `unblock` (no dragging, clicks pass through) |
| Lock all / Unlock all | `aniaplayer block --all` / `unblock --all` |
| Change avatar… | lists your `.ania` files, then `aniaplayer open <file>` |
| Marketplace (free avatars) | opens aniamodels.shop/marketplace?category=free |
| Get credits | opens your wallet, aniamodels.shop/reports?tab=wallet |
| Create avatar with your AI | opens aniamodels.shop/connect-ai (MCP how-to) |
| Create wake word | opens aniamodels.shop/create-wakeword |
| Briefing on/off | needs a player update (no CLI verb yet) |
| Edit briefing… | `aniaplayer biometria briefing editar` (newer player) |
| Biometric unlock on/off | `aniaplayer biometria ligar` / `desligar`; first time opens the enrolment window |
| Settings | `aniaplayer settings voice` |
| Logs | `journalctl --user -u aniaplayer -f` in a terminal |

The same from a terminal:

```bash
omaania status [--json] | doctor
omaania show | hide | toggle | start | quit
omaania lock [--all] | unlock [--all]
omaania avatars | avatar <file.ania>
omaania settings [voice|avatar|plugins|hotkeys|startup]
omaania open marketplace|credits|create-avatar|create-wakeword
omaania biometric on|off|setup|status
omaania briefing edit|preview
omaania logs [-f | --open]
```

## Biometric unlock (opt-in, local)

Off by default and never turned on by setup. When you switch it on, Ania
Player's own window asks for consent and enrols your face. What it keeps is a
128-number embedding (not a photo) in `~/.local/share/aniaplayer/biometria/`
with `0600` permissions, for your user only. Nothing is uploaded. Switch it
off from the menu, or delete the enrolment with
`aniaplayer biometria apagar --sim`.

## Player versions

omaania reads what the installed player can do from the files the .deb
ships and only relies on what is there (`omaania doctor` lists it).

| Feature | Ania Player 1.2.47 (current release) | Next release |
|---|---|---|
| Install, show/hide, lock, avatars, settings, logs | yes | yes |
| Biometric unlock on/off | yes | yes |
| Brain = Omarchy default agent | no (the player keeps its own brain setting) | yes |
| Conversation until dismissed | no (5 s follow-up window) | yes |
| Chat in Omarchy theme colours | no | yes |
| Edit briefing | no | yes |
| Briefing on/off from the bar | no | needs a CLI verb |

## Security

- Downloads only over HTTPS. The player .deb is checked against the
  release's `SHA256SUMS.txt` before anything is unpacked; wake word bundles
  and avatars need a pinned sha256 in [`models.json`](models.json).
- Nothing downloaded is executed during setup. The .deb is unpacked with
  `bsdtar` (no dpkg, no maintainer scripts, no root).
- No sudo, no `pkexec`, no package manager, no edits outside your home.
- An API key you enter is read from the prompt (or `OMAANIA_API_KEY`), never
  from argv, and stored `0600`.
- `npx -y ania-mcp@0.1.2` runs only if you say yes, pinned to that version.
- Every file setup creates is listed in `~/.local/state/omaania/installed.json`.

## Privacy

- Wake word detection runs on your machine. What you say after it goes to the
  brain you chose: your local agent CLI (and whatever service that agent
  uses), or the API endpoint you configured.
- omaania itself sends nothing anywhere. Its only network use is the GitHub
  release lookup and downloads during setup.

## Troubleshooting

| Symptom | Try |
|---|---|
| The icon shows a gear | Setup isn't finished: click it, or run `omaania setup` |
| Icon is dimmed | The player isn't running: click it, or `systemctl --user start aniaplayer` |
| The avatar has a frame or tiles | `omaania doctor` (rules file and the `hypr.omaania` line), then `hyprctl reload` |
| Two avatars appear at login | Remove `~/.config/autostart/aniaplayer.desktop` (the service already starts it) |
| One phrase wakes both the avatar and omawake | Give them different wake words (in omawake: `omawake wake <id>`) |
| It doesn't wake on “Hey Omarchy” | The model isn't published yet (coming soon); use `ctrl+shift+space` or your own wake word |
| Anything else | `omaania doctor`, `omaania logs --open` |

## Uninstall

```bash
omaania uninstall                                  # player, launcher, rules, unit, added config keys
omaania uninstall --purge                          # also the player's own settings, avatars and voices
omarchy plugin remove io.github.rob-d3v.omaania    # the bar widget
```

`omaania uninstall` asks before it deletes Ania Player's own settings and
downloads. An Ania Player you installed yourself is never removed. If you
added the Ania MCP tools, remove the `ania` server from your agent's config.

## Development

```bash
git clone https://github.com/rob-d3v/omaania && cd omaania
PYTHONPATH=src:tests python3 -m unittest discover -s tests   # scratch HOME, fake .deb
omarchy plugin validate .
```

Tests run setup and uninstall in a temporary HOME with `OMAANIA_SANDBOX=1`,
which turns off every `systemctl` and `hyprctl` call.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Omarchy is a trademark of its owner. This project is unofficial and is not
affiliated with or endorsed by Omarchy or 37signals.
