import QtQuick
import QtQuick.Controls

Item {
    id: root

    default property alias contentData: content.data
    property real radius: Theme.radiusControl
    property real padding: 14
    property bool focused: false

    function ensureCursorVisible() {
        if (content.children.length === 0)
            return
        const child = content.children[0]
        if (child.cursorRectangle === undefined)
            return

        const margin = 4
        const cursorTop = child.cursorRectangle.y - margin
        const cursorBottom = child.cursorRectangle.y + child.cursorRectangle.height + margin
        const viewportTop = viewport.contentY
        const viewportBottom = viewportTop + viewport.height

        if (cursorTop < viewportTop) {
            viewport.contentY = Math.max(0, cursorTop)
        } else if (cursorBottom > viewportBottom) {
            viewport.contentY = Math.min(
                Math.max(0, viewport.contentHeight - viewport.height),
                cursorBottom - viewport.height
            )
        }
    }

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

    Flickable {
        id: viewport
        objectName: "insetViewport"
        anchors.fill: panel
        anchors.margins: root.padding
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: Math.max(height, content.implicitHeight)
        interactive: contentHeight > height

        ScrollBar.vertical: ScrollBar {
            objectName: "insetVerticalScrollBar"
            policy: ScrollBar.AsNeeded
        }

        Item {
            id: content
            width: viewport.width
            height: Math.max(viewport.height, implicitHeight)
            implicitHeight: {
                let value = 0
                for (let index = 0; index < children.length; ++index)
                    value = Math.max(value, children[index].implicitHeight)
                return value
            }
        }
    }

    Connections {
        target: content.children.length > 0 ? content.children[0] : null
        ignoreUnknownSignals: true

        function onCursorRectangleChanged() {
            root.ensureCursorVisible()
        }
    }
}
