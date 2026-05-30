"use client";

import { AppProgressBar } from "next-nprogress-bar";

export default function ProgressBar() {
  return (
    <AppProgressBar
      height="2px"
      color="var(--app-primary)"
      options={{ showSpinner: false }}
      shallowRouting
    />
  );
}
