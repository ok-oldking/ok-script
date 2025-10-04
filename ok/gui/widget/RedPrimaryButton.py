from qfluentwidgets import PrimaryPushButton


class RedPrimaryPushButton(PrimaryPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(
            """ PrimaryPushButton { background-color: rgb(201, 79, 79);
             color: white; border: none; border-radius: 5px;
              } 
              PrimaryPushButton:hover { 
              background-color: rgb(171, 49, 49); 
            } """)
