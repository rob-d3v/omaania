-- omaania: Hyprland window rules for Ania Player (unofficial community plugin).
--
-- Installed by `omaania setup` as ~/.config/hypr/omaania.lua and loaded by ONE
-- line in ~/.config/hypr/hyprland.lua:  pcall(require, "hypr.omaania")
-- Delete this file (and that line) to undo; `omaania uninstall` does both.
--
-- The player runs under XWayland (its launcher forces QT_QPA_PLATFORM=xcb): it
-- positions and drags its own avatar window and cuts the click region with the
-- X11 SHAPE extension. The avatar window is titled "Ania Player", the chat
-- "Ania Player Chat". Settings dialogs keep their own titles and stay normal
-- floating windows.

local player = "^(aniaplayer|AniaPlayer|run_ania_player\\.py)$"

local overlay = {
  tag = "-default-opacity",
  float = true,
  pin = true,              -- on every workspace
  -- No no_focus: on Hyprland it cuts the pointer from the XWayland window.
  no_initial_focus = true,
  border_size = 0,
  rounding = 0,
  no_shadow = true,
  no_blur = true,
  no_anim = true,
  no_dim = true,
  opacity = "1 1",
  suppress_event = "fullscreen maximize activate activatefocus",
}

-- The avatar: bottom-right corner the first time; afterwards the player
-- restores wherever you dragged it.
local avatar = {}
for k, v in pairs(overlay) do avatar[k] = v end
avatar.move = { "(monitor_w-window_w-40)", "(monitor_h-window_h-40-monitor_h*0.1)" }
pcall(o.window, { class = player, title = "^Ania Player$" }, avatar)

-- The chat bubbles: same overlay look, positioned by the player itself.
-- "aniaplayer" is the title older players gave the chat window.
pcall(o.window, { class = player, title = "^(Ania Player Chat|aniaplayer)$" }, overlay)

-- The player's settings windows are Tk toplevels: float them centred instead
-- of tiling them next to your work.
pcall(o.window, { class = "^(Toplevel)$" }, { float = true, center = true })
