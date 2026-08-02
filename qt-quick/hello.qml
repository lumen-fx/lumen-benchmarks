import QtQuick
import QtQuick.Controls.Basic

// Mirrors qt-widgets/hello.cpp: one bold "Hello" label + one "Press"
// button, centered. Basic style so controls are drawn by the scene
// graph, not deferred to a native style.
Rectangle {
    width: 800
    height: 600
    color: "white"

    Column {
        anchors.centerIn: parent
        spacing: 12

        Text {
            text: "Hello"
            font.bold: true
            font.pixelSize: 18
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Button {
            text: "Press"
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
