import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle
} from "@fluentui/react-components";
import { t } from "./i18n";

export function ConfirmDeleteDialog({ name, onCancel, onConfirm }: {
  name: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return <Dialog open modalType="modal" onOpenChange={(_event, data) => { if (!data.open) onCancel(); }}>
    <DialogSurface className="confirm-delete-dialog">
      <DialogBody className="confirm-delete-dialog-body">
        <DialogTitle>{t("Confirm Delete")}</DialogTitle>
        <DialogContent>{t("Are you sure you want to delete '{name}'?", { name })}</DialogContent>
        <DialogActions>
          <Button appearance="secondary" onClick={onCancel}>{t("Cancel")}</Button>
          <Button appearance="primary" onClick={onConfirm}>{t("Delete")}</Button>
        </DialogActions>
      </DialogBody>
    </DialogSurface>
  </Dialog>;
}
