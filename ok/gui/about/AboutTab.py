from qfluentwidgets import BodyLabel

from ok.gui.about.VersionCard import VersionCard
from ok.gui.launcher.UpdateBar import UpdateBar
from ok.gui.widget.Tab import Tab
from ok.util.file import get_path_relative_to_exe


class AboutTab(Tab):
    def __init__(self, config, updater):
        super().__init__()
        self.version_card = VersionCard(config, get_path_relative_to_exe(config.get('gui_icon')),
                                        config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        self.updater = updater
        # Create a QTextEdit instance
        self.add_widget(self.version_card)

        if self.updater is not None:
            self.update_bar = UpdateBar(config, self.updater)
            self.add_widget(self.update_bar)

        if about := config.get('about'):
            about_label = BodyLabel()
            about_label.setText(about)
            about_label.setWordWrap(True)
            about_label.setOpenExternalLinks(True)

            # Set the layout on the widget
            self.add_widget(about_label)
