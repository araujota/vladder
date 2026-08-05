"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }
  return (
    <div className="command-row">
      <code>{command}</code>
      <button type="button" onClick={copy} title="Copy install command" aria-label="Copy install command">
        {copied ? <Check size={18} /> : <Copy size={18} />}
      </button>
    </div>
  );
}
