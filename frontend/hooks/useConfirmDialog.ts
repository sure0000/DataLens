"use client";

import { useCallback, useState } from "react";

export type ConfirmAction = () => Promise<void> | void;

export interface ConfirmState {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  confirmName?: string;
  danger?: boolean;
  action: ConfirmAction;
}

const EMPTY_ACTION: ConfirmAction = () => {};
const INITIAL: ConfirmState = { open: false, title: "", action: EMPTY_ACTION };

export function useConfirmDialog() {
  const [state, setState] = useState<ConfirmState>(INITIAL);
  const [loading, setLoading] = useState(false);

  const confirm = useCallback((opts: Omit<ConfirmState, "open" | "action"> & { action: ConfirmAction }) => {
    setState({ ...opts, open: true });
  }, []);

  const handleConfirm = useCallback(async () => {
    setLoading(true);
    try {
      await state.action();
    } finally {
      setLoading(false);
      setState(INITIAL);
    }
  }, [state.action]);

  const handleCancel = useCallback(() => {
    setState(INITIAL);
  }, []);

  return { confirmState: state, confirmLoading: loading, confirm, handleConfirm, handleCancel };
}
