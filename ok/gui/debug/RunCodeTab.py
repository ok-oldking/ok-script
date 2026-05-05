import io
import sys
import traceback

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import PushButton, TextEdit

from ok import Config
from ok.gui.widget.Tab import Tab


class RunCodeTab(Tab):
    update_result_text: Signal = Signal(str)

    def __init__(self, app_config, exit_event):
        super().__init__()
        self.config = Config('run_code', {'code': ""})
        
        container = QWidget()
        layout = QVBoxLayout(container)
        
        self.code_input = TextEdit()
        self.code_input.setPlaceholderText(self.tr("Enter Python code here..."))
        if self.config.get('code'):
            self.code_input.setText(self.config.get('code'))
        layout.addWidget(self.code_input, stretch=2)
        
        self.run_button = PushButton(self.tr("Run Code"))
        self.run_button.clicked.connect(self.run_code)
        layout.addWidget(self.run_button)
        
        self.output_area = TextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText(self.tr("Output will be shown here..."))
        layout.addWidget(self.output_area, stretch=1)
        
        self.add_card(self.tr("Run Python Code"), container)
        
        self.update_result_text.connect(self.output_area.setText)
        
    def run_code(self):
        code = self.code_input.toPlainText()
        self.config['code'] = code
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_output

        try:
            from ok import og
            local_vars = {'og': og}
            exec(code, globals(), local_vars)
        except Exception:
            traceback.print_exc()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        output = redirected_output.getvalue()
        self.update_result_text.emit(output)
