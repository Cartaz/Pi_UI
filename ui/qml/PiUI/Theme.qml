pragma Singleton

import QtQuick

QtObject {
    readonly property color surface: Qt.rgba(20 / 255, 20 / 255, 20 / 255, 1)
    readonly property color accent: Qt.rgba(1, 102 / 255, 0, 1)
    readonly property color textPrimary: Qt.rgba(225 / 255, 225 / 255, 225 / 255, 1)
    readonly property color textSecondary: Qt.rgba(135 / 255, 135 / 255, 135 / 255, 1)
    readonly property color textMuted: Qt.rgba(90 / 255, 90 / 255, 90 / 255, 1)
    readonly property color shadowDarkStrong: Qt.rgba(0, 0, 0, 0.62)
    readonly property color shadowDarkSoft: Qt.rgba(0, 0, 0, 0.46)
    readonly property color shadowLightStrong: Qt.rgba(1, 1, 1, 0.10)
    readonly property color shadowLightSoft: Qt.rgba(1, 1, 1, 0.075)
    readonly property color focusGlow: Qt.rgba(1, 102 / 255, 0, 0.20)
    readonly property color errorText: Qt.rgba(220 / 255, 132 / 255, 96 / 255, 1)

    readonly property string fontFamily: "Noto Sans"

    readonly property real radiusMain: 28
    readonly property real radiusCard: 22
    readonly property real radiusControl: 16
    readonly property real radiusSmall: 12

    readonly property int durationFast: 100
    readonly property int durationNormal: 160
}
