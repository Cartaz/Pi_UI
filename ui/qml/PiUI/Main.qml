pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window

    required property var agentAdapter
    required property var messageModel
    required property var profileModel
    required property var preflightAdapter
    required property var preflightModel
    required property var sandboxGateAdapter
    required property var sandboxGateModel

    width: 1180
    height: 760
    minimumWidth: 860
    minimumHeight: 560
    visible: true
    title: "Pi_UI"
    color: Theme.surface

    function submitComposer() {
        const value = composer.text
        if (!window.agentAdapter.canSend || value.trim().length === 0)
            return
        if (window.agentAdapter.sendMessage(value))
            composer.clear()
    }

    FolderDialog {
        id: workspaceDialog
        title: "Choose AIOS workspace"
        acceptLabel: "Use this folder"
        onAccepted: window.agentAdapter.setWorkspaceUrl(currentFolder)
    }

    Popup {
        id: preflightDialog
        property int page: 0

        parent: Overlay.overlay
        x: Math.round((window.width - width) / 2)
        y: Math.round((window.height - height) / 2)
        width: Math.min(780, window.width - 72)
        height: Math.min(640, window.height - 72)
        modal: true
        focus: true
        padding: 22
        closePolicy: Popup.CloseOnEscape

        onOpened: {
            page = 0
            if (!window.preflightAdapter.running)
                window.preflightAdapter.runPreflight()
        }

        background: Rectangle {
            radius: Theme.radiusMain
            color: Theme.surface
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.08)
        }

        contentItem: ColumnLayout {
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        text: preflightDialog.page === 0
                            ? "M0 host preflight"
                            : "M0 Bubblewrap gate"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: preflightDialog.page === 0
                            ? (window.preflightAdapter.operationError.length > 0
                                ? window.preflightAdapter.operationError
                                : window.preflightAdapter.statusText)
                            : (window.sandboxGateAdapter.operationError.length > 0
                                ? window.sandboxGateAdapter.operationError
                                : window.sandboxGateAdapter.statusText)
                        color: preflightDialog.page === 0
                            ? (window.preflightAdapter.failCount > 0
                                ? Theme.errorText
                                : Theme.textSecondary)
                            : (window.sandboxGateAdapter.failCount > 0
                                ? Theme.errorText
                                : Theme.textSecondary)
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                }

                NeuButton {
                    text: preflightDialog.page === 0
                        ? (window.preflightAdapter.running ? "Cancel" : "Run again")
                        : (window.sandboxGateAdapter.running ? "Cancel" : "Run gate")
                    enabled: preflightDialog.page === 0
                        || window.sandboxGateAdapter.running
                        || window.sandboxGateAdapter.canRun
                    accentText: preflightDialog.page === 1
                        && !window.sandboxGateAdapter.running
                    onClicked: {
                        if (preflightDialog.page === 0) {
                            if (window.preflightAdapter.running)
                                window.preflightAdapter.cancelPreflight()
                            else
                                window.preflightAdapter.runPreflight()
                        } else {
                            if (window.sandboxGateAdapter.running)
                                window.sandboxGateAdapter.cancelGate()
                            else
                                window.sandboxGateAdapter.runGate()
                        }
                    }
                }

                NeuButton {
                    text: "Close"
                    onClicked: preflightDialog.close()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                NeuButton {
                    text: "Host checks"
                    accentText: preflightDialog.page === 0
                    onClicked: preflightDialog.page = 0
                }

                NeuButton {
                    text: "Sandbox gate"
                    accentText: preflightDialog.page === 1
                    onClicked: preflightDialog.page = 1
                }

                Item { Layout.fillWidth: true }
            }

            Text {
                Layout.fillWidth: true
                visible: preflightDialog.page === 1
                text: "Explicit active test. Pi_UI creates temporary app-owned files inside the AIOS and one external sentinel, launches a controlled Node probe through the exact Bubblewrap mount policy used by Pi, then removes the fixtures. It does not contact Ornith or make a model request."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 11
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 16

                Text {
                    visible: preflightDialog.page === 0
                    text: "Blocking " + window.preflightAdapter.failCount
                    color: window.preflightAdapter.failCount > 0 ? Theme.errorText : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
                Text {
                    visible: preflightDialog.page === 0
                    text: "Warnings " + window.preflightAdapter.warningCount
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
                Text {
                    visible: preflightDialog.page === 0
                    text: "Pending target gate " + window.preflightAdapter.pendingCount
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
                Text {
                    visible: preflightDialog.page === 1
                    text: "Passed " + window.sandboxGateAdapter.passCount
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
                Text {
                    visible: preflightDialog.page === 1
                    text: "Failed " + window.sandboxGateAdapter.failCount
                    color: window.sandboxGateAdapter.failCount > 0
                        ? Theme.errorText
                        : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
                Item { Layout.fillWidth: true }
            }

            ListView {
                id: preflightList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                reuseItems: true
                spacing: 8
                model: preflightDialog.page === 0
                    ? window.preflightModel
                    : window.sandboxGateModel
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }

                delegate: Rectangle {
                    id: preflightDelegate
                    required property string label
                    required property string checkStatus
                    required property string summary
                    required property string detail

                    width: ListView.view.width
                    height: checkColumn.implicitHeight + 20
                    radius: Theme.radiusSmall
                    color: Theme.surface
                    border.width: 1
                    border.color: preflightDelegate.checkStatus === "fail"
                        ? Qt.rgba(220 / 255, 132 / 255, 96 / 255, 0.35)
                        : (preflightDelegate.checkStatus === "pass"
                            ? Qt.rgba(1, 1, 1, 0.055)
                            : Qt.rgba(1, 102 / 255, 0, 0.18))

                    Column {
                        id: checkColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 10
                        spacing: 3

                        Row {
                            spacing: 8
                            Text {
                                text: preflightDelegate.checkStatus.toUpperCase()
                                color: preflightDelegate.checkStatus === "fail"
                                    ? Theme.errorText
                                    : (preflightDelegate.checkStatus === "pass"
                                        ? Theme.textSecondary
                                        : Theme.accent)
                                font.family: Theme.fontFamily
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: preflightDelegate.label
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                        }

                        Text {
                            width: parent.width
                            text: preflightDelegate.summary
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }

                        Text {
                            width: parent.width
                            visible: preflightDelegate.detail.length > 0
                            text: preflightDelegate.detail
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: 10
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                visible: preflightDialog.page === 0
                    ? window.preflightAdapter.sanitizedManifest.length > 0
                    : window.sandboxGateAdapter.sanitizedManifest.length > 0
                text: preflightDialog.page === 0
                    ? "A sanitized host manifest is ready. Static preflight alone never proves confinement."
                    : "A sanitized confinement report is ready in application state. Local filesystem paths are not included."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
        }
    }

    Connections {
        target: window.agentAdapter
        function onRestoreComposerText(text) {
            if (composer.text.length === 0)
                composer.text = text
            else
                composer.text += "\n" + text
            composer.forceActiveFocus()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 26
        spacing: 18

        RaisedSurface {
            Layout.fillWidth: true
            Layout.preferredHeight: 104
            radius: Theme.radiusCard
            padding: 18

            RowLayout {
                anchors.fill: parent
                spacing: 16

                ColumnLayout {
                    Layout.minimumWidth: 210
                    Layout.maximumWidth: 300
                    spacing: 2

                    Text {
                        text: "Pi_UI"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 24
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: window.agentAdapter.workspacePath.length > 0
                            ? window.agentAdapter.workspacePath
                            : "No AIOS workspace selected"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                    }
                }

                Item { Layout.fillWidth: true }

                ColumnLayout {
                    Layout.preferredWidth: 250
                    spacing: 4

                    Text {
                        text: "Model profile"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }

                    ComboBox {
                        id: profileCombo
                        Layout.fillWidth: true
                        implicitHeight: 42
                        model: window.profileModel
                        textRole: "label"
                        currentIndex: window.agentAdapter.selectedProfileIndex
                        enabled: !window.agentAdapter.canDisconnect
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        leftPadding: 14
                        rightPadding: 34

                        onActivated: function(index) {
                            window.agentAdapter.selectProfile(index)
                        }

                        delegate: ItemDelegate {
                            id: profileDelegate
                            required property int index
                            width: profileCombo.width
                            text: profileCombo.textAt(index)
                            highlighted: profileCombo.highlightedIndex === index

                            contentItem: Text {
                                text: profileDelegate.text
                                color: profileDelegate.highlighted ? Theme.accent : Theme.textPrimary
                                font: profileCombo.font
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }

                            background: Rectangle {
                                radius: Theme.radiusSmall
                                color: profileDelegate.highlighted
                                    ? Qt.rgba(0, 0, 0, 0.22)
                                    : Theme.surface
                            }
                        }

                        contentItem: Text {
                            leftPadding: profileCombo.leftPadding
                            rightPadding: profileCombo.rightPadding
                            text: profileCombo.displayText.length > 0
                                ? profileCombo.displayText
                                : "No profile discovered"
                            font: profileCombo.font
                            color: profileCombo.enabled ? Theme.textPrimary : Theme.textMuted
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }

                        indicator: Text {
                            x: profileCombo.width - width - 13
                            y: (profileCombo.height - height) / 2 - 1
                            text: "⌄"
                            color: profileCombo.enabled ? Theme.textSecondary : Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: 16
                        }

                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.surface
                            border.width: profileCombo.activeFocus ? 1 : 0
                            border.color: profileCombo.activeFocus ? Theme.accent : "transparent"
                        }

                        popup: Popup {
                            id: profilePopup
                            y: profileCombo.height + 5
                            width: profileCombo.width
                            padding: 5
                            implicitHeight: Math.min(contentItem.implicitHeight + 10, 280)

                            contentItem: ListView {
                                clip: true
                                implicitHeight: contentHeight
                                model: profilePopup.visible ? profileCombo.delegateModel : null
                                currentIndex: profileCombo.highlightedIndex
                                ScrollIndicator.vertical: ScrollIndicator { }
                            }

                            background: Rectangle {
                                radius: Theme.radiusSmall
                                color: Theme.surface
                                border.width: 1
                                border.color: Qt.rgba(1, 1, 1, 0.07)
                            }
                        }
                    }
                }

                NeuButton {
                    text: "Workspace"
                    enabled: !window.agentAdapter.canDisconnect
                    onClicked: workspaceDialog.open()
                }

                NeuButton {
                    text: "Preflight"
                    enabled: !window.agentAdapter.canDisconnect
                    onClicked: preflightDialog.open()
                }

                NeuButton {
                    text: "Rescan"
                    enabled: window.agentAdapter.hasWorkspace && !window.agentAdapter.canDisconnect
                    onClicked: window.agentAdapter.refreshProfiles()
                }

                NeuButton {
                    accentText: true
                    text: window.agentAdapter.canDisconnect ? "Disconnect" : "Connect"
                    enabled: window.agentAdapter.canDisconnect || window.agentAdapter.canConnect
                    onClicked: {
                        if (window.agentAdapter.canDisconnect)
                            window.agentAdapter.disconnectAgent()
                        else
                            window.agentAdapter.connectAgent()
                    }
                }
            }
        }

        RaisedSurface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusMain
            padding: 22

            ColumnLayout {
                anchors.fill: parent
                spacing: 14

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "Conversation"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: window.agentAdapter.statusText
                        color: window.agentAdapter.lastError.length > 0
                            ? Theme.errorText
                            : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideRight
                        Layout.maximumWidth: 430
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Text {
                        anchors.centerIn: parent
                        visible: transcript.count === 0
                        text: window.agentAdapter.connectionState === "ready"
                            ? "Start a conversation with your AIOS"
                            : "Connect Pi to load the conversation"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                    }

                    ListView {
                        id: transcript
                        anchors.fill: parent
                        clip: true
                        reuseItems: true
                        spacing: 10
                        model: window.messageModel
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { }
                        property bool followTail: true

                        onMovementStarted: followTail = false
                        onMovementEnded: followTail = atYEnd
                        onCountChanged: {
                            if (followTail)
                                Qt.callLater(positionViewAtEnd)
                        }
                        onContentHeightChanged: {
                            if (followTail)
                                Qt.callLater(positionViewAtEnd)
                        }

                        delegate: Item {
                            id: messageDelegate
                            required property string messageId
                            required property string messageRole
                            required property string text
                            required property string messageState

                            width: ListView.view.width
                            height: bubble.height + 8

                            Rectangle {
                                id: bubble
                                width: Math.min(parent.width * 0.84, Math.max(220, messageText.implicitWidth + 38))
                                height: messageColumn.implicitHeight + 24
                                x: messageDelegate.messageRole === "user" ? parent.width - width - 8 : 8
                                radius: Theme.radiusControl
                                color: Theme.surface
                                border.width: 1
                                border.color: messageDelegate.messageRole === "user"
                                    ? Qt.rgba(1, 102 / 255, 0, 0.22)
                                    : Qt.rgba(1, 1, 1, 0.055)

                                Column {
                                    id: messageColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 12
                                    spacing: 6

                                    Text {
                                        text: messageDelegate.messageRole === "user" ? "You" : "Ornith"
                                        color: messageDelegate.messageRole === "user"
                                            ? Theme.accent
                                            : Theme.textSecondary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }

                                    TextEdit {
                                        id: messageText
                                        width: parent.width
                                        text: messageDelegate.text
                                        readOnly: true
                                        color: Theme.textPrimary
                                        selectionColor: Theme.accent
                                        selectedTextColor: Theme.surface
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 14
                                        wrapMode: TextEdit.Wrap
                                        textFormat: TextEdit.PlainText
                                        selectByMouse: true
                                    }

                                    Text {
                                        visible: messageDelegate.messageState !== "complete"
                                        text: messageDelegate.messageState
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 10
                                    }
                                }
                            }
                        }
                    }
                }

                InsetSurface {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 128
                    radius: Theme.radiusControl
                    padding: 12
                    focused: composer.activeFocus

                    TextArea {
                        id: composer
                        anchors.fill: parent
                        enabled: window.agentAdapter.connectionState === "ready"
                        color: Theme.textPrimary
                        selectionColor: Theme.accent
                        selectedTextColor: Theme.surface
                        placeholderText: window.agentAdapter.canSend
                            ? "Message Ornith…  Enter to send · Shift+Enter for a new line"
                            : "Connect Pi and wait for the session to load"
                        placeholderTextColor: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        background: null
                        Accessible.name: "Message composer"

                        Keys.onPressed: function(event) {
                            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                    && !(event.modifiers & Qt.ShiftModifier)) {
                                window.submitComposer()
                                event.accepted = true
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Text {
                        Layout.fillWidth: true
                        text: window.agentAdapter.turnState === "running"
                            ? "Turn in progress"
                            : (window.agentAdapter.connectionState === "loading-session"
                                ? "Loading existing session…"
                                : "")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                    }

                    NeuButton {
                        text: "Stop"
                        enabled: window.agentAdapter.canStop
                        onClicked: window.agentAdapter.stopTurn()
                    }

                    NeuButton {
                        text: "Send"
                        accentText: true
                        enabled: window.agentAdapter.canSend && composer.text.trim().length > 0
                        onClicked: window.submitComposer()
                    }
                }
            }
        }
    }
}
