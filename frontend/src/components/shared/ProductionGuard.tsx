import { useState } from "react";

interface ProductionGuardProps {
  /** True when the action this guards would touch a connection tagged `environment: prod`. */
  isProduction: boolean;
  /** Label for the trigger button in the non-production case, and inside the guard banner. */
  actionLabel: string;
  /** Label shown on the trigger/confirm button while the action is in flight. */
  pendingLabel?: string;
  isPending?: boolean;
  /** Called only after the user has typed the literal confirmation phrase and clicked confirm. */
  onConfirm: () => void;
  /** Human-readable description of what is being executed, shown inside the dialog. */
  description?: string;
}

const CONFIRM_PHRASE = "EXECUTE PRODUCTION";

/**
 * Production-confirmation UI safeguard (T065 / Constitution Principle VII, FR-016).
 *
 * When `isProduction` is false, renders a plain action button — dev/test execution needs
 * no extra ceremony. When `isProduction` is true, the action is hidden behind a distinct
 * visual warning banner and a confirmation dialog that requires the operator to type an
 * exact phrase before the guarded action (`onConfirm`) can fire. This is a *UI* safeguard
 * only — the backend's own `confirm_production` gate (FR-016, 409
 * `production_confirmation_required`) is the actual enforcement boundary; this component
 * exists so an operator cannot reach that gate by muscle-memory-clicking through a plain
 * "Execute" button.
 */
export function ProductionGuard({
  isProduction,
  actionLabel,
  pendingLabel,
  isPending = false,
  onConfirm,
  description,
}: ProductionGuardProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  if (!isProduction) {
    return (
      <button type="button" onClick={onConfirm} disabled={isPending}>
        {isPending ? (pendingLabel ?? actionLabel) : actionLabel}
      </button>
    );
  }

  function closeDialog() {
    setDialogOpen(false);
    setConfirmText("");
  }

  function handleConfirm() {
    if (confirmText !== CONFIRM_PHRASE) {
      return;
    }
    closeDialog();
    onConfirm();
  }

  return (
    <div
      data-testid="production-guard"
      role="alert"
      style={{
        border: "3px solid #b3261e",
        borderRadius: 4,
        padding: "0.75rem 1rem",
        background: "#fdecea",
        color: "#5f2120",
      }}
    >
      <p style={{ fontWeight: "bold", margin: "0 0 0.5rem" }}>
        ⚠ PRODUCTION CONNECTION — this action reads from or writes to a database tagged
        `environment: prod`.
      </p>
      {description && <p style={{ margin: "0 0 0.5rem" }}>{description}</p>}
      <button
        type="button"
        data-testid="production-guard-trigger"
        onClick={() => setDialogOpen(true)}
        disabled={isPending}
      >
        {isPending ? (pendingLabel ?? actionLabel) : actionLabel}
      </button>

      {dialogOpen && (
        <dialog
          open
          data-testid="production-guard-dialog"
          aria-label="Confirm production execution"
          style={{
            marginTop: "0.75rem",
            padding: "0.75rem",
            border: "1px solid #b3261e",
            borderRadius: 4,
            background: "#fff",
          }}
        >
          <p>
            This is a production database. Type <strong>{CONFIRM_PHRASE}</strong> below to confirm
            you intend to run this for real.
          </p>
          <label>
            Confirmation phrase
            <input
              data-testid="production-guard-confirm-input"
              value={confirmText}
              onChange={(event) => setConfirmText(event.target.value)}
              autoComplete="off"
            />
          </label>
          <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              data-testid="production-guard-confirm-button"
              onClick={handleConfirm}
              disabled={confirmText !== CONFIRM_PHRASE}
            >
              Confirm and execute against production
            </button>
            <button type="button" onClick={closeDialog}>
              Cancel
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
