import QtQuick

Item {
    id: root

    default property alias contentData: content.data
    property real radius: Theme.radiusControl
    property real padding: 14
    property bool focused: false

    Rectangle {
        id: panel
        anchors.fill: parent
        radius: root.radius
        color: Theme.surface
        border.width: root.focused ? 1 : 0
        border.color: root.focused ? Theme.accent : "transparent"
    }

    // Lightweight inset cue: keep it centralized here instead of duplicating
    // edge stacks across controls. M1 will calibrate this visually on target GPU.
    Rectangle {
        anchors.top: panel.top
        anchors.left: panel.left
        anchors.right: panel.right
        anchors.margins: 2
        height: 2
        radius: 1
        color: Qt.rgba(0, 0, 0, 0.34)
    }
    Rectangle {
        anchors.left: panel.left
        anchors.top: panel.top
        anchors.bottom: panel.bottom
        anchors.margins: 2
        width: 2
        radius: 1
        color: Qt.rgba(0, 0, 0, 0.30)
    }
    Rectangle {
        anchors.bottom: panel.bottom
        anchors.left: panel.left
        anchors.right: panel.right
        anchors.margins: 2
        height: 1
        color: Qt.rgba(1, 1, 1, 0.055)
    }
    Rectangle {
        anchors.right: panel.right
        anchors.top: panel.top
        anchors.bottom: panel.bottom
        anchors.margins: 2
        width: 1
        color: Qt.rgba(1, 1, 1, 0.05)
    }

    Item {
        id: content
        anchors.fill: panel
        anchors.margins: root.padding
    }
}
