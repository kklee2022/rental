"use client";

import { X } from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { titleCase } from "@/lib/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`button button--${variant} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`field ${className}`.trim()}>
      <span className="field__label">{label}</span>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="input input--select" {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="input input--textarea" {...props} />;
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  width = "560px",
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <section
        aria-modal="true"
        className="modal"
        role="dialog"
        style={{ maxWidth: width }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal__header">
          <div>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <Button
            aria-label="關閉"
            className="icon-button"
            onClick={onClose}
            variant="ghost"
          >
            <X size={18} />
          </Button>
        </header>
        <div className="modal__body">{children}</div>
      </section>
    </div>
  );
}

const positiveStatuses = new Set([
  "active",
  "approved",
  "available",
  "completed",
  "confirmed",
  "delivered",
  "found",
  "in_progress",
  "paid",
  "ready_for_dispatch",
  "reserved",
  "signed",
]);

const warningStatuses = new Set([
  "draft",
  "held",
  "issued",
  "on_hold",
  "partial",
  "partially_paid",
  "pending_approval",
  "preparing",
  "at_site",
  "scheduled",
  "unexpected",
  "return_inspection",
]);

const dangerStatuses = new Set([
  "blocked",
  "cancelled",
  "lost_write_off",
  "missing",
  "overdue",
  "rejected",
  "safety_locked",
  "void",
]);

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const value = status ?? "unknown";
  const tone = dangerStatuses.has(value)
    ? "danger"
    : positiveStatuses.has(value)
      ? "success"
      : warningStatuses.has(value)
        ? "warning"
        : "neutral";
  return <span className={`status status--${tone}`}>{titleCase(value)}</span>;
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__mark" />
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function ErrorBanner({ children }: { children: ReactNode }) {
  return <div className="error-banner">{children}</div>;
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="loading-block" aria-label="載入中">
      {Array.from({ length: rows }).map((_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}
