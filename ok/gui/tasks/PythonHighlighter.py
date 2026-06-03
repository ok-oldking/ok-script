import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class PythonHighlighter(QSyntaxHighlighter):
    """Simple Python syntax highlighter for QTextDocument-based editors."""

    def __init__(self, document):
        super().__init__(document)
        self.highlightingRules = []

        keywordFormat = QTextCharFormat()
        keywordFormat.setForeground(QColor("#569CD6"))
        keywordFormat.setFontWeight(QFont.Bold)
        keywords = ["and", "as", "assert", "break", "class", "continue", "def",
                    "del", "elif", "else", "except", "False", "finally", "for",
                    "from", "global", "if", "import", "in", "is", "lambda", "None",
                    "nonlocal", "not", "or", "pass", "raise", "return", "True",
                    "try", "while", "with", "yield"]
        for word in keywords:
            pattern = f"\\b{word}\\b"
            self.highlightingRules.append((pattern, keywordFormat))

        functionFormat = QTextCharFormat()
        functionFormat.setForeground(QColor("#4EC9B0"))
        functionFormat.setFontWeight(QFont.Bold)
        self.highlightingRules.append(("\\b[A-Za-z0-9_]+(?=\\()", functionFormat))

        selfFormat = QTextCharFormat()
        selfFormat.setForeground(QColor("#A074C4"))
        selfFormat.setFontItalic(True)
        self.highlightingRules.append(("\\bself\\b", selfFormat))

        stringFormat = QTextCharFormat()
        stringFormat.setForeground(QColor("#D69D85"))
        self.highlightingRules.append(("\"[^\"]*\"", stringFormat))
        self.highlightingRules.append(("'[^']*'", stringFormat))

        commentFormat = QTextCharFormat()
        commentFormat.setForeground(QColor("#57A64A"))
        self.highlightingRules.append(("#[^\n]*", commentFormat))

        self.compiledRules = [(re.compile(pattern), fmt) for pattern, fmt in self.highlightingRules]

    def highlightBlock(self, text):
        for pattern, text_format in self.compiledRules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)
