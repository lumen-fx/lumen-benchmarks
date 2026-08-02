import QtQuick
import QtQuick.Controls.Basic

// Mirrors qt-widgets/textview.cpp: header + the shared corpus in a
// read-only, word-wrapped long-document view. TextArea is backed by the
// same QTextDocument layout engine QTextEdit uses, so it lays out lazily
// around the wrapped width; wrapping it in a plain Flickable (rather than
// ScrollView) gives textview.cpp a `contentY` it can drive directly, the
// same way list.cpp drives the ListView.
Item {
    id: root
    width: 800
    height: 600

    Rectangle {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 48
        color: "white"

        Text {
            text: "Bench"
            font.bold: true
            font.pixelSize: 18
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Flickable {
        id: flick
        objectName: "flick"
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        clip: true
        contentWidth: width
        contentHeight: textArea.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        TextArea {
            id: textArea
            objectName: "textArea"
            width: flick.width
            readOnly: true
            wrapMode: TextArea.Wrap
            text: benchCorpus
            background: null
        }
    }
}
