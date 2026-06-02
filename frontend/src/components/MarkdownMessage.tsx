import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type {ReactNode} from "react";
import CodeBlock from "./CodeBlock";

import "highlight.js/styles/github-dark.css";

interface Props {
  content: string;
}

/**
 * Renders assistant message text as GitHub-flavoured markdown with:
 *   - Syntax-highlighted code blocks (rehype-highlight + github-dark theme)
 *   - Tables, task lists, strikethrough (remark-gfm)
 *   - Custom CodeBlock with copy button + language badge
 *   - External links open in new tab
 */
export default function MarkdownMessage({content}: Props) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Block + inline code share the same handler in react-markdown v9.
          code(props) {
            const {className, children, node} = props;
            const match = /language-(\w+)/.exec(className ?? "");
            // Inline code: no language class AND single text-node child.
            const isBlock =
              match !== null ||
              node?.position?.start.line !== node?.position?.end.line;

            if (!isBlock) {
              return (
                <code className="px-1.5 py-0.5 rounded bg-surface-hover text-[0.875em] text-text-primary font-mono">
                  {children}
                </code>
              );
            }
            const language = match?.[1] ?? "";
            const rawText = extractText(children).replace(/\n$/, "");
            return (
              <CodeBlock language={language} code={rawText}>
                {children}
              </CodeBlock>
            );
          },
          // ReactMarkdown wraps block code in <pre>. Our CodeBlock already
          // renders its own <pre>, so unwrap to avoid double-pre nesting.
          pre({children}) {
            return <>{children}</>;
          },
          a({href, children}) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent underline-offset-2 hover:underline"
              >
                {children}
              </a>
            );
          },
          ul({children}) {
            return (
              <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>
            );
          },
          ol({children}) {
            return (
              <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>
            );
          },
          h1({children}) {
            return (
              <h1 className="text-2xl font-bold tracking-tight mt-6 mb-3 text-text-primary">
                {children}
              </h1>
            );
          },
          h2({children}) {
            return (
              <h2 className="flex items-center gap-2 text-lg font-semibold mt-6 mb-3 pb-1.5 border-b border-border-light text-text-primary before:content-[''] before:w-1 before:h-4 before:rounded-full before:bg-accent">
                {children}
              </h2>
            );
          },
          h3({children}) {
            return (
              <h3 className="text-base font-semibold mt-4 mb-1.5 text-text-primary">
                {children}
              </h3>
            );
          },
          p({children}) {
            return (
              <p className="my-2.5 leading-7 text-text-secondary">{children}</p>
            );
          },
          strong({children}) {
            return (
              <strong className="font-semibold text-text-primary">
                {children}
              </strong>
            );
          },
          blockquote({children}) {
            return (
              <blockquote className="border-l-4 border-accent/60 bg-accent/5 pl-4 pr-3 py-2 my-4 rounded-r-lg text-text-secondary italic">
                {children}
              </blockquote>
            );
          },
          table({children}) {
            return (
              <div className="my-4 overflow-x-auto rounded-lg border border-border-light">
                <table className="w-full text-sm border-collapse">
                  {children}
                </table>
              </div>
            );
          },
          thead({children}) {
            return (
              <thead className="bg-surface-alt">{children}</thead>
            );
          },
          tr({children}) {
            return (
              <tr className="border-b border-border-light last:border-b-0">
                {children}
              </tr>
            );
          },
          th({children}) {
            return (
              <th className="px-4 py-2.5 text-left font-semibold text-text-primary border-r border-border-light last:border-r-0">
                {children}
              </th>
            );
          },
          td({children}) {
            return (
              <td className="px-4 py-2.5 align-top text-text-secondary border-r border-border-light last:border-r-0">
                {children}
              </td>
            );
          },
          hr() {
            return <hr className="my-5 border-border-light" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** Walks a React children tree and returns concatenated plain text. */
function extractText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    return extractText(
      (node as {props: {children?: ReactNode}}).props.children,
    );
  }
  return "";
}
