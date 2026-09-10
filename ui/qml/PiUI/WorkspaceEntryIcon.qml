pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: icon

    required property string kind
    property bool expanded: false
    property bool muted: false

    implicitWidth: 16
    implicitHeight: 16

    readonly property color strokeColor: muted ? Theme.textMuted : Theme.textSecondary

    Item {
        anchors.fill: parent
        visible: icon.kind === "directory"

        Rectangle {
            x: 2
            y: 3
            width: 6
            height: 4
            radius: 1
            color: icon.strokeColor
            opacity: 0.9
        }

        Rectangle {
            x: 1
            y: 5
            width: 14
            height: 9
            radius: 2
            color: icon.expanded ? Qt.rgba(1, 1, 1, 0.035) : "transparent"
            border.width: 1
            border.color: icon.strokeColor
        }
    }

    Item {
        anchors.fill: parent
        visible: icon.kind === "file"

        Rectangle {
            x: 3
            y: 1
            width: 10
            height: 14
            radius: 1.5
            color: "transparent"
            border.width: 1
            border.color: icon.strokeColor
        }

        Rectangle {
            x: 5
            y: 5
            width: 6
            height: 1
            radius: 0.5
            color: icon.strokeColor
            opacity: 0.72
        }

        Rectangle {
            x: 5
            y: 8
            width: 6
            height: 1
            radius: 0.5
            color: icon.strokeColor
            opacity: 0.72
        }

        Rectangle {
            x: 5
            y: 11
            width: 4
            height: 1
            radius: 0.5
            color: icon.strokeColor
            opacity: 0.72
        }
    }

    Item {
        anchors.fill: parent
        visible: icon.kind === "symlink"

        Rectangle {
            x: 2
            y: 3
            width: 9
            height: 11
            radius: 1.5
            color: "transparent"
            border.width: 1
            border.color: icon.strokeColor
        }

        Text {
            x: 7
            y: -2
            text: "↗"
            color: icon.strokeColor
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }
    }

    Item {
        anchors.fill: parent
        visible: icon.kind !== "directory"
            && icon.kind !== "file"
            && icon.kind !== "symlink"

        Rectangle {
            anchors.centerIn: parent
            width: 10
            height: 10
            radius: 2
            color: "transparent"
            border.width: 1
            border.color: icon.strokeColor
        }

        Rectangle {
            anchors.centerIn: parent
            width: 2
            height: 2
            radius: 1
            color: icon.strokeColor
        }
    }
}
