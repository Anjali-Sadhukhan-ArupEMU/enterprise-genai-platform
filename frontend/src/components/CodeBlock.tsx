import {useState, type ReactNode} from "react";

interface Props {
  language: string;
  code: string;
  children: ReactNode;
}

export default function CodeBlock({language, code, children}: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API can fail outside secure contexts — silently ignore
    }
  };

  const displayLang = language || "text";

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-[#30363d] bg-[#0d1117] text-[13px]">
      <div className="flex items-center justify-between px-3.5 py-1.5 bg-[#161b22] border-b border-[#30363d]">
        <span className="text-[11px] font-mono text-[#8b949e] uppercase tracking-wide">
          {displayLang}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[11px] text-[#8b949e] hover:text-white transition-colors cursor-pointer"
          aria-label="Copy code"
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="px-4 py-3 overflow-x-auto leading-relaxed m-0 text-[#c9d1d9]">
        <code className={`hljs language-${displayLang}`}>{children}</code>
      </pre>
    </div>
  );
}

function CopyIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
