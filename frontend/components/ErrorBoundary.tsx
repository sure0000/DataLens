"use client";

import { Component, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { hasError: boolean; message: string };

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: unknown): State {
    const message = error instanceof Error ? error.message : "未知错误";
    return { hasError: true, message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-rose-50">
            <svg className="h-7 w-7 text-rose-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
          </div>
          <div>
            <p className="text-base font-semibold text-[#111827]">页面出现了错误</p>
            <p className="mt-1 text-sm text-[#6b7280]">{this.state.message}</p>
          </div>
          <button
            className="app-button-secondary app-button-xs"
            onClick={() => this.setState({ hasError: false, message: "" })}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
