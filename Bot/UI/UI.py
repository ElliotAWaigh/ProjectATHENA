from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

class AthenaMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ATHENA Technologies")
        self.setGeometry(100, 100, 800, 600)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout(central_widget)

        # ATHENA Logo
        logo_label = QLabel(self)
        logo_pixmap = QPixmap("athena_logo.png")  # Replace with your logo path
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Buttons Around Logo
        calendar_button = QPushButton("Calendar", self)
        calendar_button.clicked.connect(self.open_calendar_gui)
        layout.addWidget(calendar_button)

        spotify_button = QPushButton("Spotify", self)
        spotify_button.clicked.connect(self.open_spotify_gui)
        layout.addWidget(spotify_button)

        # Add more buttons as needed

    def open_calendar_gui(self):
        # Logic to open the Calendar GUI
        pass

    def open_spotify_gui(self):
        # Logic to open the Spotify GUI
        pass

if __name__ == "__main__":
    app = QApplication([])

    # Define your style sheet
    style_sheet = """
    QMainWindow {
        background-color: #2b2b2b;
        color: #ffffff;
    }

    QLabel {
        color: #ffffff;
    }

    QPushButton {
        background-color: #3a3a3a;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 10px;
        font-size: 14px;
        border-radius: 5px;
    }

    QPushButton:hover {
        background-color: #555555;
    }
    """

    # Apply the style sheet to the application
    app.setStyleSheet(style_sheet)

    main_window = AthenaMainWindow()
    main_window.show()
    app.exec_()
