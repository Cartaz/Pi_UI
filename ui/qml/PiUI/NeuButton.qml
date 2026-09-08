import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Button {
    id: control

    property bool accentText: false

    implicitWidth: Math.max(104, contentItem.implicitWidth + 34)
    implicitHeight: 44
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: 14
    font.weight: Font.DemiBold

    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled
            ? Theme.textMuted
            : (control.accentText || control.activeFocus ? Theme.accent : Theme.textPrimary)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Item {
        RectangularShadow {
            anchors.fill: buttonSurface
            visible: control.enabled && !control.down
            offset.x: control.hovered ? 4.5 : 3.5
            offset.y: control.hovered ? 4.5 : 3.5
            blur: control.hovered ? 12 : 10
            radius: buttonSurface.radius
            color: Theme.shadowDarkSoft
            cached: false
        }

        RectangularShadow {
            anchors.fill: buttonSurface
            visible: control.enabled && !control.down
            offset.x: control.hovered ? -3.8 : -3
            offset.y: control.hovered ? -3.8 : -3
            blur: control.hovered ? 10 : 8.5
            radius: buttonSurface.radius
            color: Theme.shadowLightSoft
            cached: false
        }

        RectangularShadow {
            anchors.fill: buttonSurface
            visible: control.activeFocus
            offset.x: 0
            offset.y: 0
            blur: 9
            spread: 1
            radius: buttonSurface.radius
            color: Theme.focusGlow
            cached: false
        }

        Rectangle {
            id: buttonSurface
            anchors.fill: parent
            radius: Theme.radiusControl
            color: Theme.surface
            border.width: control.activeFocus ? 1 : (control.down ? 1 : 0)
            border.color: control.activeFocus
                ? Theme.accent
                : (control.down ? Qt.rgba(0, 0, 0, 0.7) : "transparent")
            opacity: control.enabled ? 1 : 0.62
        }
    }
}
