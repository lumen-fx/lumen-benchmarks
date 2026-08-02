import QtQuick
import QtQuick.Controls.Basic

// Mirrors qt-widgets/forms.cpp: header, scrollable settings page (6
// GroupBoxes, ~40 controls), footer status labels. objectNames on the
// controls the interact driver touches (inputN, checkN, toggleN,
// radioAN, radioBN, status, themeLabel, telemetryLabel) let forms.cpp
// find them once after load and drive them the same way the Qt Widgets
// driver drives its QLineEdit/QCheckBox/QRadioButton pointers.
//
// Equivalence note: unlike Qt Widgets (no switch widget, QCheckBox
// stands in), QtQuick.Controls has a real Switch, used here directly.
Item {
    id: root
    width: 800
    height: 600

    ButtonGroup { id: themeGroup }
    ButtonGroup { id: telemetryGroup }

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

    ScrollView {
        id: scroll
        anchors.top: header.bottom
        anchors.bottom: footer.top
        anchors.left: parent.left
        anchors.right: parent.right
        clip: true

        Column {
            id: formColumn
            width: scroll.availableWidth
            spacing: 12

            GroupBox {
                title: "Account"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Username:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input0"; placeholderText: "Username"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Email:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input1"; placeholderText: "Email"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        CheckBox { objectName: "check0"; text: "Remember me" }
                        CheckBox { objectName: "check1"; text: "Subscribe to newsletter" }
                    }
                    Row {
                        Button { text: "Sign out" }
                    }
                }
            }

            GroupBox {
                title: "Appearance"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Theme:"; width: 110 }
                        Column {
                            spacing: 4
                            RadioButton { objectName: "radioA0"; text: "System"; checked: true; ButtonGroup.group: themeGroup }
                            RadioButton { objectName: "radioA1"; text: "Light"; ButtonGroup.group: themeGroup }
                            RadioButton { objectName: "radioA2"; text: "Dark"; ButtonGroup.group: themeGroup }
                            RadioButton { objectName: "radioA3"; text: "High contrast"; ButtonGroup.group: themeGroup }
                        }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Font size:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Slider { from: 0; to: 100; value: 50; width: 200; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Density:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        ComboBox { model: ["Compact", "Cozy", "Normal", "Comfortable", "Spacious"]; width: 200 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Animations:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Switch { objectName: "toggle0"; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }

            GroupBox {
                title: "Network"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Proxy host:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input2"; placeholderText: "proxy.example.com"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Proxy port:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input3"; placeholderText: "8080"; width: 100 }
                    }
                    Row {
                        spacing: 12
                        CheckBox { objectName: "check2"; text: "Use proxy" }
                        CheckBox { objectName: "check3"; text: "Verify TLS certificates" }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Timeout:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Slider { from: 0; to: 100; value: 50; width: 200; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Protocol:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        ComboBox { model: ["Auto", "HTTP/1.1", "HTTP/2", "HTTP/3", "SOCKS5"]; width: 200 }
                    }
                    Row {
                        Button { text: "Test connection" }
                    }
                }
            }

            GroupBox {
                title: "Editor"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Font family:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input4"; placeholderText: "monospace"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Tab width:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input5"; placeholderText: "4"; width: 100 }
                    }
                    Row {
                        spacing: 12
                        CheckBox { objectName: "check4"; text: "Word wrap" }
                        CheckBox { objectName: "check5"; text: "Line numbers" }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Line endings:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        ComboBox { model: ["Auto", "LF", "CRLF", "CR", "Keep mixed"]; width: 200 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Rulers:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Slider { from: 0; to: 100; value: 50; width: 200; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Autosave:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Switch { objectName: "toggle1"; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
            }

            GroupBox {
                title: "Privacy"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Telemetry:"; width: 110 }
                        Column {
                            spacing: 4
                            RadioButton { objectName: "radioB0"; text: "Off"; checked: true; ButtonGroup.group: telemetryGroup }
                            RadioButton { objectName: "radioB1"; text: "Crash reports only"; ButtonGroup.group: telemetryGroup }
                            RadioButton { objectName: "radioB2"; text: "Basic"; ButtonGroup.group: telemetryGroup }
                            RadioButton { objectName: "radioB3"; text: "Full"; ButtonGroup.group: telemetryGroup }
                        }
                    }
                    Row {
                        spacing: 12
                        CheckBox { objectName: "check6"; text: "Upload crash reports" }
                        CheckBox { objectName: "check7"; text: "Share usage statistics" }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Do not track:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Switch { objectName: "toggle2"; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        Button { text: "Clear data" }
                    }
                }
            }

            GroupBox {
                title: "Advanced"
                width: parent.width
                Column {
                    width: parent.width
                    spacing: 8
                    Row {
                        spacing: 12
                        Text { text: "Config path:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input6"; placeholderText: "~/.config/bench"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Log filter:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        TextField { objectName: "input7"; placeholderText: "info"; width: 220 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Log level:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        ComboBox { model: ["Error", "Warn", "Info", "Debug", "Trace"]; width: 200 }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Cache size:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Slider { from: 0; to: 100; value: 50; width: 200; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        spacing: 12
                        Text { text: "Experimental:"; width: 110; anchors.verticalCenter: parent.verticalCenter }
                        Switch { objectName: "toggle3"; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Row {
                        Button { text: "Reset all" }
                    }
                }
            }
        }
    }

    Rectangle {
        id: footer
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 32
        color: "white"

        Row {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            Text { objectName: "status"; text: "idle"; color: "#777777" }
            Text { objectName: "themeLabel"; text: "theme: System"; color: "#777777" }
            Text { objectName: "telemetryLabel"; text: "telemetry: Off"; color: "#777777" }
        }
    }
}
