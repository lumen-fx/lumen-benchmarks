import QtQuick
import QtQuick.Controls.Basic

// Mirrors qt-widgets/list.cpp: header (bold title + count button), a
// virtualized 10,000-row list (bold "Item {i}" + grey "subtitle {i}"),
// footer (text input + slider + value label). The model is a C++
// QAbstractListModel (benchListModel, set as a context property by
// list.cpp) so row data is produced the same way as the Qt Widgets
// BenchModel; ListView instantiates only the on-screen delegates.
Item {
    id: root
    width: 800
    height: 600

    property int clickCount: 0

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
        Button {
            text: "Count: " + root.clickCount
            onClicked: root.clickCount++
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    ListView {
        id: benchList
        objectName: "benchList"
        anchors.top: header.bottom
        anchors.bottom: footer.top
        anchors.left: parent.left
        anchors.right: parent.right
        clip: true
        model: benchListModel

        delegate: Item {
            width: benchList.width
            height: 36

            Row {
                anchors.fill: parent
                anchors.leftMargin: 8
                spacing: 12

                Text {
                    text: title
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: subtitle
                    color: "#777777"
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    Rectangle {
        id: footer
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 56
        color: "white"

        Row {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 12

            TextField {
                placeholderText: "Type here..."
                width: 240
                anchors.verticalCenter: parent.verticalCenter
            }
            Slider {
                id: slider
                from: 0
                to: 100
                value: 50
                width: 200
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: Math.round(slider.value)
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
