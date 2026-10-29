import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// omaania bar widget (unofficial community plugin).
//
// Shows Ania Player's state and runs the plugin's own `bin/omaania` CLI for
// every action; that CLI calls real `aniaplayer` verbs. Left click shows or
// hides the avatar (starts the player when it is closed, opens setup when it
// is not finished); right click opens the menu.
Panel {
  id: root
  moduleName: "io.github.rob-d3v.omaania"
  ipcTarget: "io.github.rob-d3v.omaania"

  readonly property string cli: decodeURIComponent(String(Qt.resolvedUrl("bin/omaania")).replace(/^file:\/\//, ""))

  property var info: ({})
  property var avatars: []
  property bool avatarsOpen: false
  readonly property string st: String(info.state || "stopped")
  readonly property bool setupOk: info.setup_ok === true
  readonly property bool runningNow: info.running === true
  readonly property bool hot: st === "listening" || st === "speaking"
  readonly property var feats: info.features || ({})
  readonly property var bio: info.biometric || ({})

  function glyph() {
    if (st === "setup") return ""        // gear
    if (st === "listening") return ""    // microphone
    if (st === "speaking") return ""     // volume up
    if (st === "locked") return ""       // lock
    if (st === "hidden") return ""       // eye slash
    return ""                            // smile: shown / stopped (dimmed)
  }

  function label() {
    switch (st) {
    case "setup": return "Setup needed"
    case "stopped": return "Not running"
    case "listening": return "Listening…"
    case "speaking": return "Speaking…"
    case "locked": return "Position locked"
    case "hidden": return "Hidden"
    case "shown": return "Shown"
    }
    return st
  }

  function run(args) {
    actionProc.command = [root.cli].concat(args)
    actionProc.running = true
  }

  function detached(args) {
    Quickshell.execDetached([root.cli].concat(args))
    root.close()
  }

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  function primary() {
    if (!setupOk) Quickshell.execDetached([root.cli, "open-setup"])
    else if (!runningNow) run(["start"])
    else run(["toggle"])
  }

  onOpenedChanged: {
    if (opened) {
      refresh()
      if (!avatarsProc.running) avatarsProc.running = true
    } else {
      avatarsOpen = false
    }
  }

  Process {
    id: statusProc
    command: [root.cli, "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try { root.info = JSON.parse(text) } catch (e) {}
      }
    }
  }

  Process {
    id: avatarsProc
    command: [root.cli, "avatars", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try { root.avatars = JSON.parse(text).avatars || [] } catch (e) {}
      }
    }
  }

  Process {
    id: actionProc
    onExited: root.refresh()
  }

  Timer {
    interval: root.opened || root.hot ? 2000 : 6000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.glyph()
    active: root.hot
    dimmed: root.st === "hidden" || root.st === "stopped"
    foreground: root.bar ? root.bar.barForeground : Commons.Color.foreground
    tooltipText: "Ania: " + root.label() + (root.info.avatar ? " (" + root.info.avatar + ")" : "")
                 + (root.setupOk ? "" : " · click to finish setup")
    onPressed: function(b) {
      if (b === Qt.RightButton || b === Qt.MiddleButton) root.toggle()
      else root.primary()
    }

    SequentialAnimation on opacity {
      running: root.hot
      loops: Animation.Infinite
      alwaysRunToEnd: true
      NumberAnimation { from: 1.0; to: 0.45; duration: 700; easing.type: Easing.InOutSine }
      NumberAnimation { from: 0.45; to: 1.0; duration: 700; easing.type: Easing.InOutSine }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(12)

        // ---------- hero ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroText.implicitHeight)

          Text {
            id: heroIcon
            text: root.glyph()
            color: root.hot ? Commons.Color.accent : root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }
          Column {
            id: heroText
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)
            Text {
              text: "Ania Player"
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text {
              width: parent.width
              elide: Text.ElideRight
              text: (root.label() + (root.info.avatar ? " · " + root.info.avatar : "")).toUpperCase()
              color: Qt.darker(root.bar.foreground, 1.4)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
            }
          }
        }

        Button {
          visible: !root.setupOk
          width: parent.width
          iconText: ""
          text: "Finish setup"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          active: true
          onClicked: root.detached(["open-setup"])
        }
        Button {
          visible: root.setupOk && !root.runningNow
          width: parent.width
          iconText: ""
          text: "Start Ania Player"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          active: true
          onClicked: root.run(["start"])
        }

        // ---------- avatar ----------
        Column {
          visible: root.setupOk && root.runningNow
          width: parent.width
          spacing: Style.space(6)

          Row {
            id: rowA
            width: parent.width
            spacing: Style.space(6)
            Button {
              width: (rowA.width - rowA.spacing) / 2
              iconText: root.info.visible ? "" : ""
              text: root.info.visible ? "Hide" : "Show"
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              onClicked: root.run([root.info.visible ? "hide" : "show"])
            }
            Button {
              width: (rowA.width - rowA.spacing) / 2
              iconText: root.info.blocked ? "" : ""
              text: root.info.blocked ? "Unlock position" : "Lock position"
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              active: root.info.blocked === true
              onClicked: root.run([root.info.blocked ? "unlock" : "lock"])
            }
          }
          Row {
            id: rowB
            width: parent.width
            spacing: Style.space(6)
            Button {
              width: (rowB.width - rowB.spacing) / 2
              iconText: ""
              text: "Lock all"
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.run(["lock", "--all"])
            }
            Button {
              width: (rowB.width - rowB.spacing) / 2
              iconText: ""
              text: "Unlock all"
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.run(["unlock", "--all"])
            }
          }
          Button {
            width: parent.width
            leftAlign: true
            iconText: ""
            text: "Change avatar…"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            active: root.avatarsOpen
            onClicked: root.avatarsOpen = !root.avatarsOpen
          }
          Repeater {
            model: root.avatarsOpen ? root.avatars : []
            Button {
              required property var modelData
              width: parent.width
              leftAlign: true
              iconText: ""
              text: "   " + modelData.name
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              active: root.info.avatar === modelData.name
              onClicked: { root.run(["avatar", modelData.file]); root.avatarsOpen = false }
            }
          }
          Text {
            visible: root.avatarsOpen && root.avatars.length === 0
            width: parent.width
            wrapMode: Text.Wrap
            text: "No .ania avatars yet. Get free ones from the Marketplace below."
            color: root.bar.foreground
            opacity: 0.6
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- get more ----------
        Column {
          width: parent.width
          spacing: Style.space(4)
          PanelSectionHeader { text: "AVATARS AND WAKE WORDS"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
          Repeater {
            model: [
              { what: "marketplace", icon: "", label: "Marketplace (free avatars)" },
              { what: "credits", icon: "", label: "Get credits" },
              { what: "create-avatar", icon: "", label: "Create avatar with your AI" },
              { what: "create-wakeword", icon: "", label: "Create wake word" }
            ]
            Button {
              required property var modelData
              width: parent.width
              leftAlign: true
              iconText: modelData.icon
              text: modelData.label
              fontSize: Style.font.bodySmall
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.detached(["open", modelData.what])
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- opt-in features ----------
        Column {
          width: parent.width
          spacing: Style.space(8)
          PanelSectionHeader { text: "OPT-IN"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

          Item {
            width: parent.width
            implicitHeight: Math.max(briefText.implicitHeight, briefSwitch.implicitHeight)
            opacity: root.feats.briefing_toggle ? 1 : 0.5
            Column {
              id: briefText
              anchors.left: parent.left
              anchors.right: briefSwitch.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              Text {
                text: "Briefing after login"
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: root.feats.briefing_toggle ? "Speaks only what changed since last time."
                                                 : "Needs an Ania Player update."
                color: root.bar.foreground
                opacity: 0.6
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
            ToggleSwitch {
              id: briefSwitch
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              foreground: root.bar.foreground
              interactive: root.feats.briefing_toggle === true
              checked: root.bio.briefing === true
              onToggled: root.run(["briefing", checked ? "off" : "on"])
            }
          }
          Button {
            width: parent.width
            leftAlign: true
            enabled: root.feats.briefing_edit === true
            opacity: enabled ? 1 : 0.5
            iconText: ""
            text: "Edit briefing…"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            onClicked: root.detached(["briefing", "edit"])
          }

          Item {
            width: parent.width
            implicitHeight: Math.max(bioText.implicitHeight, bioSwitch.implicitHeight)
            visible: root.feats.biometria === true
            Column {
              id: bioText
              anchors.left: parent.left
              anchors.right: bioSwitch.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              Text {
                text: "Biometric unlock"
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
              Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: "Off unless you turn it on. Your face becomes a set of numbers kept only on this computer; no photo is stored and nothing is uploaded."
                color: root.bar.foreground
                opacity: 0.6
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
            ToggleSwitch {
              id: bioSwitch
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              foreground: root.bar.foreground
              checked: root.bio.unlock === true
              onToggled: {
                if (checked) root.run(["biometric", "off"])
                else root.detached(["biometric", "on"])
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        Row {
          id: actions
          width: parent.width
          spacing: Style.space(6)
          Button {
            width: (actions.width - actions.spacing) / 2
            iconText: ""
            text: "Settings"
            enabled: root.runningNow
            opacity: enabled ? 1 : 0.5
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.detached(["settings", "voice"])
          }
          Button {
            width: (actions.width - actions.spacing) / 2
            iconText: ""
            text: "Logs"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.detached(["logs", "--open"])
          }
        }
      }
    }
  }
}
