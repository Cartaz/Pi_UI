import QtQuick
import QtQuick.Effects

Item {
    id: root

    default property alias contentData: content.data
    property real radius: Theme.radiusMain
    property real padding: 20
    property bool softDepth: false
    property bool hovered: false

    RectangularShadow {
        anchors.fill: panel
        offset.x: root.softDepth ? (root.hovered ? 4.5 : 3.5) : 8
        offset.y: root.softDepth ? (root.hovered ? 4.5 : 3.5) : 8
        blur: root.softDepth ? (root.hovered ? 12 : 10) : 20
        spread: 0
        radius: panel.radius
        color: root.softDepth ? Theme.shadowDarkSoft : Theme.shadowDarkStrong
        cached: false
    }

    RectangularShadow {
        anchors.fill: panel
        offset.x: root.softDepth ? (root.hovered ? -3.8 : -3) : -6
        offset.y: root.softDepth ? (root.hovered ? -3.8 : -3) : -6
        blur: root.softDepth ? (root.hovered ? 10 : 8.5) : 15
        spread: 0
        radius: panel.radius
        color: root.softDepth ? Theme.shadowLightSoft : Theme.shadowLightStrong
        cached: false
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        radius: root.radius
        color: Theme.surface
    }

    Item {
        id: content
        anchors.fill: panel
        anchors.margins: root.padding
    }

    Behavior on opacity {
        NumberAnimation { duration: Theme.durationFast }
    }
}
