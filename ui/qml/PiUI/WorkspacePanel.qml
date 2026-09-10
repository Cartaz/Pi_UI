pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RaisedSurface {
    id: panel

    required property var workspaceAdapter
    required property var workspaceModel

    radius: Theme.radiusMain
    padding: 16

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: "Knowledge"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                }

                Text {
                    Layout.fillWidth: true
                    text: panel.workspaceAdapter.hasWorkspace
                        ? "Workspace files"
                        : "Choose a workspace"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }

            NeuButton {
                text: "Refresh"
                Layout.preferredWidth: 96
                Layout.preferredHeight: 38
                enabled: panel.workspaceAdapter.hasWorkspace && !panel.workspaceAdapter.loading
                onClicked: panel.workspaceAdapter.refresh()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusControl
            color: Theme.surface
            border.width: fileList.activeFocus ? 1 : 0
            border.color: fileList.activeFocus ? Theme.accent : "transparent"

            Text {
                anchors.centerIn: parent
                width: parent.width - 30
                visible: panel.workspaceAdapter.itemCount === 0
                text: !panel.workspaceAdapter.hasWorkspace
                    ? "Select an AIOS workspace to browse files"
                    : (panel.workspaceAdapter.loading
                        ? "Loading workspace…"
                        : (panel.workspaceAdapter.lastError.length > 0
                            ? panel.workspaceAdapter.lastError
                            : "Workspace is empty"))
                color: panel.workspaceAdapter.lastError.length > 0
                    ? Theme.errorText
                    : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 12
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            ListView {
                id: fileList
                objectName: "workspaceFileList"
                anchors.fill: parent
                anchors.margins: 5
                clip: true
                reuseItems: true
                spacing: 2
                model: panel.workspaceModel
                activeFocusOnTab: true
                boundsBehavior: Flickable.StopAtBounds
                currentIndex: count > 0 ? 0 : -1
                ScrollBar.vertical: ScrollBar { }

                Keys.onPressed: function(event) {
                    if (fileList.currentIndex < 0)
                        return
                    if (event.key === Qt.Key_Return
                            || event.key === Qt.Key_Enter
                            || event.key === Qt.Key_Space) {
                        panel.workspaceAdapter.toggleRow(fileList.currentIndex)
                        event.accepted = true
                    }
                }

                delegate: Item {
                    id: fileRow

                    required property int index
                    required property string name
                    required property string relativePath
                    required property string entryKind
                    required property int depth
                    required property bool expanded
                    required property bool loading
                    required property bool canExpand
                    required property bool hiddenEntry

                    width: ListView.view.width
                    height: 36

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusSmall
                        color: fileRow.ListView.isCurrentItem
                            ? Qt.rgba(0, 0, 0, 0.24)
                            : "transparent"
                        border.width: fileRow.ListView.isCurrentItem && fileList.activeFocus ? 1 : 0
                        border.color: Theme.accent
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 8 + fileRow.depth * 14
                        anchors.rightMargin: 8
                        spacing: 7

                        Text {
                            width: 14
                            text: fileRow.loading
                                ? "…"
                                : (fileRow.canExpand
                                    ? (fileRow.expanded ? "⌄" : "›")
                                    : (fileRow.entryKind === "symlink" ? "↗" : "·"))
                            color: fileRow.canExpand ? Theme.accent : Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: 14
                            horizontalAlignment: Text.AlignHCenter
                        }

                        Text {
                            width: parent.width - 24
                            text: fileRow.name
                            color: fileRow.hiddenEntry ? Theme.textSecondary : Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            elide: Text.ElideMiddle
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    TapHandler {
                        acceptedButtons: Qt.LeftButton
                        onTapped: {
                            fileList.currentIndex = fileRow.index
                            if (fileRow.canExpand)
                                panel.workspaceAdapter.toggleRow(fileRow.index)
                            fileList.forceActiveFocus()
                        }
                    }

                    Accessible.role: Accessible.ListItem
                    Accessible.name: fileRow.name
                    Accessible.description: fileRow.entryKind === "directory"
                        ? (fileRow.expanded ? "Expanded directory" : "Collapsed directory")
                        : fileRow.entryKind
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: panel.workspaceAdapter.operationError.length > 0
                ? panel.workspaceAdapter.operationError
                : panel.workspaceAdapter.statusText
            color: panel.workspaceAdapter.operationError.length > 0
                    || panel.workspaceAdapter.lastError.length > 0
                ? Theme.errorText
                : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            elide: Text.ElideRight
        }
    }
}
