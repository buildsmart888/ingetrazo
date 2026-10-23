"""Synchronous, truthful progress on the IngeTrazo main GUI thread.

Never reports time-based fake percentages. Updates only when computation
reaches a named checkpoint. QApplication.processEvents keeps the dialog
visible and its Cancel button responsive between steps. Individual long
geometry/Sweep and IFC operations still run synchronously and may block
between checkpoints; optimizing or threading those requires an upstream API
change, not unsafe Qt mesh mutation off the GUI thread.
"""
from __future__ import annotations

class BuildCancelled(RuntimeError):
    """Raised at a safe checkpoint, rolling the SnapshotImport transaction back."""


class NullProgress:
    def begin(self, label="Preparing model"):
        return None
    def report(self, pct, label):
        return None
    def finish(self):
        return None
    def close(self):
        return None


class QtBuildProgress:
    def __init__(self, parent, title="GO RC Detailing — Building"):
        self.parent = parent
        self.title = title
        self.dialog = None
        self.cancelled = False
        self.values = []
        self.committing = False

    def begin(self, label="Preparing model"):
        if self.dialog is not None:
            return
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QProgressDialog
        dlg = QProgressDialog(label, "ยกเลิก / Cancel", 0, 100, self.parent)
        dlg.setWindowTitle(self.title)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.canceled.connect(lambda: setattr(self, "cancelled", True))
        self.dialog = dlg
        dlg.show()
        QApplication.processEvents()
        if self.cancelled:
            raise BuildCancelled("User cancelled before model generation")

    def report(self, pct, label):
        if self.dialog is None:
            self.begin(label)
        if self.cancelled and not self.committing:
            raise BuildCancelled("User cancelled GO RC generation")
        if not 0 <= pct <= 100:
            raise ValueError("Invalid progress percentage")
        self.values.append((int(pct), label))
        self.dialog.setLabelText(str(label))
        self.dialog.setValue(int(pct))
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        if self.cancelled and not self.committing:
            raise BuildCancelled("User cancelled GO RC generation")

    def commit(self):
        self.committing = True
        if self.dialog is not None:
            self.dialog.setCancelButton(None)

    def finish(self):
        if self.dialog is not None and not self.cancelled:
            self.dialog.setValue(100)

    def close(self):
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
