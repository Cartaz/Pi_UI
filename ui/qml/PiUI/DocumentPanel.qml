pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RaisedSurface {
    id: panel

    required property var documentAdapter
    property bool closable: false
    signal closeRequested()

    radius: Theme.radiusMain
    padding: 14

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
                    text: "Document"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                }

                Text {
                    Layout.fillWidth: true
                    text: panel.documentAdapter.hasSelection
                        ? panel.documentAdapter.selectedName
                        : "Read-only preview"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                    elide: Text.ElideMiddle
                }

                Text {
                    Layout.fillWidth: true
                    visible: panel.documentAdapter.selectedPath.length > 0
                    text: panel.documentAdapter.selectedPath
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: 9
                    elide: Text.ElideMiddle
                }
            }

            NeuButton {
                text: "Reload"
                Layout.preferredWidth: 82
                Layout.preferredHeight: 34
                enabled: panel.documentAdapter.canReload
                onClicked: panel.documentAdapter.reload()
            }

            NeuButton {
                visible: panel.closable
                text: "Close"
                Layout.preferredWidth: 72
                Layout.preferredHeight: 34
                onClicked: panel.closeRequested()
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: panel.documentAdapter.state === "ready" ? 1 : 0

            Rectangle {
                radius: Theme.radiusControl
                color: Theme.surface
                border.width: panel.documentAdapter.state === "error"
                        || panel.documentAdapter.state === "unsupported"
                    ? 1
                    : 0
                border.color: panel.documentAdapter.state === "error"
                    ? Qt.rgba(220 / 255, 132 / 255, 96 / 255, 0.35)
                    : Qt.rgba(1, 102 / 255, 0, 0.18)

                Column {
                    anchors.centerIn: parent
                    width: Math.max(120, parent.width - 32)
                    spacing: 7

                    Text {
                        width: parent.width
                        text: panel.documentAdapter.loading
                            ? "Loading preview…"
                            : (panel.documentAdapter.hasSelection
                                ? (panel.documentAdapter.message.length > 0
                                    ? panel.documentAdapter.message
                                    : panel.documentAdapter.statusText)
                                : "Select a file from Knowledge to preview it.")
                        color: panel.documentAdapter.state === "error"
                            ? Theme.errorText
                            : (panel.documentAdapter.state === "unsupported"
                                ? Theme.textSecondary
                                : Theme.textMuted)
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }

                    Text {
                        width: parent.width
                        visible: !panel.documentAdapter.hasSelection
                        text: "UTF-8 text only · maximum "
                            + Math.round(panel.documentAdapter.maxPreviewBytes / 1024)
                            + " KiB"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }

            InsetSurface {
                radius: Theme.radiusControl
                padding: 12
                focused: previewText.activeFocus

                TextArea {
                    id: previewText
                    objectName: "documentPreviewText"
                    anchors.fill: parent
                    text: panel.documentAdapter.renderedText
                    readOnly: true
                    color: Theme.textPrimary
                    selectionColor: Theme.accent
                    selectedTextColor: Theme.surface
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    selectByMouse: true
                    background: null
                    Accessible.name: panel.documentAdapter.selectedName.length > 0
                        ? "Document preview " + panel.documentAdapter.selectedName
                        : "Document preview"

                    Keys.onPressed: function(event) {
                        if (event.matches(StandardKey.Copy)
                                && previewText.selectionStart !== previewText.selectionEnd) {
                            panel.documentAdapter.copySelection(
                                previewText.selectionStart,
                                previewText.selectionEnd
                            )
                            event.accepted = true
                        }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: panel.documentAdapter.operationError.length > 0
                ? panel.documentAdapter.operationError
                : panel.documentAdapter.statusText
            color: panel.documentAdapter.operationError.length > 0
                    || panel.documentAdapter.state === "error"
                ? Theme.errorText
                : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            elide: Text.ElideRight
        }
    }
}
