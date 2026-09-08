import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window

    width: 1180
    height: 760
    minimumWidth: 860
    minimumHeight: 560
    visible: true
    title: "Pi_UI"
    color: Theme.surface

    function submitComposer() {
        const value = composer.text
        if (!agentAdapter.canSend || value.trim().length === 0)
            return
        if (agentAdapter.sendMessage(value))
            composer.clear()
    }

    FolderDialog {
        id: workspaceDialog
        title: "Choose AIOS workspace"
        onAccepted: agentAdapter.setWorkspaceUrl(selectedFolder)
    }

    Connections {
        target: agentAdapter
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
                        text: agentAdapter.workspacePath.length > 0
                            ? agentAdapter.workspacePath
                            : "No AIOS workspace selected"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                    }
                }

                Item { Layout.fillWidth: true }

                ColumnLayout {
                    Layout.preferredWidth: 290
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
                        model: profileModel
                        textRole: "label"
                        currentIndex: agentAdapter.selectedProfileIndex
                        enabled: !agentAdapter.canDisconnect
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        leftPadding: 14
                        rightPadding: 34

                        onActivated: agentAdapter.selectProfile(index)

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

                        popup.background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.surface
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, 0.07)
                        }
                    }
                }

                NeuButton {
                    text: "Workspace"
                    enabled: !agentAdapter.canDisconnect
                    onClicked: workspaceDialog.open()
                }

                NeuButton {
                    text: "Rescan"
                    enabled: agentAdapter.hasWorkspace && !agentAdapter.canDisconnect
                    onClicked: agentAdapter.refreshProfiles()
                }

                NeuButton {
                    accentText: true
                    text: agentAdapter.canDisconnect ? "Disconnect" : "Connect"
                    enabled: agentAdapter.canDisconnect || agentAdapter.canConnect
                    onClicked: {
                        if (agentAdapter.canDisconnect)
                            agentAdapter.disconnectAgent()
                        else
                            agentAdapter.connectAgent()
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
                        text: agentAdapter.statusText
                        color: agentAdapter.lastError.length > 0
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
                        text: agentAdapter.connectionState === "ready"
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
                        model: messageModel
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
                                x: messageRole === "user" ? parent.width - width - 8 : 8
                                radius: Theme.radiusControl
                                color: Theme.surface
                                border.width: 1
                                border.color: messageRole === "user"
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
                                        text: messageRole === "user" ? "You" : "Ornith"
                                        color: messageRole === "user" ? Theme.accent : Theme.textSecondary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }

                                    Text {
                                        id: messageText
                                        width: parent.width
                                        text: parent.parent.parent.text
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 14
                                        wrapMode: Text.Wrap
                                        textFormat: Text.PlainText
                                        selectByMouse: true
                                    }

                                    Text {
                                        visible: messageState !== "complete"
                                        text: messageState
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
                        enabled: agentAdapter.connectionState === "ready"
                        color: Theme.textPrimary
                        selectionColor: Theme.accent
                        selectedTextColor: Theme.surface
                        placeholderText: agentAdapter.canSend
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
                        text: agentAdapter.turnState === "running"
                            ? "Turn in progress"
                            : (agentAdapter.connectionState === "loading-session"
                                ? "Loading existing session…"
                                : "")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                    }

                    NeuButton {
                        text: "Stop"
                        enabled: agentAdapter.canStop
                        onClicked: agentAdapter.stopTurn()
                    }

                    NeuButton {
                        text: "Send"
                        accentText: true
                        enabled: agentAdapter.canSend && composer.text.trim().length > 0
                        onClicked: window.submitComposer()
                    }
                }
            }
        }
    }
}
